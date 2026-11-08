#!/usr/bin/env python3
"""
verify_akoflow_run.py — AkôFlow Execution & Provenance Verification Harness
===========================================================================

PURPOSE:
--------
Inspects the shared output directory after an AkôFlow workflow run (or local
multi-task execution) and validates:
1. Artifact Completeness & Integrity:
   - Every expected task directory contains `result.csv`, `metrics.json`, and
     `task_provenance.json`.
   - `result.csv` is non-empty and its actual SHA256 digest matches the digest
     recorded in both `metrics.json` (`csv_sha256`) and `task_provenance.json`
     (`jabuti:PredictionOutput` -> `jabuti:file_sha256`).
   - `task_provenance.json` conforms to the W3C PROV-JSON schema (`prefix`,
     `entity`, `activity`, `agent`, `wasAssociatedWith`, `used`,
     `wasGeneratedBy`, `wasDerivedFrom`).
2. Decomposed Latency & Telemetry Aggregation:
   - Computes mean, median, min, max, and cumulative totals across tasks for
     decomposed wall-clock latencies:
       * T_Total (`t_total_ms`)
       * T_LLM   (`t_llm_ms` — LLM inference wait time)
       * T_DB    (`t_db_ms` — PostgreSQL container execution time)
       * T_Other (`t_total_ms - t_llm_ms - t_db_ms` — orchestration overhead)
   - Aggregates ReAct `step_count`, token consumption (`tokens_prompt`,
     `tokens_completion`, `tokens_total`), and SQL export tool adherence
     (`COPY_TO_STDOUT` vs. `PSQL_PLAIN` vs. `NONE`).
3. AkôFlow `/provenance/` REST API Verification (Optional / Remote Mode):
   - When `--akoflow_api_url` (or `AKOFLOW_API_URL`) is provided, queries
     AkôFlow's `/provenance/` REST API endpoint to verify that activity
     execution records (`preflight-check`, `task-local_jabuti_XXX`,
     `evaluation`) were persisted in the provenance database.

USAGE:
------
  # Verify 3-task smoke test output directory (offline/local filesystem check):
  python methods/spider-agent-jabuti/akoflow/verify_akoflow_run.py \\
      --results_dir output/test_phase2 \\
      --expected_tasks 0,1,2

  # Verify full 69-task run and query AkôFlow REST API:
  python methods/spider-agent-jabuti/akoflow/verify_akoflow_run.py \\
      --results_dir /shared/output/qwen2.5-coder:32b \\
      --expected_tasks all \\
      --akoflow_api_url http://akoflow-server:8080 \\
      --workflow_name jabuti-sql-benchmark-qwen2.5-coder-32b
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    from spider_agent.agent.provenance import calculate_file_hash
except ImportError:
    def calculate_file_hash(filepath: str) -> str:
        """Fallback SHA256 file hash computation."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


REQUIRED_W3C_PROV_SECTIONS = (
    "prefix",
    "entity",
    "activity",
    "agent",
    "wasAssociatedWith",
    "used",
    "wasGeneratedBy",
    "wasDerivedFrom",
)

REQUIRED_METRICS_KEYS = (
    "instance_id",
    "model",
    "step_count",
    "exit_code",
    "t_total_ms",
    "t_llm_ms",
    "t_db_ms",
    "has_result_csv",
)


# =============================================================================
# Task Resolution Utilities
# =============================================================================
def parse_expected_tasks(
    expected_spec: str,
    results_dir: str,
    total_benchmark_tasks: int = 69,
) -> List[str]:
    """
    Resolves `--expected_tasks` into an ordered list of canonical task IDs
    (e.g. `['local_jabuti_000', 'local_jabuti_001', 'local_jabuti_002']`).

    Supported formats:
      - 'all': `local_jabuti_000` through `local_jabuti_068`
      - 'auto': discovers `local_jabuti_*` directories inside `results_dir`
      - Comma-separated indices, ranges, or task IDs: e.g. '0,1,2', '0-5',
        'local_jabuti_000,local_jabuti_001'
    """
    spec = (expected_spec or "auto").strip()
    if spec.lower() == "all":
        return [f"local_jabuti_{i:03d}" for i in range(total_benchmark_tasks)]

    if spec.lower() == "auto":
        discovered = discover_task_ids_in_dir(results_dir)
        if not discovered:
            raise ValueError(
                f"No 'local_jabuti_*' task directories found in '{results_dir}' "
                "under --expected_tasks=auto."
            )
        return discovered

    task_ids: List[str] = []
    seen = set()

    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue

        range_match = re.match(r"^(\d+)-(\d+)$", part)
        if range_match:
            start_idx = int(range_match.group(1))
            end_idx = int(range_match.group(2))
            if start_idx > end_idx:
                raise ValueError(f"Invalid task range '{part}' (start > end)")
            for idx in range(start_idx, end_idx + 1):
                tid = f"local_jabuti_{idx:03d}"
                if tid not in seen:
                    task_ids.append(tid)
                    seen.add(tid)
            continue

        if part.isdigit():
            tid = f"local_jabuti_{int(part):03d}"
            if tid not in seen:
                task_ids.append(tid)
                seen.add(tid)
            continue

        normalized = part[len("task-") :] if part.startswith("task-") else part
        if normalized not in seen:
            task_ids.append(normalized)
            seen.add(normalized)

    if not task_ids:
        raise ValueError(f"No valid task IDs parsed from --expected_tasks='{expected_spec}'")

    return task_ids


