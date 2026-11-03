import base64
import json
import logging
import os
import re
import time
from http import HTTPStatus
from io import BytesIO

from openai import AzureOpenAI
from typing import Dict, List, Optional, Tuple, Any, TypedDict
import dashscope
from groq import Groq
import google.generativeai as genai
import openai
import requests
import tiktoken
import signal

logger = logging.getLogger("api-llms")

_OLLAMA_CACHE = None
_LAST_LLM_USAGE: Dict[str, Optional[int]] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}


def get_last_llm_usage() -> Dict[str, Optional[int]]:
    """Returns token usage from the most recent call_llm() invocation."""
    return dict(_LAST_LLM_USAGE)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _estimate_messages_tokens(messages: list) -> int:
    total = 0
    for msg in messages or []:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += _estimate_tokens(part.get("text", ""))
    return total


def _record_usage(
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    messages: Optional[list] = None,
    output_text: Optional[str] = None,
) -> None:
    global _LAST_LLM_USAGE
    if prompt_tokens is None and messages is not None:
        prompt_tokens = _estimate_messages_tokens(messages)
    if completion_tokens is None and output_text is not None:
        completion_tokens = _estimate_tokens(output_text)
    p = int(prompt_tokens or 0)
    c = int(completion_tokens or 0)
    t = int(total_tokens) if total_tokens is not None else (p + c)
    _LAST_LLM_USAGE = {
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": t,
    }



def get_ollama_models(host="http://localhost:11434") -> set:
    global _OLLAMA_CACHE
    if _OLLAMA_CACHE is not None:
        return _OLLAMA_CACHE
    try:
        res = requests.get(f"{host}/api/tags", timeout=1)
        if res.status_code == 200:
            models = {m["name"] for m in res.json().get("models", [])}
            expanded = set(models)
            for m in models:
                if ":" in m:
                    expanded.add(m.split(":")[0])
            _OLLAMA_CACHE = expanded
            return expanded
    except Exception:
        pass
    _OLLAMA_CACHE = set()
    return _OLLAMA_CACHE


def resolve_llm_config(payload: dict) -> Tuple[str, str, Optional[str], str]:
    """
    Resolves (actual_model, provider, endpoint_url, api_key).
    
    Supports:
    1. Model prefixes: 'ollama/qwen2.5-coder:32b', 'openai/gpt-4o', etc.
    2. Explicit provider: payload['provider'] or LLM_PROVIDER env.
    3. Custom OpenAI-compatible base URL: payload['base_url'] or OPENAI_BASE_URL env.
    4. Auto-detection: local Ollama detection, OpenAI/cloud routing, and backward-compatible aliases.
    """
    raw_model = payload.get("model", "")
    provider = payload.get("provider") or os.environ.get("LLM_PROVIDER")
    base_url = payload.get("base_url") or os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL")
    api_key = payload.get("api_key") or os.environ.get("OPENAI_API_KEY")

    actual_model = raw_model
    if "/" in raw_model:
        prefix, rest = raw_model.split("/", 1)
        known_prefixes = {
            "ollama": "ollama",
            "local": "ollama",
            "vllm": "ollama",
            "openai": "openai",
            "azure": "azure",
            "deepseek": "deepseek",
            "groq": "groq",
            "together": "together",
            "claude": "claude",
            "gemini": "gemini",
            "dashscope": "dashscope",
        }
        if prefix.lower() in known_prefixes:
            if not provider:
                provider = known_prefixes[prefix.lower()]
            actual_model = rest

    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    # Explicit base_url takes highest precedence for OpenAI-compatible routing
    if base_url:
        b = base_url.rstrip("/")
        if not b.endswith("/chat/completions"):
            if not b.endswith("/v1"):
                b = f"{b}/v1"
            endpoint = f"{b}/chat/completions"
        else:
            endpoint = b
        return actual_model, "openai_compatible", endpoint, api_key or "ollama"

    # Explicit provider
    if provider in ["ollama", "local", "vllm"]:
        return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", api_key or "ollama"

    if provider:
        if provider == "openai":
            return actual_model, "openai", "https://api.openai.com/v1/chat/completions", api_key or os.environ.get("OPENAI_API_KEY")
        return actual_model, provider, None, api_key

    # Auto-detection if provider not explicitly specified:
    ollama_models = get_ollama_models(ollama_host)
    if (actual_model in ollama_models or raw_model in ollama_models or
            actual_model.startswith("gpt-qwen") or actual_model.startswith("gpt-devstral") or actual_model.startswith("gpt-oss")):
        return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", api_key or "ollama"

    # Known cloud models
    if actual_model.startswith("gpt-") or actual_model.startswith("o1"):
        if api_key and not api_key.startswith("ollama"):
            return actual_model, "openai", "https://api.openai.com/v1/chat/completions", api_key
        # If no OpenAI key but Ollama is running, fall back to Ollama
        if ollama_models:
            return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", "ollama"
        return actual_model, "openai", "https://api.openai.com/v1/chat/completions", api_key

    if actual_model.startswith("claude"):
        return actual_model, "claude", None, api_key
    if actual_model.startswith("azure"):
        return actual_model, "azure", None, api_key
    if actual_model.startswith("deepseek"):
        if os.environ.get("DEEPSEEK_API_KEY"):
            return actual_model, "deepseek", None, api_key
        return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", "ollama"
    if actual_model.startswith("qwen") or actual_model.startswith("Qwen"):
        if os.environ.get("DASHSCOPE_API_KEY"):
            return actual_model, "dashscope", None, api_key
        return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", "ollama"

    # Default to Ollama
    return actual_model, "ollama", f"{ollama_host}/v1/chat/completions", "ollama"


