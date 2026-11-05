#!/usr/bin/env python3
"""
generate_akoflow_workflow.py — AkôFlow Workflow DAG Generator for JABUTI-SQL
=============================================================================

Reads the JABUTI-SQL benchmark tasks from `examples/jabuti.jsonl` and generates
a clean, valid AkôFlow workflow specification YAML file modeling the benchmark
sweep as a parallel fan-out / fan-in DAG:

    preflight-check
          │
          ├──► task-local_jabuti_000 ──┐
          ├──► task-local_jabuti_001 ──┤
          │            ...             ├──► evaluation
          └──► task-local_jabuti_068 ──┘

Usage:
    # Full 69-task benchmark workflow:
    python methods/spider-agent-jabuti/generate_akoflow_workflow.py \
        --model qwen2.5-coder:32b \
        --instances all \
        --output_yaml methods/spider-agent-jabuti/akoflow/workflow_jabuti.yaml

    # 3-instance smoke test workflow:
    python methods/spider-agent-jabuti/generate_akoflow_workflow.py \
        --model qwen2.5-coder:32b \
        --instances 0,1,2 \
        --output_yaml akoflow/workflow_smoke.yaml
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_YAML = os.path.join(SCRIPT_DIR, "akoflow", "workflow_jabuti.yaml")


def sanitize_model_name(model: str) -> str:
    """
    Sanitizes an LLM model identifier into a valid AkôFlow workflow name suffix.
    Example: 'qwen2.5-coder:32b' -> 'qwen2.5-coder-32b'
    """
    base = str(model).strip().split("/")[-1]
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "-", base)
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-._")
    return cleaned or "default-model"


def resolve_jsonl_path(jsonl_path: str) -> str:
    """
    Resolves the path to `examples/jabuti.jsonl` whether invoked from the
    repository root or from `methods/spider-agent-jabuti/`.
    """
    candidates = [
        jsonl_path,
        os.path.join(SCRIPT_DIR, jsonl_path),
        os.path.join(SCRIPT_DIR, "examples", os.path.basename(jsonl_path)),
        os.path.join(
            os.getcwd(), "methods", "spider-agent-jabuti", jsonl_path.lstrip("./")
        ),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise FileNotFoundError(
        f"Could not find JABUTI benchmark JSONL file at '{jsonl_path}'. "
        f"Searched: {candidates}"
    )


def load_jabuti_tasks(jsonl_path: str) -> List[Dict[str, Any]]:
    """Loads all task records from `jabuti.jsonl`."""
    resolved_path = resolve_jsonl_path(jsonl_path)
    tasks: List[Dict[str, Any]] = []
    with open(resolved_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON on line {line_num} of '{resolved_path}': {exc}"
                ) from exc
            instance_id = record.get("instance_id") or record.get("id")
            if not instance_id:
                raise ValueError(
                    f"Missing 'instance_id' on line {line_num} of '{resolved_path}'"
                )
            tasks.append(record)
    return tasks


def filter_tasks(
    tasks: List[Dict[str, Any]], instances_spec: str
) -> List[Dict[str, Any]]:
    """
    Filters the task list according to `--instances`:
      - 'all': returns all tasks in order.
      - Comma-separated indices or IDs (e.g. '0,1,2', '0-5', 'local_jabuti_000'):
        returns the matching tasks in the requested order without duplicates.
    """
    if instances_spec is None:
        return list(tasks)
    spec = str(instances_spec).strip()
    if spec.lower() == "all":
        return list(tasks)
    if not spec:
        raise ValueError("Empty --instances specification; use 'all' or a comma-separated list of instances")

    by_id: Dict[str, Dict[str, Any]] = {
        str(t.get("instance_id") or t.get("id")): t for t in tasks
    }

    selected: List[Dict[str, Any]] = []
    seen_ids = set()

    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue

        # Handle numeric range like "0-5"
        range_match = re.match(r"^(\d+)-(\d+)$", part)
        if range_match:
            start_idx = int(range_match.group(1))
            end_idx = int(range_match.group(2))
            if start_idx > end_idx:
                raise ValueError(f"Invalid instance range '{part}' (start > end)")
            indices = list(range(start_idx, end_idx + 1))
            for idx in indices:
                candidate_id = f"local_jabuti_{idx:03d}"
                if candidate_id in by_id:
                    task = by_id[candidate_id]
                elif 0 <= idx < len(tasks):
                    task = tasks[idx]
                else:
                    raise ValueError(
                        f"Instance index {idx} out of range (total tasks: {len(tasks)})"
                    )
                tid = str(task.get("instance_id") or task.get("id"))
                if tid not in seen_ids:
                    selected.append(task)
                    seen_ids.add(tid)
            continue

        # Handle single integer index like "0", "1", "2"
        if part.isdigit():
            idx = int(part)
            candidate_id = f"local_jabuti_{idx:03d}"
            if candidate_id in by_id:
                task = by_id[candidate_id]
            elif 0 <= idx < len(tasks):
                task = tasks[idx]
            else:
                raise ValueError(
                    f"Instance index {idx} not found in benchmark (total tasks: {len(tasks)})"
                )
            tid = str(task.get("instance_id") or task.get("id"))
            if tid not in seen_ids:
                selected.append(task)
                seen_ids.add(tid)
            continue

        # Handle explicit instance_id like "local_jabuti_000" or "task-local_jabuti_000"
        normalized_id = part[len("task-") :] if part.startswith("task-") else part
        if normalized_id not in by_id:
            raise ValueError(
                f"Task instance '{part}' not found in benchmark JSONL"
            )
        if normalized_id not in seen_ids:
            selected.append(by_id[normalized_id])
            seen_ids.add(normalized_id)

    if not selected:
        raise ValueError(f"No tasks matched --instances='{instances_spec}'")

    return selected


def build_workflow_dict(
    tasks: List[Dict[str, Any]],
    model: str = "qwen2.5-coder:32b",
    namespace: str = "escience-jabuti",
    image: str = "spider-agent-runner:latest",
    cpu_limit: str = "1",
    memory_limit: str = "2Gi",
    shared_output_root: str = "/shared/output",
) -> Dict[str, Any]:
    """
    Constructs the AkôFlow workflow dictionary conforming to the AkôFlow
    Workflow schema (`name`, `spec.namespace`, `spec.image`, `spec.activities`).
    """
    model_name_slug = sanitize_model_name(model)
    workflow_name = f"jabuti-sql-benchmark-{model_name_slug}"
    output_base = f"{shared_output_root.rstrip('/')}/{model}"

    activities: List[Dict[str, Any]] = []

    # Activity 0: preflight-check (verifies PostgreSQL connectivity and LLM endpoint availability)
    preflight_cmd = (
        "pg_isready -h ${JABUTI_PG_HOST:-jabuti-postgres} -p ${JABUTI_PG_PORT:-5432} "
        "-U postgres -d jabuti_sql && "
        "curl -sf ${LLM_BASE_URL:-http://localhost:11434/v1}/models > /dev/null"
    )
    activities.append(
        {
            "name": "preflight-check",
            "cpuLimit": str(cpu_limit),
            "memoryLimit": str(memory_limit),
            "run": preflight_cmd,
        }
    )

    # Activities 1..N: Fan-out of benchmark task instances
    task_activity_names: List[str] = []
    for task in tasks:
        task_id = str(task.get("instance_id") or task.get("id"))
        activity_name = f"task-{task_id}"
        task_activity_names.append(activity_name)

        task_run_cmd = (
            f"python run_single_task.py "
            f"--task_id {task_id} "
            f"--model {model} "
            f"--output_dir {output_base}/{task_id}"
        )
        activities.append(
            {
                "name": activity_name,
                "dependsOn": ["preflight-check"],
                "cpuLimit": str(cpu_limit),
                "memoryLimit": str(memory_limit),
                "run": task_run_cmd,
            }
        )

    # Final Activity: evaluation (fan-in across all task activities)
    eval_run_cmd = (
        f"python evaluate_jabuti.py "
        f"--result_dir {output_base} "
        f"--gold_dir evaluation/gold "
        f"--jabuti_jsonl examples/jabuti.jsonl"
    )
    activities.append(
        {
            "name": "evaluation",
            "dependsOn": list(task_activity_names),
            "cpuLimit": str(cpu_limit),
            "memoryLimit": str(memory_limit),
            "run": eval_run_cmd,
        }
    )

    return {
        "name": workflow_name,
        "spec": {
            "namespace": namespace,
            "image": image,
            "activities": activities,
        },
    }


def _yaml_scalar(value: str, force_quote: bool = False) -> str:
    """Formats a scalar string safely for YAML 1.2 serialization."""
    s = str(value)
    needs_quotes = (
        force_quote
        or s == ""
        or s.isdigit()
        or s.lower() in {"true", "false", "null", "yes", "no", "on", "off", "~"}
        or any(ch in s for ch in [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "'", '"', "%", "@", "`"])
        or s != s.strip()
    )
    if needs_quotes:
        escaped = (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    return s


def dump_workflow_yaml(workflow: Dict[str, Any]) -> str:
    """
    Serializes the AkôFlow workflow dictionary into a clean, deterministic
    YAML 1.2 document. Explicitly quotes resource limit strings (e.g. "1", "2Gi")
    so strict YAML/JSON decoders preserve string types.
    """
    spec = workflow["spec"]
    lines: List[str] = [
        f"name: {_yaml_scalar(workflow['name'])}",
        "spec:",
        f"  namespace: {_yaml_scalar(spec['namespace'])}",
        f"  image: {_yaml_scalar(spec['image'])}",
        "  activities:",
    ]

    for activity in spec["activities"]:
        lines.append(f"    - name: {_yaml_scalar(activity['name'])}")
        if "dependsOn" in activity and activity["dependsOn"]:
            deps = activity["dependsOn"]
            if len(deps) == 1:
                lines.append(f"      dependsOn: [{_yaml_scalar(deps[0])}]")
            else:
                lines.append("      dependsOn:")
                for dep in deps:
                    lines.append(f"        - {_yaml_scalar(dep)}")
        if "cpuLimit" in activity:
            lines.append(
                f"      cpuLimit: {_yaml_scalar(activity['cpuLimit'], force_quote=True)}"
            )
        if "memoryLimit" in activity:
            lines.append(
                f"      memoryLimit: {_yaml_scalar(activity['memoryLimit'], force_quote=True)}"
            )
        if "run" in activity:
            lines.append(f"      run: {_yaml_scalar(activity['run'])}")

    return "\n".join(lines) + "\n"


def generate_workflow_file(
    model: str = "qwen2.5-coder:32b",
    instances: str = "all",
    output_yaml: str = DEFAULT_OUTPUT_YAML,
    jabuti_jsonl: str = "examples/jabuti.jsonl",
    namespace: str = "escience-jabuti",
    image: str = "spider-agent-runner:latest",
    cpu_limit: str = "1",
    memory_limit: str = "2Gi",
    shared_output_root: str = "/shared/output",
) -> Dict[str, Any]:
    """
    Loads tasks from `jabuti.jsonl`, filters by `instances`, builds the AkôFlow
    workflow definition, and writes the YAML file to `output_yaml`.
    """
    all_tasks = load_jabuti_tasks(jabuti_jsonl)
    selected_tasks = filter_tasks(all_tasks, instances)

    workflow = build_workflow_dict(
        tasks=selected_tasks,
        model=model,
        namespace=namespace,
        image=image,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        shared_output_root=shared_output_root,
    )

    yaml_content = dump_workflow_yaml(workflow)

    output_path = os.path.abspath(output_yaml)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    return workflow


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an AkôFlow workflow YAML specification for the JABUTI-SQL benchmark."
    )
    parser.add_argument(
        "--model",
        type=str,
        default="qwen2.5-coder:32b",
        help="Target LLM model name (default: qwen2.5-coder:32b).",
    )
    parser.add_argument(
        "--instances",
        type=str,
        default="all",
        help="Filter subset of instances (e.g. '0,1,2' for smoke test or 'all' for full suite).",
    )
    parser.add_argument(
        "--output_yaml",
        type=str,
        default=DEFAULT_OUTPUT_YAML,
        help="Destination path for generated AkôFlow YAML file.",
    )
    parser.add_argument(
        "--jabuti_jsonl",
        type=str,
        default="examples/jabuti.jsonl",
        help="Path to examples/jabuti.jsonl (default: examples/jabuti.jsonl).",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="escience-jabuti",
        help="AkôFlow workflow namespace (default: escience-jabuti).",
    )
    parser.add_argument(
        "--image",
        type=str,
        default="spider-agent-runner:latest",
        help="Base container image for runner activities (default: spider-agent-runner:latest).",
    )
    parser.add_argument(
        "--cpu_limit",
        type=str,
        default="1",
        help="CPU limit per task activity (default: '1').",
    )
    parser.add_argument(
        "--memory_limit",
        type=str,
        default="2Gi",
        help="Memory limit per task activity (default: '2Gi').",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        workflow = generate_workflow_file(
            model=args.model,
            instances=args.instances,
            output_yaml=args.output_yaml,
            jabuti_jsonl=args.jabuti_jsonl,
            namespace=args.namespace,
            image=args.image,
            cpu_limit=args.cpu_limit,
            memory_limit=args.memory_limit,
        )
    except Exception as exc:
        print(f"ERROR: Failed to generate AkôFlow workflow YAML: {exc}", file=sys.stderr)
        return 1

    total_activities = len(workflow["spec"]["activities"])
    task_count = total_activities - 2
    print(
        f"Generated AkôFlow workflow '{workflow['name']}' "
        f"({task_count} task activities, {total_activities} total activities) -> {args.output_yaml}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

