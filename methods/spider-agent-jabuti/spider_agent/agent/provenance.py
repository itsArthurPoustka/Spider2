"""
provenance.py — Scientific Provenance & Telemetry Utilities for JABUTI-SQL / AkôFlow
====================================================================================

Provides helper functions for file hashing, export tool syntax classification,
and W3C PROV-JSON record construction according to the W3C PROV-DM standard.
"""

import csv
import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spider_agent")


def calculate_file_hash(filepath: str) -> str:
    """Returns SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def sanitize_prov_id(name: str) -> str:
    """Sanitizes strings for safe inclusion in W3C PROV identifiers."""
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "-", str(name))
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-._")
    return cleaned or "unknown"


def detect_export_syntax(
    actions: List[Any],
    target_filename: str = "result.csv",
) -> str:
    """
    Checks whether the final winning action that exported the result used
    `COPY (...) TO STDOUT WITH CSV HEADER` ("COPY_TO_STDOUT") or plain `psql -c` ("PSQL_PLAIN").
    Returns "NONE" if neither was used or if no action exported to the target CSV.
    """
    if not actions:
        return "NONE"

    clean_target = os.path.basename(target_filename or "result.csv") or "result.csv"
    target_pattern = re.escape(clean_target)

    # Helper to check if a bash command explicitly directs output to the target CSV
    def is_export_command(cmd: str) -> bool:
        # Matches redirection: > result.csv, >> result.csv, | tee result.csv
        if re.search(r"(?:>>?|\|\s*tee\s+(?:-[a-zA-Z]+\s+)?)[^\n|;&]*\b" + target_pattern + r"\b", cmd):
            return True
        # Matches psql output file flag: -o result.csv
        if re.search(r"(?:^|\s)-o\s+['\"]?[^\s'\"]*" + target_pattern + r"['\"]?", cmd):
            return True
        # Matches psql meta-command: \o result.csv
        if re.search(r"\\o\s+['\"]?[^\s'\"]*" + target_pattern + r"['\"]?", cmd):
            return True
        # Matches COPY ... TO '...result.csv'
        if re.search(r"\b(?:\\copy|copy)\b.*?\bTO\s+['\"][^'\"]*" + target_pattern + r"['\"]", cmd, flags=re.IGNORECASE | re.DOTALL):
            return True
        return False

    # Traverse actions in reverse to find the winning action that wrote to result.csv
    for act in reversed(actions):
        if act is None:
            continue
        code_str = getattr(act, "code", None)
        if not code_str or not isinstance(code_str, str):
            act_str = str(act)
            if act_str.startswith("Bash("):
                code_str = act_str
            else:
                continue

        if not is_export_command(code_str):
            continue

        # Found the action writing to result.csv; classify syntax
        if re.search(r"\bCOPY\b.*?\bTO\s+STDOUT\b", code_str, flags=re.IGNORECASE | re.DOTALL):
            return "COPY_TO_STDOUT"
        if re.search(r"\\copy\b", code_str, flags=re.IGNORECASE):
            return "COPY_TO_STDOUT"
        if re.search(r"\bpsql\b", code_str, flags=re.IGNORECASE):
            return "PSQL_PLAIN"

        # Exported via python, echo, or another non-psql tool
        return "NONE"

    return "NONE"


def resolve_schema_hash(ddl_path: Optional[str] = None) -> Optional[str]:
    """
    Computes or resolves the SHA256 digest of the database DDL schema file.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates = []
    if ddl_path:
        candidates.append(ddl_path)
    candidates.extend([
        os.path.join(base_dir, "..", "..", "JABUTI-SQL", "ddl", "ddl.sql"),
        os.path.join(base_dir, "..", "..", "..", "JABUTI-SQL", "ddl", "ddl.sql"),
        os.path.join(base_dir, "examples", "local_jabuti_000", "ddl.sql"),
    ])

    for path in candidates:
        if path and os.path.isfile(path):
            try:
                return calculate_file_hash(path)
            except Exception as e:
                logger.debug("Could not hash candidate schema file %s: %s", path, e)
    return None