def discover_task_ids_in_dir(results_dir: str) -> List[str]:
    """Discovers `local_jabuti_*` subdirectories inside `results_dir`."""
    if not os.path.isdir(results_dir):
        return []

    direct_matches = sorted(
        entry
        for entry in os.listdir(results_dir)
        if entry.startswith("local_jabuti_")
        and os.path.isdir(os.path.join(results_dir, entry))
    )
    if direct_matches:
        return direct_matches

    # Also check one level deeper (e.g. /shared/output/<model>/local_jabuti_XXX)
    nested_matches = set()
    for sub in sorted(os.listdir(results_dir)):
        sub_path = os.path.join(results_dir, sub)
        if os.path.isdir(sub_path):
            for entry in os.listdir(sub_path):
                if entry.startswith("local_jabuti_") and os.path.isdir(
                    os.path.join(sub_path, entry)
                ):
                    nested_matches.add(entry)
    return sorted(nested_matches)


def locate_task_dir(results_dir: str, task_id: str) -> str:
    """
    Locates the directory for `task_id` inside `results_dir`.
    Supports both direct layout (`<results_dir>/<task_id>`) and model-namespaced
    layout (`<results_dir>/<model>/<task_id>`).
    """
    direct_path = os.path.join(results_dir, task_id)
    if os.path.isdir(direct_path):
        return direct_path

    if os.path.isdir(results_dir):
        for sub in sorted(os.listdir(results_dir)):
            sub_path = os.path.join(results_dir, sub)
            if os.path.isdir(sub_path):
                candidate = os.path.join(sub_path, task_id)
                if os.path.isdir(candidate):
                    return candidate

    return direct_path


