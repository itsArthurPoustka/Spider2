#!/usr/bin/env python3
"""
ingest_provenance_sqlite.py — Ingest W3C PROV-JSON & ReAct Traces into SQLite
=============================================================================

PURPOSE:
--------
Scans benchmark run outputs, parses:
  1. `task_provenance.json` (W3C PROV-JSON scientific lineage graph)
  2. `metrics.json` (Decomposed latencies, tokens, export tool syntax)
  3. `evaluation_report.json` (Ground truth evaluation scores)
  4. `spider/result.json` (Step-by-step ReAct thought/action/observation trajectory)

And ingests them into a self-contained, queryable SQLite database (`provenance.db`).

KEY FEATURES:
-------------
- Self-contained: Built entirely with Python's standard `sqlite3` and `json`.
- Multi-run capable: Stores a `run_id` on all tables, so multiple models
  (e.g., Qwen, Mistral, DeepSeek) can be queried and compared in a single database.
- Rich views: Includes pre-configured SQL views for:
    * `v_persona_summary`
    * `v_difficulty_summary`
    * `v_sql_actions` (all executed SQL commands)
    * `v_failed_tasks`
- CLI interactive query mode: `--query "SELECT ..."` runs instant SQL queries.

USAGE:
------
  # Ingest a specific run into output/.../provenance.db:
  python ingest_provenance_sqlite.py --results_dir output/qwen2.5-coder_32b-full-run

  # Ingest into a shared database and run a summary query:
  python ingest_provenance_sqlite.py \\
      --results_dir output/qwen2.5-coder_32b-full-run \\
      --db_path output/benchmark_provenance.db \\
      --query "SELECT persona, COUNT(*), ROUND(AVG(is_correct)*100, 1) AS acc_pct FROM task_provenance GROUP BY persona;"
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def init_database(conn: sqlite3.Connection) -> None:
    """Initializes tables, indexes, and analytical views in SQLite."""
    cur = conn.cursor()

    # 1. Runs Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        model TEXT,
        provider TEXT,
        total_tasks INTEGER DEFAULT 0,
        correct_tasks INTEGER DEFAULT 0,
        accuracy REAL DEFAULT 0.0,
        total_duration_sec REAL DEFAULT 0.0,
        avg_llm_sec REAL DEFAULT 0.0,
        avg_db_sec REAL DEFAULT 0.0,
        created_at TEXT
    );
    """)

    # 2. Task Provenance Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS task_provenance (
        run_id TEXT,
        task_id TEXT,
        persona TEXT,
        difficulty TEXT,
        parent_group TEXT,
        question TEXT,
        prompt_hash TEXT,
        model TEXT,
        model_digest TEXT,
        provider TEXT,
        schema_sha256 TEXT,
        container_name TEXT,
        exit_code INTEGER,
        status TEXT,
        step_count INTEGER,
        t_total_ms REAL,
        t_llm_ms REAL,
        t_db_ms REAL,
        t_other_ms REAL,
        tokens_prompt INTEGER,
        tokens_completion INTEGER,
        tokens_total INTEGER,
        export_syntax TEXT,
        csv_sha256 TEXT,
        pred_rows INTEGER,
        gold_rows INTEGER,
        is_correct INTEGER,
        error_info TEXT,
        start_time TEXT,
        end_time TEXT,
        raw_prov_json TEXT,
        PRIMARY KEY (run_id, task_id),
        FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
    );
    """)

    # 3. Task Steps Table (Granular ReAct cognitive trace)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS task_steps (
        run_id TEXT,
        task_id TEXT,
        step_number INTEGER,
        thought TEXT,
        action TEXT,
        action_type TEXT,
        sql_query TEXT,
        observation TEXT,
        PRIMARY KEY (run_id, task_id, step_number),
        FOREIGN KEY (run_id, task_id) REFERENCES task_provenance (run_id, task_id) ON DELETE CASCADE
    );
    """)

    # Create Indexes for fast querying
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_prov_run_task ON task_provenance (run_id, task_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_prov_persona ON task_provenance (persona);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_prov_diff ON task_provenance (difficulty);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_prov_correct ON task_provenance (is_correct);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_steps_action ON task_steps (action_type);")

    # Analytical Views for Researchers
    cur.execute("""
    CREATE VIEW IF NOT EXISTS v_persona_summary AS
    SELECT 
        run_id,
        persona,
        COUNT(*) AS total_tasks,
        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_tasks,
        ROUND(AVG(is_correct) * 100, 2) AS accuracy_pct,
        ROUND(AVG(t_llm_ms) / 1000.0, 2) AS avg_llm_sec,
        ROUND(AVG(t_db_ms) / 1000.0, 3) AS avg_db_sec,
        ROUND(AVG(step_count), 2) AS avg_steps,
        SUM(tokens_total) AS total_tokens
    FROM task_provenance
    GROUP BY run_id, persona;
    """)

    cur.execute("""
    CREATE VIEW IF NOT EXISTS v_difficulty_summary AS
    SELECT 
        run_id,
        difficulty,
        COUNT(*) AS total_tasks,
        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_tasks,
        ROUND(AVG(is_correct) * 100, 2) AS accuracy_pct,
        ROUND(AVG(t_llm_ms) / 1000.0, 2) AS avg_llm_sec,
        ROUND(AVG(step_count), 2) AS avg_steps
    FROM task_provenance
    GROUP BY run_id, difficulty;
    """)

    cur.execute("""
    CREATE VIEW IF NOT EXISTS v_sql_actions AS
    SELECT 
        run_id,
        task_id,
        step_number,
        thought,
        sql_query,
        action
    FROM task_steps
    WHERE sql_query IS NOT NULL AND sql_query != '';
    """)

    conn.commit()


def extract_sql_from_action(action_str: str) -> Optional[str]:
    """Extracts SQL command if action is Bash running psql."""
    if not action_str or "psql" not in action_str:
        return None
    # Handle escaped quotes (e.g. \"...\" in JSON) as well as unescaped ("..." or '...')
    m_esc = re.search(r'-c\s*\\([\"\'])(.*?)\\\1', action_str, re.DOTALL)
    if m_esc:
        return m_esc.group(2).strip()
    m = re.search(r'-c\s*([\"\'])(.*?)\1', action_str, re.DOTALL)
    if m:
        return m.group(2).strip()
    return None


def parse_evaluation_report(eval_path: str) -> Dict[str, Dict[str, Any]]:
    """Loads per_task_results from evaluation_report.json."""
    if not os.path.isfile(eval_path):
        return {}
    try:
        with open(eval_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = {}
        for item in data.get("per_task_results", []):
            iid = item.get("instance_id")
            if iid:
                results[iid] = {
                    "score": item.get("score", 0),
                    "error_info": item.get("error_info"),
                    "pred_rows": item.get("pred_rows"),
                    "gold_rows": item.get("gold_rows"),
                }
        return results
    except Exception as e:
        print(f"[WARN] Failed to parse evaluation report {eval_path}: {e}", file=sys.stderr)
        return {}


def ingest_run(
    results_dir: str,
    db_path: str,
    run_id: Optional[str] = None,
    eval_json_path: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Ingests all task records from results_dir into db_path SQLite database.
    Returns (tasks_ingested, steps_ingested).
    """
    results_dir = os.path.abspath(results_dir)
    if not os.path.isdir(results_dir):
        raise ValueError(f"Results directory does not exist: {results_dir}")

    resolved_run_id = run_id or os.path.basename(results_dir.rstrip("/"))

    # Check for evaluation report
    if not eval_json_path:
        candidate_eval = os.path.join(results_dir, "evaluation_report.json")
        eval_json_path = candidate_eval if os.path.isfile(candidate_eval) else None

    eval_scores = parse_evaluation_report(eval_json_path) if eval_json_path else {}

    # Discover task folders
    task_dirs = sorted([
        d for d in glob.glob(os.path.join(results_dir, "local_jabuti_*"))
        if os.path.isdir(d)
    ])
    if not task_dirs:
        raise ValueError(f"No 'local_jabuti_*' task directories found under {results_dir}")

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    init_database(conn)
    cur = conn.cursor()

    run_model = None
    run_provider = None
    total_duration_ms = 0.0
    total_llm_ms = 0.0
    total_db_ms = 0.0
    total_correct = 0
    tasks_count = 0
    total_steps_ingested = 0

    print(f"[INFO] Ingesting run '{resolved_run_id}' ({len(task_dirs)} tasks) into {db_path}...")

    for tdir in task_dirs:
        tid = os.path.basename(tdir)
        prov_file = os.path.join(tdir, "task_provenance.json")
        metrics_file = os.path.join(tdir, "metrics.json")
        spider_res_file = os.path.join(tdir, "spider", "result.json")

        prov_data = {}
        if os.path.isfile(prov_file):
            try:
                with open(prov_file, "r", encoding="utf-8") as pf:
                    prov_data = json.load(pf)
            except Exception as e:
                print(f"[WARN] Failed to parse {prov_file}: {e}", file=sys.stderr)

        metrics_data = {}
        if os.path.isfile(metrics_file):
            try:
                with open(metrics_file, "r", encoding="utf-8") as mf:
                    metrics_data = json.load(mf)
            except Exception as e:
                print(f"[WARN] Failed to parse {metrics_file}: {e}", file=sys.stderr)

        spider_data = {}
        if os.path.isfile(spider_res_file):
            try:
                with open(spider_res_file, "r", encoding="utf-8") as sf:
                    spider_data = json.load(sf)
            except Exception as e:
                print(f"[WARN] Failed to parse {spider_res_file}: {e}", file=sys.stderr)

        # Extract Fields from W3C PROV entities
        entities = prov_data.get("entity", {})
        task_spec = {}
        db_state = {}
        model_ver = {}
        pred_out = {}
        metrics_ent = {}
        container_ent = {}

        for k, v in entities.items():
            ptype = v.get("prov:type")
            if ptype == "jabuti:TaskSpec":
                task_spec = v
            elif ptype == "jabuti:DatabaseState":
                db_state = v
            elif ptype == "jabuti:ModelVersion":
                model_ver = v
            elif ptype == "jabuti:PredictionOutput":
                pred_out = v
            elif ptype == "jabuti:Metrics":
                metrics_ent = v
            elif ptype == "jabuti:DockerContainer":
                container_ent = v

        persona = task_spec.get("jabuti:persona")
        difficulty = task_spec.get("jabuti:difficulty")
        parent_group = task_spec.get("jabuti:parent_group")
        question = task_spec.get("jabuti:question")
        prompt_hash = task_spec.get("jabuti:prompt_hash")

        model = model_ver.get("jabuti:model_id") or metrics_data.get("model", "unknown")
        if not run_model and model:
            run_model = model
        model_digest = model_ver.get("jabuti:digest")
        provider = model_ver.get("jabuti:provider") or metrics_data.get("provider", "unknown")
        if not run_provider and provider:
            run_provider = provider

        schema_sha256 = db_state.get("jabuti:schema_sha256")
        container_name = container_ent.get("jabuti:container_name")

        exit_code = metrics_ent.get("jabuti:exit_code", metrics_data.get("exit_code", 0))
        status = "SUCCESS" if exit_code == 0 else "ERROR"
        step_count = metrics_ent.get("jabuti:step_count", metrics_data.get("step_count", 0))

        t_tot = float(metrics_ent.get("jabuti:t_total_ms", metrics_data.get("t_total_ms", 0.0)))
        t_llm = float(metrics_ent.get("jabuti:t_llm_ms", metrics_data.get("t_llm_ms", 0.0)))
        t_db = float(metrics_ent.get("jabuti:t_db_ms", metrics_data.get("t_db_ms", 0.0)))
        t_other = max(0.0, round(t_tot - t_llm - t_db, 2))

        total_duration_ms += t_tot
        total_llm_ms += t_llm
        total_db_ms += t_db

        tokens_p = metrics_ent.get("jabuti:tokens_prompt", metrics_data.get("tokens_prompt", 0))
        tokens_c = metrics_ent.get("jabuti:tokens_completion", metrics_data.get("tokens_completion", 0))
        tokens_t = metrics_ent.get("jabuti:tokens_total", metrics_data.get("tokens_total", 0))

        export_syntax = pred_out.get("jabuti:export_syntax", metrics_data.get("export_syntax", "NONE"))
        csv_sha256 = pred_out.get("jabuti:file_sha256", metrics_data.get("csv_sha256"))

        # Evaluation data
        eval_item = eval_scores.get(tid, {})
        is_correct = eval_item.get("score")
        if is_correct == 1:
            total_correct += 1
        pred_rows = eval_item.get("pred_rows", pred_out.get("jabuti:row_count"))
        gold_rows = eval_item.get("gold_rows")
        error_info = eval_item.get("error_info") or metrics_data.get("error")

        # Activities
        activity_ent = {}
        for ak, av in prov_data.get("activity", {}).items():
            if av.get("prov:type") == "jabuti:TaskExecution":
                activity_ent = av
                break
        start_time = activity_ent.get("prov:startTime", metrics_data.get("start_time"))
        end_time = activity_ent.get("prov:endTime", metrics_data.get("end_time"))

        cur.execute("""
        INSERT OR REPLACE INTO task_provenance (
            run_id, task_id, persona, difficulty, parent_group, question,
            prompt_hash, model, model_digest, provider, schema_sha256,
            container_name, exit_code, status, step_count, t_total_ms,
            t_llm_ms, t_db_ms, t_other_ms, tokens_prompt, tokens_completion,
            tokens_total, export_syntax, csv_sha256, pred_rows, gold_rows,
            is_correct, error_info, start_time, end_time, raw_prov_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """, (
            resolved_run_id, tid, persona, difficulty, parent_group, question,
            prompt_hash, model, model_digest, provider, schema_sha256,
            container_name, exit_code, status, step_count, t_tot,
            t_llm, t_db, t_other, tokens_p, tokens_c,
            tokens_t, export_syntax, csv_sha256, pred_rows, gold_rows,
            is_correct, error_info, start_time, end_time,
            json.dumps(prov_data) if prov_data else None,
        ))

        # Ingest Steps from spider/result.json if present
        trajectory = spider_data.get("trajectory", [])
        for step_idx, step in enumerate(trajectory, start=1):
            thought = step.get("thought", "")
            action = step.get("action", "")
            obs = step.get("observation", "")
            action_type = action.split("(")[0].strip() if action else "Unknown"
            sql_query = extract_sql_from_action(action)

            cur.execute("""
            INSERT OR REPLACE INTO task_steps (
                run_id, task_id, step_number, thought, action, action_type, sql_query, observation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                resolved_run_id, tid, step_idx, thought, action, action_type, sql_query, obs
            ))
            total_steps_ingested += 1

        tasks_count += 1

    # Insert or replace top-level Run record
    accuracy = round(total_correct / tasks_count, 4) if tasks_count > 0 else 0.0
    avg_llm_sec = round((total_llm_ms / tasks_count) / 1000.0, 2) if tasks_count > 0 else 0.0
    avg_db_sec = round((total_db_ms / tasks_count) / 1000.0, 3) if tasks_count > 0 else 0.0
    tot_sec = round(total_duration_ms / 1000.0, 1)

    cur.execute("""
    INSERT OR REPLACE INTO runs (
        run_id, model, provider, total_tasks, correct_tasks, accuracy,
        total_duration_sec, avg_llm_sec, avg_db_sec, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        resolved_run_id, run_model, run_provider, tasks_count, total_correct, accuracy,
        tot_sec, avg_llm_sec, avg_db_sec, datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()

    print(f"[SUCCESS] Ingested {tasks_count} tasks and {total_steps_ingested} ReAct steps into '{db_path}'.")
    return tasks_count, total_steps_ingested


def execute_interactive_query(db_path: str, sql_query: str) -> None:
    """Runs a SQL query against the database and prints formatted table."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(sql_query)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []

        print("\n" + "=" * 80)
        print(f"QUERY: {sql_query}")
        print("=" * 80)
        if not rows:
            print("(0 rows returned)")
            return

        # Simple ascii table
        col_widths = [max(len(str(c)), max(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
        header = " | ".join(f"{cols[i]:<{col_widths[i]}}" for i in range(len(cols)))
        sep = "-+-".join("-" * col_widths[i] for i in range(len(cols)))
        print(header)
        print(sep)
        for r in rows:
            row_str = " | ".join(f"{str(r[i]):<{col_widths[i]}}" for i in range(len(r)))
            print(row_str)
        print(f"({len(rows)} rows)\n")
    except Exception as e:
        print(f"[ERROR] Query failed: {e}", file=sys.stderr)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest W3C PROV-JSON & ReAct Traces into SQLite"
    )
    parser.add_argument(
        "--results_dir",
        "-r",
        type=str,
        required=True,
        help="Path to results directory containing task folders (e.g. output/qwen2.5-coder_32b-full-run)",
    )
    parser.add_argument(
        "--db_path",
        "-d",
        type=str,
        default=None,
        help="Path to target SQLite database (default: <results_dir>/provenance.db)",
    )
    parser.add_argument(
        "--run_id",
        type=str,
        default=None,
        help="Identifier for this run (default: basename of results_dir)",
    )
    parser.add_argument(
        "--evaluation_json",
        "-e",
        type=str,
        default=None,
        help="Path to evaluation_report.json (default: <results_dir>/evaluation_report.json)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help="Optional SQL query to execute immediately after ingestion",
    )

    args = parser.parse_args()
    db_path = args.db_path or os.path.join(args.results_dir, "provenance.db")

    ingest_run(
        results_dir=args.results_dir,
        db_path=db_path,
        run_id=args.run_id,
        eval_json_path=args.evaluation_json,
    )

    if args.query:
        execute_interactive_query(db_path, args.query)
    else:
        # Run a default analytical preview
        default_query = """
        SELECT 
            persona,
            COUNT(*) AS tasks,
            SUM(is_correct) AS correct,
            ROUND(AVG(is_correct)*100, 1) || '%' AS accuracy,
            ROUND(AVG(t_llm_ms)/1000.0, 1) AS avg_llm_sec,
            ROUND(AVG(step_count), 1) AS avg_steps
        FROM task_provenance
        GROUP BY persona;
        """
        execute_interactive_query(db_path, default_query)


if __name__ == "__main__":
    main()
