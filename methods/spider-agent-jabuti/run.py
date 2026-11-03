import argparse
import csv
import datetime
import json
import logging
import os
import random
import sys
import glob
import re
import time

from tqdm import tqdm

from spider_agent.envs.spider_agent import Spider_Agent_Env
from spider_agent.agent.agents import PromptAgent
from spider_agent.agent.provenance import (
    build_w3c_prov_record,
    calculate_file_hash,
    detect_export_syntax,
)


#  Logger Configs {{{ #
logger = logging.getLogger("spider_agent")
logger.setLevel(logging.DEBUG)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

file_handler = logging.FileHandler(os.path.join("logs", "normal-{:}.log".format(datetime_str)), encoding="utf-8")
debug_handler = logging.FileHandler(os.path.join("logs", "debug-{:}.log".format(datetime_str)), encoding="utf-8")
stdout_handler = logging.StreamHandler(sys.stdout)
sdebug_handler = logging.FileHandler(os.path.join("logs", "sdebug-{:}.log".format(datetime_str)), encoding="utf-8")

file_handler.setLevel(logging.INFO)
debug_handler.setLevel(logging.DEBUG)
stdout_handler.setLevel(logging.INFO)
sdebug_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s")
file_handler.setFormatter(formatter)
debug_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
sdebug_handler.setFormatter(formatter)

stdout_handler.addFilter(logging.Filter("spider_agent"))
sdebug_handler.addFilter(logging.Filter("spider_agent"))

logger.addHandler(file_handler)
logger.addHandler(debug_handler)
logger.addHandler(stdout_handler)
logger.addHandler(sdebug_handler)
#  }}} Logger Configs # 



def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end evaluation on the benchmark"
    )
    
    parser.add_argument("--max_steps", type=int, default=20)
    
    parser.add_argument("--max_memory_length", type=int, default=25)
    parser.add_argument("--suffix", '-s', type=str, default="gpt-4-try1")
    
    parser.add_argument("--model", type=str, default="gpt-4o")
    parser.add_argument("--provider", type=str, default=os.environ.get("LLM_PROVIDER", "ollama"),
                        help="LLM provider: 'ollama', 'openai', 'azure', 'deepseek', 'groq', or specify via model prefix (e.g. 'ollama/qwen2.5-coder:32b')")
    parser.add_argument("--base_url", type=str, default=os.environ.get("OPENAI_BASE_URL", os.environ.get("LLM_BASE_URL", None)),
                        help="Base URL for OpenAI-compatible LLM endpoint (e.g. http://localhost:11434/v1)")
    parser.add_argument("--api_key", type=str, default=None,
                        help="API key for LLM endpoint (default: OPENAI_API_KEY env or 'ollama')")
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--max_tokens", type=int, default=2500)
    parser.add_argument("--stop_token", type=str, default=None)
    
    # example config
    parser.add_argument("--test_path","-t", type=str, default="./examples/jabuti.jsonl")
    parser.add_argument("--example_index", "-i", type=str, default="all", help="index range of the examples to run, e.g., '0-10', '2,3', 'all'")
    parser.add_argument("--example_name", "-n", type=str, default="", help="name of the example to run")
    parser.add_argument("--overwriting", action="store_true", default=False)
    parser.add_argument("--retry_failed", action="store_true", default=False)

    # output related
    parser.add_argument("--output_dir", type=str, default="output")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--bq_only", action="store_true")
    parser.add_argument("--local_only", action="store_true")
    parser.add_argument("--dbt_only", action="store_true")
    parser.add_argument("--sf_only", action="store_true")
    # ─── JABUTI-SQL ADAPTATION ───────────────────────────────────────────
    # Added --pg_only flag to run exclusively the PostgreSQL-based JABUTI-SQL
    # tasks.  This mirrors the existing --bq_only, --local_only, etc. pattern.
    # ─────────────────────────────────────────────────────────────────────────
    parser.add_argument("--pg_only", action="store_true", default=True,
                        help="Run only PostgreSQL (JABUTI-SQL) tasks")
    parser.add_argument("--pg_host", type=str, default=os.environ.get("JABUTI_PG_HOST", "jabuti-postgres"),
                        help="PostgreSQL host for JABUTI tasks (default: jabuti-postgres or JABUTI_PG_HOST)")
    parser.add_argument("--pg_port", type=int, default=int(os.environ.get("JABUTI_PG_PORT", 5432)),
                        help="PostgreSQL port (default: 5432)")
    parser.add_argument("--docker_network", type=str, default=os.environ.get("SPIDER_DOCKER_NETWORK", "spider-net"),
                        help="Docker network for containers (default: spider-net)")
    
    
    args = parser.parse_args()

    return args