def _call_openai_compatible(endpoint: str, api_key: str, model_name: str, payload: dict) -> Tuple[bool, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'ollama'}"
    }
    logger.info("Generating content via %s with model: %s", endpoint, model_name)
    
    req_payload = {
        "model": model_name,
        "messages": payload["messages"],
        "max_tokens": payload.get("max_tokens", 2500),
        "temperature": payload.get("temperature", 0.5),
        "top_p": payload.get("top_p", 0.9),
    }
    if "stop" in payload and payload["stop"]:
        req_payload["stop"] = payload["stop"]
        
    if model_name.startswith("o1"):
        req_payload["max_completion_tokens"] = 10000
        req_payload.pop("max_tokens", None)
        req_payload.pop("temperature", None)
        req_payload.pop("top_p", None)

    code_value = 'unknown_error'
    for i in range(3):
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=req_payload,
                timeout=180
            )
            if response.status_code == 200:
                resp_json = response.json()
                output_message = resp_json['choices'][0]['message']['content']
                usage = resp_json.get('usage') or {}
                _record_usage(
                    usage.get('prompt_tokens'),
                    usage.get('completion_tokens'),
                    usage.get('total_tokens'),
                    messages=payload.get('messages'),
                    output_text=output_message,
                )
                return True, output_message
            else:
                logger.error("HTTP error %s from %s: %s", response.status_code, endpoint, response.text)
                try:
                    error_info = response.json()
                    code_value = error_info.get('error', {}).get('code', f"http_{response.status_code}")
                except Exception:
                    code_value = f"http_{response.status_code}"
                if code_value == "content_filter":
                    if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                        payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                if code_value == "context_length_exceeded":
                    return False, code_value
        except Exception as e:
            logger.error("Failed to call LLM: " + str(e))
            code_value = 'unknown_error'
            
        logger.error("Retrying ...")
        time.sleep(2 * (2 ** (i + 1)))
        
    return False, code_value


def call_llm(payload):
    global _LAST_LLM_USAGE
    _LAST_LLM_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    raw_messages = payload.get("messages") if isinstance(payload, dict) else None
    status, output = _call_llm_inner(payload)
    if status and (_LAST_LLM_USAGE.get("total_tokens") or 0) == 0:
        _record_usage(None, None, None, messages=raw_messages, output_text=output)
    return status, output