# =============================================================================
# Per-Task Artifact & W3C PROV Validation
# =============================================================================
def validate_w3c_prov_document(
    prov_doc: Dict[str, Any],
    task_id: str,
    actual_csv_sha256: Optional[str],
    require_csv: bool = True,
) -> List[str]:
    """
    Validates a parsed `task_provenance.json` dictionary against the JABUTI-SQL
    W3C PROV-DM contract. Returns a list of validation error strings (empty if valid).
    """
    errors: List[str] = []

    for section in REQUIRED_W3C_PROV_SECTIONS:
        if section not in prov_doc or not isinstance(prov_doc[section], dict):
            errors.append(f"task_provenance.json missing or invalid section '{section}'")

    if errors:
        return errors

    entities = prov_doc["entity"]
    activities = prov_doc["activity"]
    agents = prov_doc["agent"]

    # 1. Verify TaskSpec entity
    task_entity_key = f"jabuti:task:{task_id}"
    if task_entity_key not in entities:
        errors.append(f"Missing TaskSpec entity '{task_entity_key}'")
    else:
        task_ent = entities[task_entity_key]
        if task_ent.get("jabuti:instance_id") != task_id:
            errors.append(
                f"TaskSpec instance_id mismatch: expected '{task_id}', "
                f"got '{task_ent.get('jabuti:instance_id')}'"
            )
        if not task_ent.get("jabuti:prompt_hash"):
            errors.append("TaskSpec entity missing 'jabuti:prompt_hash'")

    # 2. Verify DatabaseState entity
    db_entities = [
        k for k, v in entities.items() if v.get("prov:type") == "jabuti:DatabaseState"
    ]
    if not db_entities:
        errors.append("Missing DatabaseState entity ('prov:type': 'jabuti:DatabaseState')")

    # 3. Verify ModelVersion entity
    model_entities = [
        k for k, v in entities.items() if v.get("prov:type") == "jabuti:ModelVersion"
    ]
    if not model_entities:
        errors.append("Missing ModelVersion entity ('prov:type': 'jabuti:ModelVersion')")

    # 4. Verify PredictionOutput entity & hash linkage
    pred_entities = [
        (k, v)
        for k, v in entities.items()
        if v.get("prov:type") == "jabuti:PredictionOutput"
    ]
    if not pred_entities:
        errors.append(
            "Missing PredictionOutput entity ('prov:type': 'jabuti:PredictionOutput')"
        )
    else:
        _, pred_ent = pred_entities[0]
        prov_sha = pred_ent.get("jabuti:file_sha256")
        if require_csv:
            if not prov_sha:
                errors.append(
                    "PredictionOutput entity has empty/null 'jabuti:file_sha256'"
                )
            elif actual_csv_sha256 and prov_sha != actual_csv_sha256:
                errors.append(
                    f"PredictionOutput SHA256 mismatch: prov='{prov_sha[:12]}...' "
                    f"vs disk='{actual_csv_sha256[:12]}...'"
                )

    # 5. Verify Metrics entity
    metrics_entities = [
        (k, v) for k, v in entities.items() if v.get("prov:type") == "jabuti:Metrics"
    ]
    if not metrics_entities:
        errors.append("Missing Metrics entity ('prov:type': 'jabuti:Metrics')")

    # 6. Verify TaskExecution activity
    activity_key = f"jabuti:activity:{task_id}"
    if activity_key not in activities:
        errors.append(f"Missing TaskExecution activity '{activity_key}'")
    else:
        act = activities[activity_key]
        if not act.get("prov:startTime") or not act.get("prov:endTime"):
            errors.append(
                f"Activity '{activity_key}' missing startTime or endTime timestamps"
            )

    # 7. Verify required SoftwareAgents (LLMBackend, PostgreSQLServer, AkôFlowEngine)
    agent_roles = {a.get("jabuti:role") for a in agents.values() if isinstance(a, dict)}
    for expected_role in ("LLMBackend", "PostgreSQLServer", "AkôFlowEngine"):
        if expected_role not in agent_roles:
            errors.append(f"Missing SoftwareAgent with role '{expected_role}'")

    # 8. Verify non-empty relations
    for rel_section in ("wasAssociatedWith", "used", "wasGeneratedBy", "wasDerivedFrom"):
        if len(prov_doc.get(rel_section, {})) == 0:
            errors.append(f"Provenance relation section '{rel_section}' is empty")

    return errors