def test(
    args: argparse.Namespace,
    test_all_meta: dict = None
) -> None:
    scores = []
    
    # log args
    logger.info("Args: %s", args)

    model_name_for_id = args.model.split("/")[-1].replace(":", "_")
    if args.suffix == "":
        logger.warning("No suffix is provided, the experiment id will be the model name.")
        experiment_id = model_name_for_id
    else:
        experiment_id = model_name_for_id + "-" + args.suffix
        
    if args.plan:
        experiment_id = f"{experiment_id}-plan"

    env_config = \
    {
        "image_name": "spider_agent-image",
        "init_args": {
            "name": experiment_id,
            "work_dir": "/workspace",
        }
    }
    
    agent = PromptAgent(
        model=args.model,
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        top_p=args.top_p,
        temperature=args.temperature,
        max_memory_length=args.max_memory_length,
        max_steps=args.max_steps,
        use_plan=args.plan
    )
    valid_ids = []
    ## load task configs
    assert os.path.exists(args.test_path), f"Invalid test_path: {args.test_path}"
    # ─── JABUTI-SQL ADAPTATION ───────────────────────────────────────────
    # Original code only accepts .jsonl files.  We keep that as default but
    # the assertion message is now more helpful.
    # ─────────────────────────────────────────────────────────────────────
    assert args.test_path.endswith(".jsonl"), f"test_path must be a .jsonl file: {args.test_path}"
    with open(args.test_path, "r") as f:
        task_configs = [json.loads(line) for line in f]

        
    if args.example_name != "":
        task_configs = [
            task for task in task_configs
            if args.example_name in task.get("instance_id", task.get("id", ""))
        ]
    else:
        if args.example_index != "all":
            if "-" in args.example_index:
                start, end = map(int, args.example_index.split("-"))
                task_configs = task_configs[start:end]
            else:
                indices = list(map(int, args.example_index.split(",")))
                task_configs = [task_configs[i] for i in indices]
    
    for task_config in task_configs:
        instance_id = experiment_id +"/"+ task_config["instance_id"]
        output_dir = os.path.join(args.output_dir, instance_id)
        result_json_path =os.path.join(output_dir, "spider/result.json")


        task_type = None
        if task_config["instance_id"].startswith("bq") or task_config["instance_id"].startswith("ga"):
            task_type = 'bq'
            task_config['type'] = 'Bigquery'
        elif task_config["instance_id"].startswith("local"):
            # ─── JABUTI-SQL ADAPTATION ───────────────────────────────────
            # JABUTI-SQL instance_ids start with "local_jabuti_".  We need
            # to distinguish them from regular local (SQLite) tasks.  The
            # type is already set to "PostgreSQL" in jabuti.jsonl, so we
            # check for that first.  If the JSONL already has type set, we
            # preserve it; otherwise we default to 'Local' for backward
            # compatibility with existing Spider2-lite local tasks.
            # ─────────────────────────────────────────────────────────────
            if task_config.get('type') == 'PostgreSQL':
                task_type = 'pg'
            else:
                task_type = 'local'
                task_config['type'] = 'Local'
        elif task_config["instance_id"].startswith("sf"):
            task_type = 'sf'
            task_config['type'] = 'Snowflake'
        else:
            task_type = 'dbt'

        valid_types = set()
        if args.local_only: valid_types.add('local')
        if args.bq_only: valid_types.add('bq')
        if args.sf_only: valid_types.add('sf')
        if args.dbt_only: valid_types.add('dbt')
        # ─── JABUTI-SQL ADAPTATION ───────────────────────────────────────
        if args.pg_only: valid_types.add('pg')
        # ─────────────────────────────────────────────────────────────────
        
        if  (args.local_only or args.bq_only or args.sf_only or args.dbt_only or args.pg_only):
            if task_type not in valid_types: continue
        else:
            pass

        valid_ids.append(task_config["instance_id"])
        
        if not args.overwriting and os.path.exists(result_json_path):
            logger.info("Skipping %s", instance_id)
            continue
        elif os.path.exists(result_json_path):
            logger.info("Overwriting %s", instance_id)
        else:
            logger.info("Running %s", instance_id)
        if args.retry_failed and os.path.exists(result_json_path):
            with open(result_json_path, "r") as f:
                result = json.load(f)
                if result["finished"] and (not "FAIL" in result["result"]) and (not "error" in result["result"].lower()):
                    logger.info("Skipping %s", instance_id)
                    continue
            logger.info("Retrying %s", instance_id)

        if os.path.exists(output_dir):
            os.system(f"rm -rf {output_dir}")
            logger.info("Removed existing %s", output_dir)

        os.makedirs(output_dir, exist_ok=True)

        # Sanitize container name for Docker (only [a-zA-Z0-9][a-zA-Z0-9_.-] allowed)
        safe_container_name = re.sub(r'[^a-zA-Z0-9_.-]', '-', f"{experiment_id}-{task_config['instance_id']}")
        env_config["init_args"]["name"] = safe_container_name

        # ─── JABUTI-SQL ADAPTATION ───────────────────────────────────────
        # For PostgreSQL tasks, use spider_agent_jabuti-image and attach
        # to the shared docker_network so the container can query the
        # standing jabuti-postgres service.
        # ─────────────────────────────────────────────────────────────────
        if task_type == 'pg':
            env_config["image_name"] = "spider_agent_jabuti-image"
            if args.docker_network:
                env_config["init_args"]["network_mode"] = args.docker_network
            env_config["init_args"]["environment"] = {
                "PGHOST": args.pg_host,
                "PGPORT": str(args.pg_port),
                "PGUSER": "postgres",
                "PGDATABASE": "jabuti_sql",
            }
        else:
            env_config["image_name"] = "spider_agent-image"

        
        source_data_dir = os.path.dirname(args.test_path)        
        task_config['config'] = [{"type": "copy_all_subfiles", "parameters": {"dirs": [os.path.join(source_data_dir, task_config["instance_id"])]}}]

        start_time = time.time()
        start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        env = None
        done = False
        result_output = ""
        trajectory = {"trajectory": []}
        result_files = {}
        error_message = None

        try:
            env = Spider_Agent_Env(
                env_config=env_config,
                task_config=task_config,
                cache_dir="./cache",
                mnt_dir=output_dir
            )

            agent.set_env_and_task(env)

            logger.info('Task input:' + task_config.get('question', task_config.get('instruction', '')))
            done, result_output = agent.run()
            trajectory = agent.get_trajectory()
            result_files = env.post_process()
        except Exception as e:
            logger.exception("Task execution encountered exception: %s", e)
            error_message = str(e)
            done = False
            result_output = f"EXCEPTION: {e}"
            try:
                trajectory = agent.get_trajectory()
            except Exception:
                pass
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception as e:
                    logger.warning("Error closing env: %s", e)

        end_time = time.time()
        total_duration_ms = (end_time - start_time) * 1000.0
        end_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        step_count = len(trajectory.get("trajectory", []))

        os.makedirs(os.path.join(output_dir, "spider"), exist_ok=True)
        spider_result = {"finished": done, "steps": step_count,
                           "result": result_output,"result_files": result_files, **trajectory}
        with open(os.path.join(output_dir, "spider/result.json"), "w") as f:
            json.dump(spider_result, f, indent=2)

        # Delete sqlite files
        if task_type == 'local':
            sqlite_files = glob.glob(os.path.join(output_dir, '*.sqlite')) + glob.glob(os.path.join(output_dir, '*.duckdb'))

            for file_path in sqlite_files:
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

        target_result_csv = os.path.join(output_dir, "result.csv")
        has_result_csv = os.path.exists(target_result_csv) and os.path.getsize(target_result_csv) > 0
        csv_hash = calculate_file_hash(target_result_csv) if has_result_csv else None
        csv_row_count = 0
        if has_result_csv:
            try:
                with open(target_result_csv, "r", encoding="utf-8", errors="ignore") as f:
                    csv_row_count = max(0, len(list(csv.reader(f))) - 1)
            except Exception:
                pass

        if error_message is not None or "ERROR: Repeated action" in str(result_output):
            exit_code = 1
        elif not done and step_count >= args.max_steps:
            exit_code = 2
        elif done and has_result_csv:
            exit_code = 0
        else:
            exit_code = 1

        t_llm_ms = round(float(getattr(agent, "t_llm_ms", 0.0)), 2)
        t_db_ms = round(float(getattr(agent, "t_db_ms", 0.0)), 2)
        tokens_prompt = int(getattr(agent, "tokens_prompt", 0) or 0)
        tokens_completion = int(getattr(agent, "tokens_completion", 0) or 0)
        tokens_total = int(getattr(agent, "tokens_total", 0) or 0)
        export_syntax = getattr(agent, "export_syntax", "NONE")
        if not export_syntax or export_syntax == "NONE":
            export_syntax = detect_export_syntax(getattr(agent, "actions", []), result_output or "result.csv")

        metrics = {
            "instance_id": task_config["instance_id"],
            "model": args.model,
            "provider": args.provider,
            "step_count": step_count,
            "max_steps": args.max_steps,
            "finished": done,
            "done": done,
            "exit_code": exit_code,
            "t_total_ms": round(total_duration_ms, 2),
            "t_llm_ms": t_llm_ms,
            "t_db_ms": t_db_ms,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "tokens_total": tokens_total,
            "export_syntax": export_syntax,
            "result_output": result_output,
            "has_result_csv": has_result_csv,
            "csv_row_count": csv_row_count,
            "csv_sha256": csv_hash,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "error": error_message,
        }
        with open(os.path.join(output_dir, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        prov_record = build_w3c_prov_record(
            task_config=task_config,
            model=args.model,
            provider=args.provider,
            temperature=args.temperature,
            top_p=args.top_p,
            output_dir=output_dir,
            container_name=safe_container_name,
            image_name=env_config["image_name"],
            step_count=step_count,
            total_duration_ms=total_duration_ms,
            t_llm_ms=t_llm_ms,
            t_db_ms=t_db_ms,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            tokens_total=tokens_total,
            export_syntax=export_syntax,
            exit_code=exit_code,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            has_result_csv=has_result_csv,
            pg_host=args.pg_host,
            pg_port=args.pg_port,
        )
        with open(os.path.join(output_dir, "task_provenance.json"), "w", encoding="utf-8") as f:
            json.dump(prov_record, f, indent=2)

        logger.info("Finished %s", instance_id)

if __name__ == '__main__':
    args = config()
    
    test(args)