def _call_llm_inner(payload):
    actual_model, provider, endpoint_url, api_key = resolve_llm_config(payload)
    model = actual_model
    stop = ["Observation:", "\n\n\n\n", "\n \n \n"]

    if provider in ["ollama", "openai_compatible", "openai"]:
        return _call_openai_compatible(endpoint_url, api_key, actual_model, payload)

    elif model.startswith("azure"):
        client = AzureOpenAI(
            api_key = os.environ['AZURE_API_KEY'],  
            api_version = "2024-02-15-preview",
            azure_endpoint = os.environ['AZURE_ENDPOINT']
            )
        model_name = model.split("/")[-1]
        for i in range(3):
            try:
                response = client.chat.completions.create(model=model_name,messages=payload['messages'], max_tokens=payload['max_tokens'], top_p=payload['top_p'], temperature=payload['temperature'], stop=stop)
                response = response.choices[0].message.content
                # logger.info(f"Input: \n{payload['messages']}\nOutput:{response}")
                return True, response
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                error_info = e.response.json()  
                code_value = error_info['error']['code']
                if code_value == "content_filter":
                    if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                        payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                if code_value == "context_length_exceeded":
                    return False, code_value        
                logger.error("Retrying ...")
                time.sleep(10 * (2 ** (i + 1)))
        return False, code_value
        
    elif model.startswith("claude"):
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]

        gemini_messages = []

        for i, message in enumerate(messages):
            gemini_message = {
                "role": message["role"],
                "content": []
            }
            assert len(message["content"]) in [1, 2], "One text, or one text with one image"
            for part in message["content"]:

                if part['type'] == "image_url":
                    image_source = {}
                    image_source["type"] = "base64"
                    image_source["media_type"] = "image/png"
                    image_source["data"] = part['image_url']['url'].replace("data:image/png;base64,", "")
                    gemini_message['content'].append({"type": "image", "source": image_source})

                if part['type'] == "text":
                    gemini_message['content'].append({"type": "text", "text": part['text']})

            gemini_messages.append(gemini_message)
        
        if gemini_messages[0]['role'] == "system":
            gemini_system_message_item = gemini_messages[0]['content'][0]
            gemini_messages[1]['content'].insert(0, gemini_system_message_item)
            gemini_messages.pop(0)


        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {os.environ["GEMINI_API_KEY"]}',
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }  
        
        payload = json.dumps({"model": model,"messages": gemini_messages,"max_tokens": max_tokens,"temperature": temperature,"top_p": top_p})


        
        for i in range(3):
            try:
                response = requests.request("POST", "https://api2.aigcbest.top/v1/chat/completions", headers=headers, data=payload)
                logger.info(f"response_code {response.status_code}")
                if response.status_code == 200:
                    return True, response.json()['choices'][0]['message']['content']
                else:
                    error_info = response.json()  
                    code_value = error_info['error']['code']
                    if code_value == "content_filter":
                        if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                            payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                    if code_value == "context_length_exceeded":
                        return False, code_value
                    logger.error("Retrying ...")
                    time.sleep(10 * (2 ** (i + 1)))
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                time.sleep(10 * (2 ** (i + 1)))
                code_value = "context_length_exceeded"
        return False, code_value
                           

    elif model.startswith("mixtral"):
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]

        mistral_messages = []

        for i, message in enumerate(messages):
            mistral_message = {
                "role": message["role"],
                "content": ""
            }

            for part in message["content"]:
                mistral_message['content'] = part['text'] if part['type'] == "text" else ""

            mistral_messages.append(mistral_message)

        client = Groq(
            api_key=os.environ.get("GROQ_API_KEY"),
        )

        for i in range(2):
            try:
                logger.info("Generating content with model: %s", model)
                response = client.chat.completions.create(
                    messages=mistral_messages,
                    model=model,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    temperature=temperature,
                    stop = stop
                )
                return True, response.choices[0].message.content
                
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                time.sleep(10 * (2 ** (i + 1)))
                if hasattr(e, 'response'):
                    error_info = e.response.json()  
                    code_value = error_info['error']['code']
                    if code_value == "content_filter":
                        if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                            payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                    if code_value == "context_length_exceeded":
                        return False, code_value        
                else:
                    code_value = ""
                logger.error("Retrying ...") 

        return False, code_value
        
    # elif model.startswith("llama"):
    #     messages = payload["messages"]
    #     max_tokens = payload["max_tokens"]
    #     top_p = payload["top_p"]
    #     temperature = payload["temperature"]

    #     llama_messages = []

    #     for i, message in enumerate(messages):
    #         llama_message = {
    #             "role": message["role"],
    #             "content": ""
    #         }
    #         for part in message["content"]:
    #             llama_message['content'] = part['text'] if part['type'] == "text" else ""
    #             llama_messages.append(llama_message)   
    #         llama_messages.append(llama_message)

    #     for i in range(3):
    #         try:
    #             logger.info("Generating content with model: %s", model)
    #             response = dashscope.Generation.call(
    #                 model=model,
    #                 messages=llama_messages,
    #                 result_format="message",
    #                 max_length=max_tokens,
    #                 top_p=top_p,
    #                 temperature=temperature,
    #                 stop = stop
    #             )
    #             import pdb; pdb.set_trace()
    #             return True, response['output']['choices'][0]['message']['content']

    #         except Exception as e:
    #             logger.error("Failed to call LLM: " + str(e))
    #             time.sleep(4 * (2 ** (i + 1)))
    #             if hasattr(e, 'response'):
    #                 error_info = e.response.json()  
    #                 code_value = error_info['error']['code']
    #                 if code_value == "content_filter":
    #                     if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
    #                         payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
    #             else:
    #                 code_value = "context_length_exceeded"
    #             logger.error("Retrying ...")
    #     return False, code_value
    
    
    
    elif model.startswith("deepseek"):
        
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]
        from openai import OpenAI
        
        deepseek_messages = []

        for i, message in enumerate(messages):
            deepseek_message = {
                "role": message["role"],
                "content": ""
            }
            for part in message["content"]:
                deepseek_message['content'] = part['text'] if part['type'] == "text" else ""
                deepseek_messages.append(deepseek_message)
        client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
        for i in range(3):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=deepseek_messages,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    temperature=temperature
                )
                output_message = json.loads(response.json())['choices'][0]['message']['content']
                return True, output_message
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                if hasattr(e, 'response') and e.response is not None:
                    error_info = e.response.json()  
                    code_value = error_info['error']['code']

                    if code_value == "content_filter":
                        last_message = messages[-1]
                        if 'content' in last_message and isinstance(last_message['content'], str):
                            if not last_message['content'].endswith("They do not represent any real events or entities. ]"):
                                last_message['content'] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                        else:
                            logger.error("Unexpected message structure in 'messages'. Skipping content modification.")
                    elif code_value == "context_length_exceeded":
                        return False, code_value        
                else:
                    code_value = 'unknown_error'
                
                logger.error("Retrying ...")
                time.sleep(10 * (2 ** (i + 1)))
            return False, code_value


        
    elif model.startswith("qwen") or model.startswith("Qwen") or model.startswith("llama3.1"):
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]
        
        if model.startswith("llama3.1"):
            max_tokens = 2000

        qwen_messages = []

        for i, message in enumerate(messages):
            qwen_message = {
                "role": message["role"],
                "content": []
            }
            assert len(message["content"]) in [1, 2], "One text, or one text with one image"
            for part in message["content"]:
                qwen_message['content'].append({"text": part['text']}) if part['type'] == "text" else None

            qwen_messages.append(qwen_message)

        for i in range(3):
            try:
                logger.info("Generating content with model: %s", model)
                response = dashscope.Generation.call(
                    model=model,
                    messages=qwen_messages,
                    result_format="message",
                    max_length=max_tokens,
                    top_p=top_p,
                    temperature=temperature,
                    stop = stop
                )
                return True, response['output']['choices'][0]['message']['content']

            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                time.sleep(3 * (2 ** (i + 1)))
                if hasattr(e, 'response'):
                    error_info = e.response.json()  
                    code_value = error_info['error']['code']
                    if code_value == "content_filter":
                        if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                            payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                else:
                    code_value = "context_length_exceeded"
                logger.error("Retrying ...")
        return False, code_value


        
    elif model.startswith("codellama") or model.startswith("mistralai"):
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        if model == "codellama/CodeLlama-70b-Instruct-hf":
            max_tokens = 800
        top_p = payload["top_p"]
        temperature = payload["temperature"]

        mistral_messages = []

        for i, message in enumerate(messages):
            mistral_message = {
                "role": message["role"],
                "content": ""
            }

            for part in message["content"]:
                mistral_message['content'] = part['text'] if part['type'] == "text" else ""

            mistral_messages.append(mistral_message)

        from openai import OpenAI

        client = OpenAI(api_key=os.environ["TOGETHER_API_KEY"],
                        base_url='https://api.together.xyz',
                        )

        for i in range(3):
            try:
                logger.info("Generating content with model: %s", model)
                response = client.chat.completions.create(
                    messages=mistral_messages,
                    model=model,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    temperature=temperature
                )
                return True, response.choices[0].message.content
                
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                time.sleep(10 * (2 ** (i + 1)))
                # if hasattr(e, 'response'):
                #     error_info = e.response  
                #     code_value = error_info['error']['param']
                #     if "content" in code_value:
                #         if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                #             payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                #     if code_value == "max_tokens":
                #         return False, code_value        
                # else:
                code_value = "context_length_exceeded"
                logger.error("Retrying ...")

        return False, code_value



    elif model == "gemini-1.5-pro-latest":
        messages = payload["messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]

        gemini_messages = []

        for i, message in enumerate(messages):
            gemini_message = {
                "role": message["role"],
                "content": []
            }
            assert len(message["content"]) in [1, 2], "One text, or one text with one image"
            for part in message["content"]:

                if part['type'] == "image_url":
                    image_source = {}
                    image_source["type"] = "base64"
                    image_source["media_type"] = "image/png"
                    image_source["data"] = part['image_url']['url'].replace("data:image/png;base64,", "")
                    gemini_message['content'].append({"type": "image", "source": image_source})

                if part['type'] == "text":
                    gemini_message['content'].append({"type": "text", "text": part['text']})

            gemini_messages.append(gemini_message)

        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {os.environ["GEMINI_API_KEY"]}',
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Content-Type': 'application/json'
        }  
        
        payload = json.dumps({"model": model,"messages": gemini_messages,"max_tokens": max_tokens,"temperature": temperature,"top_p": top_p})


        
        for i in range(3):
            try:
                response = requests.request("POST", "https://api2.aigcbest.top/v1/chat/completions", headers=headers, data=payload)
                logger.info(f"response_code {response.status_code}")
                if response.status_code == 200:
                    return True, response.json()['choices'][0]['message']['content']
                else:
                    error_info = response.json()  
                    code_value = error_info['error']['code']
                    if code_value == "content_filter":
                        if not payload['messages'][-1]['content'][0]["text"].endswith("They do not represent any real events or entities. ]"):
                            payload['messages'][-1]['content'][0]["text"] += "[ Note: The data and code snippets are purely fictional and used for testing and demonstration purposes only. They do not represent any real events or entities. ]"
                    if code_value == "context_length_exceeded":
                        return False, code_value
                    logger.error("Retrying ...")
                    time.sleep(10 * (2 ** (i + 1)))
            except Exception as e:
                logger.error("Failed to call LLM: " + str(e))
                time.sleep(10 * (2 ** (i + 1)))
                code_value = "context_length_exceeded"
        return False, code_value

    else:
        fallback_endpoint = endpoint_url or f"{os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')}/v1/chat/completions"
        return _call_openai_compatible(fallback_endpoint, api_key or "ollama", actual_model, payload)