def verify_single_task_directory(
    task_id: str,
    task_dir: str,
    allow_non_zero_exit: bool = False,
) -> Dict[str, Any]:
    """
    Inspects a single task's output directory and validates `result.csv`,
    `metrics.json`, and `task_provenance.json`.
    """
    errors: List[str] = []
    warnings: List[str] = []

    result_csv_path = os.path.join(task_dir, "result.csv")
    metrics_json_path = os.path.join(task_dir, "metrics.json")
    prov_json_path = os.path.join(task_dir, "task_provenance.json")
    trajectory_json_path = os.path.join(task_dir, "trajectory.json")

    if not os.path.isdir(task_dir):
        return {
            "task_id": task_id,
            "task_dir": task_dir,
            "valid": False,
            "has_result_csv": False,
            "has_metrics_json": False,
            "has_provenance_json": False,
            "has_trajectory_json": False,
            "exit_code": None,
            "step_count": 0,
            "t_total_ms": 0.0,
            "t_llm_ms": 0.0,
            "t_db_ms": 0.0,
            "t_other_ms": 0.0,
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "tokens_total": 0,
            "export_syntax": "NONE",
            "csv_row_count": 0,
            "csv_sha256": None,
            "prov_status": "MISSING",
            "errors": [f"Task output directory not found: {task_dir}"],
            "warnings": [],
        }

    # 1. Check result.csv
    has_result_csv = os.path.isfile(result_csv_path) and os.path.getsize(result_csv_path) > 0
    actual_csv_sha256: Optional[str] = None
    if not os.path.isfile(result_csv_path):
        if not allow_non_zero_exit:
            errors.append("Missing required artifact: result.csv")
        else:
            warnings.append("result.csv not present (non-zero exit allowed)")
    elif os.path.getsize(result_csv_path) == 0:
        if not allow_non_zero_exit:
            errors.append("Artifact result.csv is empty (0 bytes)")
        else:
            warnings.append("result.csv is empty (0 bytes)")
    else:
        try:
            actual_csv_sha256 = calculate_file_hash(result_csv_path)
        except Exception as exc:
            errors.append(f"Failed to compute SHA256 of result.csv: {exc}")

    # 2. Check trajectory.json (informational warning if missing)
    has_trajectory_json = os.path.isfile(trajectory_json_path)
    if not has_trajectory_json:
        warnings.append("Optional artifact trajectory.json is missing")

    # 3. Check metrics.json
    has_metrics_json = os.path.isfile(metrics_json_path)
    metrics_data: Dict[str, Any] = {}
    if not has_metrics_json:
        errors.append("Missing required artifact: metrics.json")
    else:
        try:
            with open(metrics_json_path, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
            for req_key in REQUIRED_METRICS_KEYS:
                if req_key not in metrics_data:
                    errors.append(f"metrics.json missing required key '{req_key}'")
        except Exception as exc:
            errors.append(f"Malformed metrics.json: {exc}")

    # Extract telemetry fields safely
    exit_code = metrics_data.get("exit_code")
    step_count = int(metrics_data.get("step_count", 0) or 0)
    t_total_ms = float(metrics_data.get("t_total_ms", 0.0) or 0.0)
    t_llm_ms = float(metrics_data.get("t_llm_ms", 0.0) or 0.0)
    t_db_ms = float(metrics_data.get("t_db_ms", 0.0) or 0.0)
    t_other_ms = max(0.0, t_total_ms - (t_llm_ms + t_db_ms))
    tokens_prompt = int(metrics_data.get("tokens_prompt", 0) or 0)
    tokens_completion = int(metrics_data.get("tokens_completion", 0) or 0)
    tokens_total = int(
        metrics_data.get("tokens_total", tokens_prompt + tokens_completion) or 0
    )
    export_syntax = str(metrics_data.get("export_syntax", "NONE") or "NONE")
    csv_row_count = int(metrics_data.get("csv_row_count", 0) or 0)
    metrics_csv_sha256 = metrics_data.get("csv_sha256")

    if has_metrics_json:
        if t_total_ms < 0 or t_llm_ms < 0 or t_db_ms < 0:
            errors.append(
                f"Negative latency values in metrics.json: "
                f"t_total={t_total_ms}, t_llm={t_llm_ms}, t_db={t_db_ms}"
            )
        if not allow_non_zero_exit and exit_code != 0:
            errors.append(f"Task exited with non-zero exit_code={exit_code}")
        if actual_csv_sha256 and metrics_csv_sha256 != actual_csv_sha256:
            errors.append(
                f"metrics.json csv_sha256 ('{metrics_csv_sha256}') does not match "
                f"result.csv SHA256 ('{actual_csv_sha256}')"
            )

    # 4. Check task_provenance.json
    has_provenance_json = os.path.isfile(prov_json_path)
    prov_status = "MISSING"
    if not has_provenance_json:
        errors.append("Missing required artifact: task_provenance.json")
    else:
        try:
            with open(prov_json_path, "r", encoding="utf-8") as f:
                prov_data = json.load(f)
            prov_errors = validate_w3c_prov_document(
                prov_doc=prov_data,
                task_id=task_id,
                actual_csv_sha256=actual_csv_sha256,
                require_csv=not allow_non_zero_exit,
            )
            if prov_errors:
                errors.extend(prov_errors)
                prov_status = "INVALID"
            else:
                act_obj = prov_data.get("activity", {}).get(f"jabuti:activity:{task_id}", {})
                prov_status = str(act_obj.get("jabuti:status", "VALID"))
        except Exception as exc:
            errors.append(f"Malformed task_provenance.json: {exc}")
            prov_status = "MALFORMED"

    return {
        "task_id": task_id,
        "task_dir": task_dir,
        "valid": len(errors) == 0,
        "has_result_csv": has_result_csv,
        "has_metrics_json": has_metrics_json,
        "has_provenance_json": has_provenance_json,
        "has_trajectory_json": has_trajectory_json,
        "exit_code": exit_code,
        "step_count": step_count,
        "t_total_ms": round(t_total_ms, 2),
        "t_llm_ms": round(t_llm_ms, 2),
        "t_db_ms": round(t_db_ms, 2),
        "t_other_ms": round(t_other_ms, 2),
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "tokens_total": tokens_total,
        "export_syntax": export_syntax,
        "csv_row_count": csv_row_count,
        "csv_sha256": actual_csv_sha256,
        "prov_status": prov_status,
        "errors": errors,
        "warnings": warnings,
    }


# =============================================================================
# Decomposed Latency & Telemetry Aggregation
# =============================================================================
def aggregate_telemetry(task_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates decomposed latencies (T_LLM vs T_DB vs T_Total), step counts,
    token counts, and export tool syntax across all inspected tasks.
    """
    total_tasks = len(task_reports)
    valid_tasks = [r for r in task_reports if r["valid"]]
    tasks_with_metrics = [r for r in task_reports if r["has_metrics_json"]]

    if not tasks_with_metrics:
        return {
            "total_expected_tasks": total_tasks,
            "valid_task_count": len(valid_tasks),
            "failed_verification_count": total_tasks - len(valid_tasks),
            "tasks_with_metrics": 0,
            "latency_ms": {
                "avg_t_total_ms": 0.0,
                "avg_t_llm_ms": 0.0,
                "avg_t_db_ms": 0.0,
                "avg_t_other_ms": 0.0,
                "median_t_total_ms": 0.0,
                "median_t_llm_ms": 0.0,
                "median_t_db_ms": 0.0,
                "sum_t_total_ms": 0.0,
                "sum_t_llm_ms": 0.0,
                "sum_t_db_ms": 0.0,
                "sum_t_other_ms": 0.0,
                "llm_share_pct": 0.0,
                "db_share_pct": 0.0,
                "other_share_pct": 0.0,
                "llm_to_db_ratio": None,
            },
            "steps": {
                "avg_steps": 0.0,
                "median_steps": 0.0,
                "min_steps": 0,
                "max_steps": 0,
                "total_steps": 0,
            },
            "tokens": {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "avg_tokens_per_task": 0.0,
            },
            "export_syntax_counts": {},
            "exit_code_counts": {},
        }

    t_totals = [r["t_total_ms"] for r in tasks_with_metrics]
    t_llms = [r["t_llm_ms"] for r in tasks_with_metrics]
    t_dbs = [r["t_db_ms"] for r in tasks_with_metrics]
    t_others = [r["t_other_ms"] for r in tasks_with_metrics]
    steps = [r["step_count"] for r in tasks_with_metrics]

    sum_total = sum(t_totals)
    sum_llm = sum(t_llms)
    sum_db = sum(t_dbs)
    sum_other = sum(t_others)

    llm_share_pct = (sum_llm / sum_total * 100.0) if sum_total > 0 else 0.0
    db_share_pct = (sum_db / sum_total * 100.0) if sum_total > 0 else 0.0
    other_share_pct = (sum_other / sum_total * 100.0) if sum_total > 0 else 0.0
    llm_to_db_ratio = round(sum_llm / sum_db, 2) if sum_db > 0 else None

    syntax_counts: Dict[str, int] = {}
    exit_code_counts: Dict[str, int] = {}
    for r in tasks_with_metrics:
        syn = r.get("export_syntax", "NONE")
        syntax_counts[syn] = syntax_counts.get(syn, 0) + 1
        ec = str(r.get("exit_code", "unknown"))
        exit_code_counts[ec] = exit_code_counts.get(ec, 0) + 1

    total_prompt = sum(r["tokens_prompt"] for r in tasks_with_metrics)
    total_completion = sum(r["tokens_completion"] for r in tasks_with_metrics)
    total_tok = sum(r["tokens_total"] for r in tasks_with_metrics)

    return {
        "total_expected_tasks": total_tasks,
        "valid_task_count": len(valid_tasks),
        "failed_verification_count": total_tasks - len(valid_tasks),
        "tasks_with_metrics": len(tasks_with_metrics),
        "latency_ms": {
            "avg_t_total_ms": round(statistics.mean(t_totals), 2),
            "avg_t_llm_ms": round(statistics.mean(t_llms), 2),
            "avg_t_db_ms": round(statistics.mean(t_dbs), 2),
            "avg_t_other_ms": round(statistics.mean(t_others), 2),
            "median_t_total_ms": round(statistics.median(t_totals), 2),
            "median_t_llm_ms": round(statistics.median(t_llms), 2),
            "median_t_db_ms": round(statistics.median(t_dbs), 2),
            "sum_t_total_ms": round(sum_total, 2),
            "sum_t_llm_ms": round(sum_llm, 2),
            "sum_t_db_ms": round(sum_db, 2),
            "sum_t_other_ms": round(sum_other, 2),
            "llm_share_pct": round(llm_share_pct, 2),
            "db_share_pct": round(db_share_pct, 2),
            "other_share_pct": round(other_share_pct, 2),
            "llm_to_db_ratio": llm_to_db_ratio,
        },
        "steps": {
            "avg_steps": round(statistics.mean(steps), 2),
            "median_steps": round(statistics.median(steps), 2),
            "min_steps": min(steps),
            "max_steps": max(steps),
            "total_steps": sum(steps),
        },
        "tokens": {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tok,
            "avg_tokens_per_task": round(total_tok / len(tasks_with_metrics), 1),
        },
        "export_syntax_counts": syntax_counts,
        "exit_code_counts": exit_code_counts,
    }


# =============================================================================
# AkôFlow `/provenance/` REST API Verification
# =============================================================================
def verify_akoflow_provenance_api(
    api_url: Optional[str],
    expected_task_ids: List[str],
    workflow_name: Optional[str] = None,
    namespace: str = "escience-jabuti",
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
    """
    Queries AkôFlow's `/provenance/` REST API (if configured and reachable) to
    verify that activity execution records (`task-local_jabuti_XXX`) were
    recorded in the engine's PostgreSQL provenance store.

    Returns a dictionary describing the API verification status:
      - status: "SKIPPED" | "VERIFIED" | "PARTIAL" | "UNREACHABLE" | "ERROR"
      - endpoint: Resolved URL queried
      - recorded_activities: List of matching activity names found in API response
      - missing_activities: List of expected task activities not found in API response
      - message: Human-readable status explanation
    """
    if not api_url or not api_url.strip():
        return {
            "status": "SKIPPED",
            "endpoint": None,
            "recorded_activities": [],
            "missing_activities": [],
            "message": "No --akoflow_api_url provided (local/offline verification mode).",
        }

    base = api_url.strip().rstrip("/")
    if not base.endswith("/provenance"):
        endpoint = f"{base}/provenance/"
    else:
        endpoint = f"{base}/"

    query_params: Dict[str, str] = {}
    if namespace:
        query_params["namespace"] = namespace
    if workflow_name:
        query_params["workflow"] = workflow_name
    if query_params:
        endpoint = f"{endpoint}?{urllib.parse.urlencode(query_params)}"

    expected_activities = [f"task-{tid}" for tid in expected_task_ids]

    try:
        req = urllib.request.Request(
            endpoint,
            headers={
                "Accept": "application/json",
                "User-Agent": "SpiderAgentJabuti-Verifier/1.0",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            status_code = getattr(resp, "status", 200)
    except urllib.error.HTTPError as http_err:
        return {
            "status": "ERROR",
            "endpoint": endpoint,
            "http_status": http_err.code,
            "recorded_activities": [],
            "missing_activities": expected_activities,
            "message": f"AkôFlow provenance API returned HTTP {http_err.code}: {http_err.reason}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as net_err:
        return {
            "status": "UNREACHABLE",
            "endpoint": endpoint,
            "recorded_activities": [],
            "missing_activities": expected_activities,
            "message": f"AkôFlow provenance API unreachable at {endpoint}: {net_err}",
        }

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        # Fallback: scan raw response text if non-JSON or HTML/text listing
        payload = raw_body

    recorded_activities = _extract_recorded_activities(payload, expected_activities, expected_task_ids)
    missing_activities = [
        act for act in expected_activities if act not in recorded_activities
    ]

    if not missing_activities:
        status = "VERIFIED"
        msg = (
            f"All {len(expected_activities)} expected task activities verified in "
            f"AkôFlow /provenance/ API (HTTP {status_code})."
        )
    elif recorded_activities:
        status = "PARTIAL"
        msg = (
            f"Found {len(recorded_activities)}/{len(expected_activities)} task "
            f"activities in AkôFlow /provenance/ API. Missing: {missing_activities}"
        )
    else:
        status = "ERROR"
        msg = (
            f"AkôFlow /provenance/ API responded (HTTP {status_code}) but none of the "
            f"{len(expected_activities)} expected task activities were found."
        )

    return {
        "status": status,
        "endpoint": endpoint,
        "http_status": status_code,
        "recorded_activities": recorded_activities,
        "missing_activities": missing_activities,
        "message": msg,
    }


def _extract_recorded_activities(
    payload: Any,
    expected_activities: List[str],
    expected_task_ids: List[str],
) -> List[str]:
    """
    Extracts matching `task-local_jabuti_XXX` activity names from flexible
    AkôFlow `/provenance/` JSON payload structures (lists of workflow runs,
    activity objects, or W3C PROV activity maps).
    """
    serialized = json.dumps(payload) if not isinstance(payload, str) else payload
    matched: List[str] = []
    for act_name, tid in zip(expected_activities, expected_task_ids):
        if act_name in serialized or f"jabuti:activity:{tid}" in serialized:
            matched.append(act_name)
    return matched


# =============================================================================
# Console Summary Formatter
# =============================================================================
def print_verification_summary(
    results_dir: str,
    task_reports: List[Dict[str, Any]],
    summary: Dict[str, Any],
    api_report: Dict[str, Any],
) -> None:
    """Prints a formatted summary table of per-task artifacts, latencies, and provenance."""
    width = 98
    print("\n" + "=" * width)
    print("AKÔFLOW RUN & W3C PROV VERIFICATION REPORT")
    print("=" * width)
    print(f"Results Directory : {os.path.abspath(results_dir)}")
    print(
        f"Tasks Verified    : {summary['valid_task_count']}/{summary['total_expected_tasks']} passed "
        f"({summary['failed_verification_count']} failed)"
    )

    print("\n" + "-" * width)
    header = (
        f"{'Task ID':<18} | {'Status':<6} | {'Exit':>4} | {'Steps':>5} | "
        f"{'T_Total(ms)':>11} | {'T_LLM(ms)':>10} | {'T_DB(ms)':>9} | "
        f"{'Export Syntax':<14} | {'PROV':<8}"
    )
    print(header)
    print("-" * width)

    for r in task_reports:
        status_label = "PASS" if r["valid"] else "FAIL"
        exit_str = str(r["exit_code"]) if r["exit_code"] is not None else "N/A"
        print(
            f"{r['task_id']:<18} | {status_label:<6} | {exit_str:>4} | {r['step_count']:>5} | "
            f"{r['t_total_ms']:>11.2f} | {r['t_llm_ms']:>10.2f} | {r['t_db_ms']:>9.2f} | "
            f"{r['export_syntax']:<14} | {r['prov_status']:<8}"
        )
        for err in r["errors"]:
            print(f"   └── [ERROR] {err}")

    print("-" * width)

    lat = summary["latency_ms"]
    steps = summary["steps"]
    tok = summary["tokens"]

    print("\nDECOMPOSED LATENCY AGGREGATION (T_LLM vs T_DB):")
    print(
        f"  Average T_Total : {lat['avg_t_total_ms']:>10.2f} ms   (Cumulative: {lat['sum_t_total_ms']:.2f} ms)"
    )
    print(
        f"  Average T_LLM   : {lat['avg_t_llm_ms']:>10.2f} ms   ({lat['llm_share_pct']:>5.2f}% of total runtime)"
    )
    print(
        f"  Average T_DB    : {lat['avg_t_db_ms']:>10.2f} ms   ({lat['db_share_pct']:>5.2f}% of total runtime)"
    )
    print(
        f"  Average T_Other : {lat['avg_t_other_ms']:>10.2f} ms   ({lat['other_share_pct']:>5.2f}% sandbox/IO overhead)"
    )
    if lat["llm_to_db_ratio"] is not None:
        print(f"  T_LLM / T_DB    : {lat['llm_to_db_ratio']}x")

    print("\nCOGNITIVE TRAJECTORY & EXPORT TOOL METRICS:")
    print(
        f"  ReAct Steps     : avg={steps['avg_steps']:.2f}, median={steps['median_steps']:.2f}, "
        f"min={steps['min_steps']}, max={steps['max_steps']}, total={steps['total_steps']}"
    )
    print(
        f"  Token Usage     : total={tok['total_tokens']} "
        f"(prompt={tok['total_prompt_tokens']}, completion={tok['total_completion_tokens']}, "
        f"avg/task={tok['avg_tokens_per_task']})"
    )
    print(f"  Export Syntax   : {json.dumps(summary['export_syntax_counts'])}")

    print("\nAKÔFLOW /provenance/ REST API VERIFICATION:")
    print(f"  Status          : {api_report['status']}")
    if api_report.get("endpoint"):
        print(f"  Endpoint        : {api_report['endpoint']}")
    print(f"  Details         : {api_report['message']}")
    print("=" * width + "\n")


# =============================================================================
# CLI Entrypoint
# =============================================================================
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify AkôFlow benchmark output artifacts, W3C PROV records, and decomposed latencies."
    )
    parser.add_argument(
        "--results_dir",
        "--result_dir",
        dest="results_dir",
        type=str,
        required=True,
        help="Path to the shared output directory containing task folders (e.g. 'output/test_phase2').",
    )
    parser.add_argument(
        "--expected_tasks",
        "--instances",
        dest="expected_tasks",
        type=str,
        default="auto",
        help="Expected tasks: comma-separated indices/IDs (e.g. '0,1,2'), range ('0-5'), 'all' (69 tasks), or 'auto'.",
    )
    parser.add_argument(
        "--akoflow_api_url",
        type=str,
        default=os.environ.get("AKOFLOW_API_URL", None),
        help="Optional base URL of the AkôFlow server to query `/provenance/` REST API.",
    )
    parser.add_argument(
        "--workflow_name",
        type=str,
        default=None,
        help="Optional workflow name filter for `/provenance/` API query.",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="escience-jabuti",
        help="AkôFlow namespace (default: 'escience-jabuti').",
    )
    parser.add_argument(
        "--skip_api",
        action="store_true",
        default=False,
        help="Explicitly skip querying AkôFlow `/provenance/` REST API even if AKOFLOW_API_URL is set.",
    )
    parser.add_argument(
        "--require_api",
        action="store_true",
        default=False,
        help="Fail verification (exit 1) if the AkôFlow `/provenance/` REST API is not verified.",
    )
    parser.add_argument(
        "--allow_non_zero_exit",
        action="store_true",
        default=False,
        help="Allow tasks with non-zero exit_code to pass structural provenance verification.",
    )
    parser.add_argument(
        "--output_json",
        type=str,
        default=None,
        help="Optional file path to save the full verification report as JSON.",
    )
    return parser.parse_args(argv)


def run_verification(args: argparse.Namespace) -> Tuple[int, Dict[str, Any]]:
    """
    Executes the full verification workflow and returns `(exit_code, report_dict)`.
    """
    if not os.path.isdir(args.results_dir):
        raise FileNotFoundError(
            f"Results directory does not exist: '{args.results_dir}'"
        )

    expected_task_ids = parse_expected_tasks(args.expected_tasks, args.results_dir)

    task_reports: List[Dict[str, Any]] = []
    for task_id in expected_task_ids:
        task_dir = locate_task_dir(args.results_dir, task_id)
        report = verify_single_task_directory(
            task_id=task_id,
            task_dir=task_dir,
            allow_non_zero_exit=args.allow_non_zero_exit,
        )
        task_reports.append(report)

    summary = aggregate_telemetry(task_reports)

    effective_api_url = None if args.skip_api else args.akoflow_api_url
    api_report = verify_akoflow_provenance_api(
        api_url=effective_api_url,
        expected_task_ids=expected_task_ids,
        workflow_name=args.workflow_name,
        namespace=args.namespace,
    )

    print_verification_summary(
        results_dir=args.results_dir,
        task_reports=task_reports,
        summary=summary,
        api_report=api_report,
    )

    all_tasks_valid = summary["failed_verification_count"] == 0
    api_ok = True
    if args.require_api and api_report["status"] != "VERIFIED":
        api_ok = False
    elif effective_api_url and api_report["status"] in ("ERROR", "PARTIAL"):
        api_ok = False

    exit_code = 0 if (all_tasks_valid and api_ok) else 1

    full_report = {
        "results_dir": os.path.abspath(args.results_dir),
        "expected_tasks": expected_task_ids,
        "all_tasks_valid": all_tasks_valid,
        "exit_code": exit_code,
        "summary": summary,
        "akoflow_provenance_api": api_report,
        "tasks": task_reports,
    }

    if args.output_json:
        out_path = os.path.abspath(args.output_json)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)

    return exit_code, full_report


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = parse_args(argv)
        exit_code, _ = run_verification(args)
        return exit_code
    except Exception as exc:
        print(f"ERROR: Verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