def resolve_database_dump_hash(dump_path: Optional[str] = None) -> Optional[str]:
    """
    Computes or resolves the SHA256 digest of the database data dump file (.dump or dump.sql).
    Returns None if no actual database dump file is found locally.
    """
    env_hash = os.environ.get("JABUTI_DB_DUMP_SHA256")
    if env_hash:
        return env_hash

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates = []
    if dump_path:
        candidates.append(dump_path)
    candidates.extend([
        os.path.join(base_dir, "..", "..", "JABUTI-SQL", "jabuti_sql.dump"),
        os.path.join(base_dir, "..", "..", "..", "JABUTI-SQL", "jabuti_sql.dump"),
        os.path.join(base_dir, "..", "..", "JABUTI-SQL", "dump.sql"),
        os.path.join(base_dir, "..", "..", "..", "JABUTI-SQL", "dump.sql"),
    ])

    for path in candidates:
        if path and os.path.isfile(path):
            try:
                # Only hash files <= 500MB directly to avoid stalling task teardown
                if os.path.getsize(path) <= 500 * 1024 * 1024:
                    return calculate_file_hash(path)
            except Exception as e:
                logger.debug("Could not hash candidate db dump %s: %s", path, e)
    return None


def resolve_model_digest(
    model: str,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[str]:
    """
    Resolves the SHA256 digest of the model weights from local Ollama or environment.
    Returns None if unavailable (e.g. for proprietary commercial cloud APIs).
    """
    env_digest = os.environ.get("LLM_WEIGHTS_DIGEST")
    if env_digest:
        return env_digest

    # Attempt to query local Ollama tags endpoint
    host = base_url or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if host.endswith("/v1"):
        host = host[:-3]
    if host.endswith("/v1/"):
        host = host[:-4]

    try:
        import urllib.request
        import json as _json

        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "SpiderAgentJabuti"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = _json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                target = model.strip()
                target_base = target.split(":")[0]
                for m in models:
                    name = m.get("name", "")
                    m_model = m.get("model", "")
                    if target in (name, m_model) or target == name.split(":")[0] or target_base == name.split(":")[0]:
                        return m.get("digest")
    except Exception as e:
        logger.debug("Ollama model digest lookup skipped or unavailable: %s", e)

    return None


def build_w3c_prov_record(
    task_config: Dict[str, Any],
    model: str,
    provider: str,
    temperature: float,
    top_p: float,
    output_dir: str,
    container_name: str = "unknown_container",
    image_name: str = "spider_agent_jabuti-image",
    step_count: int = 0,
    total_duration_ms: float = 0.0,
    t_llm_ms: float = 0.0,
    t_db_ms: float = 0.0,
    tokens_prompt: Optional[int] = 0,
    tokens_completion: Optional[int] = 0,
    tokens_total: Optional[int] = 0,
    exit_code: int = 1,
    start_time_iso: str = "",
    end_time_iso: str = "",
    has_result_csv: bool = False,
    export_syntax: str = "NONE",
    model_digest: Optional[str] = None,
    db_dump_hash: Optional[str] = None,
    db_name: str = "jabuti_sql",
    pg_host: str = "jabuti-postgres",
    pg_port: int = 5432,
) -> Dict[str, Any]:
    """
    Generates a W3C PROV-JSON dictionary connecting:
    - Entities:
        * TaskSpec (parent_id, persona, difficulty, prompt hash)
        * DatabaseState (dump hash)
        * ModelVersion (tag, digest)
        * PredictionOutput (result.csv hash, export tool syntax)
        * Metrics (t_total_ms, t_llm_ms, t_db_ms, step_count, token counts)
    - Activities:
        * TaskExecution (start/end timestamp)
    - Agents:
        * LLMBackend
        * PostgreSQLServer
        * AkôFlowEngine
    - Relations:
        * wasAssociatedWith, used, wasGeneratedBy, wasDerivedFrom
    """
    task_id = str(task_config.get("instance_id", task_config.get("id", "unknown_task")))
    instruction_text = str(
        task_config.get("question", task_config.get("instruction", ""))
    )
    prompt_hash = hashlib.sha256(instruction_text.encode("utf-8")).hexdigest()

    csv_path = os.path.join(output_dir, "result.csv") if output_dir else ""
    csv_hash: Optional[str] = None
    csv_row_count = 0
    if csv_path and os.path.isfile(csv_path) and os.path.getsize(csv_path) > 0:
        try:
            csv_hash = calculate_file_hash(csv_path)
            with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                rows = list(reader)
                csv_row_count = max(0, len(rows) - 1) if len(rows) > 0 else 0
            has_result_csv = True
        except Exception as e:
            logger.warning("Error reading result.csv for provenance: %s", e)

    # Resolve schema and dump hashes separately
    task_ddl = os.path.join(output_dir, "ddl.sql") if output_dir else None
    resolved_schema_hash = resolve_schema_hash(task_ddl)
    resolved_dump_hash = db_dump_hash if db_dump_hash is not None else resolve_database_dump_hash()

    safe_model = sanitize_prov_id(model.split("/")[-1])
    resolved_digest = model_digest or resolve_model_digest(model, provider)

    task_entity_id = f"jabuti:task:{task_id}"
    db_entity_id = f"jabuti:db:{db_name}"
    model_entity_id = f"jabuti:model:{safe_model}"
    container_entity_id = f"jabuti:container:{container_name}"
    prediction_entity_id = f"jabuti:prediction:{safe_model}:{task_id}"
    metrics_entity_id = f"jabuti:metrics:{safe_model}:{task_id}"
    trajectory_entity_id = f"jabuti:trajectory:{safe_model}:{task_id}"

    activity_id = f"jabuti:activity:{task_id}"

    llm_agent_id = f"jabuti:agent:LLMBackend:{safe_model}"
    pg_agent_id = "jabuti:agent:PostgreSQLServer"
    akoflow_agent_id = "jabuti:agent:AkoFlowEngine"

    p_tok = int(tokens_prompt) if tokens_prompt is not None else 0
    c_tok = int(tokens_completion) if tokens_completion is not None else 0
    t_tok = int(tokens_total) if tokens_total is not None else (p_tok + c_tok)

    raw_parent_id = task_config.get("parent_id")
    parent_id_val = str(raw_parent_id) if raw_parent_id is not None else None
    persona_val = task_config.get("persona") or None
    difficulty_val = task_config.get("difficulty") or None

    status_str = "SUCCESS" if exit_code == 0 else ("TIMEOUT" if exit_code == 2 else "FAILURE")
    is_partial = bool(exit_code != 0 and (has_result_csv or step_count > 0))

    prov_doc: Dict[str, Any] = {
        "prefix": {
            "prov": "http://www.w3.org/ns/prov#",
            "jabuti": "http://jabuti-sql.org/provenance/",
            "akoflow": "http://akoflow.org/provenance/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
        "entity": {
            task_entity_id: {
                "prov:type": "jabuti:TaskSpec",
                "jabuti:instance_id": task_id,
                "jabuti:parent_id": parent_id_val,
                "jabuti:parent_group": parent_id_val,
                "jabuti:persona": persona_val,
                "jabuti:difficulty": difficulty_val,
                "jabuti:prompt_hash": prompt_hash,
                "jabuti:question": instruction_text,
            },
            db_entity_id: {
                "prov:type": "jabuti:DatabaseState",
                "jabuti:database_name": db_name,
                "jabuti:schema_sha256": resolved_schema_hash,
                "jabuti:dump_sha256": resolved_dump_hash,
                "jabuti:host": pg_host,
                "jabuti:port": pg_port,
            },
            model_entity_id: {
                "prov:type": "jabuti:ModelVersion",
                "jabuti:tag": model,
                "jabuti:model_id": model,
                "jabuti:digest": resolved_digest,
                "jabuti:weights_digest": resolved_digest,
                "jabuti:provider": provider or None,
                "jabuti:temperature": temperature,
                "jabuti:top_p": top_p,
            },
            container_entity_id: {
                "prov:type": "jabuti:DockerContainer",
                "jabuti:container_name": container_name,
                "jabuti:image_name": image_name,
            },
            prediction_entity_id: {
                "prov:type": "jabuti:PredictionOutput",
                "jabuti:file_sha256": csv_hash,
                "jabuti:export_tool": export_syntax or "NONE",
                "jabuti:export_syntax": export_syntax or "NONE",
                "jabuti:row_count": csv_row_count,
                "jabuti:has_result": bool(has_result_csv),
            },
            metrics_entity_id: {
                "prov:type": "jabuti:Metrics",
                "jabuti:step_count": int(step_count),
                "jabuti:t_total_ms": round(float(total_duration_ms), 2),
                "jabuti:t_llm_ms": round(float(t_llm_ms), 2),
                "jabuti:t_db_ms": round(float(t_db_ms), 2),
                "jabuti:tokens_prompt": p_tok,
                "jabuti:tokens_completion": c_tok,
                "jabuti:tokens_total": t_tok,
                "jabuti:exit_code": int(exit_code),
            },
            trajectory_entity_id: {
                "prov:type": "jabuti:TrajectoryJSON",
                "jabuti:step_count": int(step_count),
            },
        },
        "activity": {
            activity_id: {
                "prov:type": "jabuti:TaskExecution",
                "prov:startTime": start_time_iso,
                "prov:endTime": end_time_iso,
                "jabuti:exit_code": int(exit_code),
                "jabuti:status": status_str,
                "jabuti:is_partial": is_partial,
            }
        },
        "agent": {
            llm_agent_id: {
                "prov:type": "prov:SoftwareAgent",
                "jabuti:role": "LLMBackend",
                "jabuti:model": model,
                "jabuti:provider": provider or "unknown",
            },
            pg_agent_id: {
                "prov:type": "prov:SoftwareAgent",
                "jabuti:role": "PostgreSQLServer",
                "jabuti:engine": "PostgreSQL 16",
                "jabuti:host": pg_host,
                "jabuti:port": pg_port,
            },
            akoflow_agent_id: {
                "prov:type": "prov:SoftwareAgent",
                "jabuti:role": "AkôFlowEngine",
                "jabuti:engine": "AkôFlow Workflow & Provenance Engine",
            },
        },
        "wasAssociatedWith": {
            "_:waw1": {
                "prov:activity": activity_id,
                "prov:agent": llm_agent_id,
                "prov:role": "LLMBackend",
            },
            "_:waw2": {
                "prov:activity": activity_id,
                "prov:agent": pg_agent_id,
                "prov:role": "PostgreSQLServer",
            },
            "_:waw3": {
                "prov:activity": activity_id,
                "prov:agent": akoflow_agent_id,
                "prov:role": "AkôFlowEngine",
            },
        },
        "used": {
            "_:u1": {
                "prov:activity": activity_id,
                "prov:entity": task_entity_id,
            },
            "_:u2": {
                "prov:activity": activity_id,
                "prov:entity": db_entity_id,
            },
            "_:u3": {
                "prov:activity": activity_id,
                "prov:entity": model_entity_id,
            },
            "_:u4": {
                "prov:activity": activity_id,
                "prov:entity": container_entity_id,
            },
        },
        "wasGeneratedBy": {
            "_:wgb1": {
                "prov:entity": prediction_entity_id,
                "prov:activity": activity_id,
            },
            "_:wgb2": {
                "prov:entity": metrics_entity_id,
                "prov:activity": activity_id,
            },
            "_:wgb3": {
                "prov:entity": trajectory_entity_id,
                "prov:activity": activity_id,
            },
        },
        "wasDerivedFrom": {
            "_:wdf1": {
                "prov:generatedEntity": prediction_entity_id,
                "prov:usedEntity": task_entity_id,
            },
            "_:wdf2": {
                "prov:generatedEntity": prediction_entity_id,
                "prov:usedEntity": db_entity_id,
            },
            "_:wdf3": {
                "prov:generatedEntity": prediction_entity_id,
                "prov:usedEntity": model_entity_id,
            },
        },
    }
    return prov_doc

