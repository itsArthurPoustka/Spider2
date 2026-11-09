#!/usr/bin/env python3
"""
provenance_queries.py — Catalog of Provenance & Telemetry Analytical SQL Queries
================================================================================

PURPOSE:
--------
Provides an organized, executable catalog of research-grade SQL queries for
analyzing the `provenance.db` SQLite database created by `ingest_provenance_sqlite.py`.

Answers essential e-Science questions across 6 core categories:
  1. Benchmark Accuracy & Stratification (Accuracy, Persona, Difficulty, Semantic Consistency)
  2. Decomposed Latency & Telemetry (T_Total, T_LLM, T_DB, T_Other, LLM/DB Ratios)
  3. Cognitive Trajectories & Token Economics (ReAct Steps, Prompt/Completion Tokens)
  4. Tool Adherence & Protocol Compliance (COPY_TO_STDOUT vs PSQL_PLAIN)
  5. Failure Diagnostics & Debugging (Row count mismatches, High step loops)
  6. Scientific Lineage & Cryptographic Integrity (Prompt/Schema/Result SHA256)

MODES OF USE:
-------------
1. As a CLI Tool:
   - List catalog:       python provenance_queries.py --list
   - Run specific query: python provenance_queries.py --run semantic_consistency
   - Run all queries:    python provenance_queries.py --run-all
   - Export to pure SQL: python provenance_queries.py --export-sql provenance_queries.sql

2. As a Python Library:
   from provenance_queries import CATALOG, run_query
   cols, rows = run_query("output/.../provenance.db", "persona_performance")
"""

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Query Catalog Definition
# =============================================================================

CATALOG: Dict[str, Dict[str, str]] = {
    # -------------------------------------------------------------------------
    # 1. Benchmark Accuracy & Stratification
    # -------------------------------------------------------------------------
    "overall_summary": {
        "title": "Overall Benchmark Execution Summary",
        "category": "Accuracy & Stratification",
        "description": "High-level summary of the model, accuracy, task count, and average latencies.",
        "sql": """
SELECT 
    run_id,
    model,
    provider,
    total_tasks,
    correct_tasks,
    ROUND(accuracy * 100, 1) || '%' AS accuracy,
    ROUND(total_duration_sec / 60.0, 1) AS total_minutes,
    avg_llm_sec,
    avg_db_sec
FROM runs;
""".strip(),
    },
    "persona_performance": {
        "title": "Performance Stratified by Persona",
        "category": "Accuracy & Stratification",
        "description": "Measures accuracy, average inference time, and ReAct steps across the three distinct personas.",
        "sql": """
SELECT 
    persona,
    COUNT(*) AS total_tasks,
    SUM(is_correct) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy,
    ROUND(AVG(t_llm_ms) / 1000.0, 1) AS avg_llm_sec,
    ROUND(AVG(t_db_ms) / 1000.0, 3) AS avg_db_sec,
    ROUND(AVG(step_count), 1) AS avg_steps
FROM task_provenance
GROUP BY persona
ORDER BY AVG(is_correct) DESC;
""".strip(),
    },
    "difficulty_breakdown": {
        "title": "Performance Stratified by Difficulty Tier",
        "category": "Accuracy & Stratification",
        "description": "Examines how accuracy and reasoning effort scale across simple, medium, and hard tasks.",
        "sql": """
SELECT 
    difficulty,
    COUNT(*) AS total_tasks,
    SUM(is_correct) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy,
    ROUND(AVG(t_llm_ms) / 1000.0, 1) AS avg_llm_sec,
    ROUND(AVG(step_count), 1) AS avg_steps
FROM task_provenance
GROUP BY difficulty
ORDER BY 
    CASE difficulty 
        WHEN 'simple' THEN 1 
        WHEN 'medium' THEN 2 
        WHEN 'hard' THEN 3 
        ELSE 4 
    END;
""".strip(),
    },
    "semantic_consistency": {
        "title": "Semantic Consistency Across Persona Formulations",
        "category": "Accuracy & Stratification",
        "description": "Checks whether an agent consistently answers all 3 persona phrasings of the same underlying inquiry.",
        "sql": """
SELECT 
    parent_group,
    COUNT(*) AS total_personas,
    SUM(is_correct) AS correct_personas,
    CASE 
        WHEN SUM(is_correct) = 3 THEN 'Fully Consistent (3/3)'
        WHEN SUM(is_correct) > 0 THEN 'Partially Consistent'
        ELSE 'Failed (0/3)'
    END AS consistency_status,
    GROUP_CONCAT(persona || ': ' || CASE WHEN is_correct = 1 THEN '✅' ELSE '❌' END, ' | ') AS persona_details
FROM task_provenance
GROUP BY parent_group
ORDER BY CAST(parent_group AS INTEGER);
""".strip(),
    },
    "semantic_consistency_summary": {
        "title": "Semantic Consistency Aggregate Summary",
        "category": "Accuracy & Stratification",
        "description": "Calculates the overall percentage of inquiry groups that are fully vs partially correct.",
        "sql": """
WITH group_stats AS (
    SELECT 
        parent_group,
        SUM(is_correct) AS correct_count
    FROM task_provenance
    GROUP BY parent_group
)
SELECT 
    COUNT(*) AS total_inquiry_groups,
    SUM(CASE WHEN correct_count = 3 THEN 1 ELSE 0 END) AS fully_consistent_groups,
    ROUND(AVG(CASE WHEN correct_count = 3 THEN 1.0 ELSE 0.0 END) * 100, 1) || '%' AS fully_consistent_pct,
    SUM(CASE WHEN correct_count > 0 THEN 1 ELSE 0 END) AS partially_consistent_groups,
    ROUND(AVG(CASE WHEN correct_count > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) || '%' AS partially_consistent_pct,
    SUM(CASE WHEN correct_count = 0 THEN 1 ELSE 0 END) AS completely_failed_groups
FROM group_stats;
""".strip(),
    },

    # -------------------------------------------------------------------------
    # 2. Decomposed Latency & Telemetry
    # -------------------------------------------------------------------------
    "decomposed_latency_summary": {
        "title": "Decomposed Wall-Clock Latency Breakdown (T_LLM vs T_DB)",
        "category": "Latency & Telemetry",
        "description": "Aggregates total runtime into LLM inference, DB execution, and container/IO overhead.",
        "sql": """
SELECT 
    COUNT(*) AS tasks,
    ROUND(AVG(t_total_ms) / 1000.0, 2) AS avg_total_sec,
    ROUND(AVG(t_llm_ms) / 1000.0, 2) AS avg_llm_sec,
    ROUND(AVG(t_llm_ms) * 100.0 / AVG(t_total_ms), 1) || '%' AS llm_time_pct,
    ROUND(AVG(t_db_ms) / 1000.0, 3) AS avg_db_sec,
    ROUND(AVG(t_db_ms) * 100.0 / AVG(t_total_ms), 1) || '%' AS db_time_pct,
    ROUND(AVG(t_other_ms) / 1000.0, 2) AS avg_other_sec,
    ROUND(AVG(t_llm_ms) / NULLIF(AVG(t_db_ms), 0), 1) || 'x' AS llm_over_db_ratio
FROM task_provenance;
""".strip(),
    },
    "slowest_tasks": {
        "title": "Top 10 Slowest Tasks (Total Wall-Clock Time)",
        "category": "Latency & Telemetry",
        "description": "Identifies tasks with the longest total execution time and decomposes where time was spent.",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    ROUND(t_total_ms / 1000.0, 1) AS total_sec,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    ROUND(t_db_ms / 1000.0, 2) AS db_sec,
    is_correct,
    exit_code
FROM task_provenance
ORDER BY t_total_ms DESC
LIMIT 10;
""".strip(),
    },
    "db_heavy_tasks": {
        "title": "Top 10 Tasks with Highest PostgreSQL Query Latency (T_DB)",
        "category": "Latency & Telemetry",
        "description": "Finds queries that performed heavy database work (e.g. joins over large stock tables).",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    ROUND(t_db_ms / 1000.0, 2) AS db_sec,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    step_count,
    is_correct
FROM task_provenance
ORDER BY t_db_ms DESC
LIMIT 10;
""".strip(),
    },

    # -------------------------------------------------------------------------
    # 3. Cognitive Trajectories & Token Economics
    # -------------------------------------------------------------------------
    "token_consumption_by_persona": {
        "title": "Token Consumption & Economics by Persona",
        "category": "Cognitive & Tokens",
        "description": "Measures total and average prompt/completion tokens consumed per persona.",
        "sql": """
SELECT 
    persona,
    COUNT(*) AS tasks,
    SUM(tokens_total) AS total_tokens,
    ROUND(AVG(tokens_prompt), 0) AS avg_prompt_tokens,
    ROUND(AVG(tokens_completion), 0) AS avg_completion_tokens,
    ROUND(AVG(tokens_total), 0) AS avg_total_tokens
FROM task_provenance
GROUP BY persona
ORDER BY total_tokens DESC;
""".strip(),
    },
    "high_step_tasks": {
        "title": "Tasks with Long Reasoning Loops (Steps >= 8)",
        "category": "Cognitive & Tokens",
        "description": "Lists tasks where the agent required many ReAct iterations to converge or struggle.",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    is_correct,
    exit_code,
    SUBSTR(error_info, 1, 40) AS error_snippet
FROM task_provenance
WHERE step_count >= 8
ORDER BY step_count DESC;
""".strip(),
    },
    "react_action_distribution": {
        "title": "Distribution of Agent Action Types in Steps",
        "category": "Cognitive & Tokens",
        "description": "Counts how many times each action type (Bash, Terminate, etc.) was executed.",
        "sql": """
SELECT 
    action_type,
    COUNT(*) AS total_executions,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM task_steps), 1) || '%' AS percentage
FROM task_steps
GROUP BY action_type
ORDER BY total_executions DESC;
""".strip(),
    },

    # -------------------------------------------------------------------------
    # 4. Tool Adherence & Protocol Compliance
    # -------------------------------------------------------------------------
    "export_syntax_compliance": {
        "title": "SQL Export Syntax Adherence (RFC 4180 Compliance)",
        "category": "Tool Adherence",
        "description": "Checks adherence to recommended COPY (...) TO STDOUT WITH CSV HEADER syntax.",
        "sql": """
SELECT 
    export_syntax,
    COUNT(*) AS task_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM task_provenance), 1) || '%' AS percentage,
    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy
FROM task_provenance
GROUP BY export_syntax
ORDER BY task_count DESC;
""".strip(),
    },
    "non_standard_exports": {
        "title": "Tasks Using Non-Standard Export Methods",
        "category": "Tool Adherence",
        "description": "Lists tasks that fell back to PSQL_PLAIN or failed to export result.csv cleanly.",
        "sql": """
SELECT 
    task_id,
    persona,
    export_syntax,
    is_correct,
    exit_code,
    error_info
FROM task_provenance
WHERE export_syntax != 'COPY_TO_STDOUT';
""".strip(),
    },

    # -------------------------------------------------------------------------
    # 5. Failure Diagnostics & Debugging
    # -------------------------------------------------------------------------
    "failed_tasks_detail": {
        "title": "Detailed Diagnostics on Failed Tasks",
        "category": "Failure Diagnostics",
        "description": "Inspects predicted row count vs gold row count for all incorrect tasks.",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    pred_rows,
    gold_rows,
    exit_code,
    COALESCE(error_info, 'Result value mismatch') AS failure_reason
FROM task_provenance
WHERE is_correct = 0 OR is_correct IS NULL
ORDER BY CAST(SUBSTR(task_id, 14) AS INTEGER);
""".strip(),
    },
    "row_count_mismatches": {
        "title": "Row Count Mismatches (Prediction vs Gold Standard)",
        "category": "Failure Diagnostics",
        "description": "Tasks where the model produced rows, but the number of rows was different from gold.",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    pred_rows,
    gold_rows,
    (pred_rows - gold_rows) AS row_delta
FROM task_provenance
WHERE pred_rows != gold_rows AND is_correct = 0 AND pred_rows IS NOT NULL
ORDER BY ABS(pred_rows - gold_rows) DESC;
""".strip(),
    },
    "empty_predictions": {
        "title": "Tasks with Missing or Empty Predictions",
        "category": "Failure Diagnostics",
        "description": "Finds tasks where result.csv was empty (0 bytes) or failed to execute.",
        "sql": """
SELECT 
    task_id,
    persona,
    difficulty,
    exit_code,
    csv_sha256,
    error_info
FROM task_provenance
WHERE pred_rows IS NULL OR pred_rows = 0 OR exit_code != 0;
""".strip(),
    },

    # -------------------------------------------------------------------------
    # 6. Scientific Lineage & Cryptographic Integrity
    # -------------------------------------------------------------------------
    "provenance_integrity_audit": {
        "title": "Cryptographic Lineage Audit (SHA256 Integrity)",
        "category": "Scientific Lineage",
        "description": "Verifies that all required cryptographic digests were captured for scientific audit.",
        "sql": """
SELECT 
    COUNT(*) AS total_tasks,
    SUM(CASE WHEN prompt_hash IS NOT NULL AND prompt_hash != '' THEN 1 ELSE 0 END) AS valid_prompt_hashes,
    SUM(CASE WHEN schema_sha256 IS NOT NULL AND schema_sha256 != '' THEN 1 ELSE 0 END) AS valid_schema_hashes,
    SUM(CASE WHEN model_digest IS NOT NULL AND model_digest != '' THEN 1 ELSE 0 END) AS valid_model_digests,
    SUM(CASE WHEN csv_sha256 IS NOT NULL AND csv_sha256 != '' THEN 1 ELSE 0 END) AS valid_csv_hashes,
    SUM(CASE WHEN raw_prov_json IS NOT NULL THEN 1 ELSE 0 END) AS valid_w3c_records
FROM task_provenance;
""".strip(),
    },
    "model_version_audit": {
        "title": "Model Version and Weights Digest Audit",
        "category": "Scientific Lineage",
        "description": "Audits model tag, weights digest, provider, and container across tasks.",
        "sql": """
SELECT 
    model,
    model_digest,
    provider,
    COUNT(*) AS task_count
FROM task_provenance
GROUP BY model, model_digest, provider;
""".strip(),
    },
}


# =============================================================================
# Query Execution & Formatting Helpers
# =============================================================================

def run_query(db_path: str, query_id: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    """
    Executes a query by its ID from the catalog against the target SQLite database.
    Returns (columns, rows).
    """
    if query_id not in CATALOG:
        raise KeyError(f"Query ID '{query_id}' not found in catalog. Available: {list(CATALOG.keys())}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(CATALOG[query_id]["sql"])
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, rows
    finally:
        conn.close()


def print_table(cols: List[str], rows: List[Tuple[Any, ...]]) -> None:
    """Prints a clean ASCII table."""
    if not rows:
        print("(0 rows returned)")
        return
    col_widths = [max(len(str(c)), max(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    header = " | ".join(f"{cols[i]:<{col_widths[i]}}" for i in range(len(cols)))
    sep = "-+-".join("-" * col_widths[i] for i in range(len(cols)))
    print(header)
    print(sep)
    for r in rows:
        row_str = " | ".join(f"{str(r[i]):<{col_widths[i]}}" for i in range(len(r)))
        print(row_str)
    print(f"({len(rows)} rows)")


def list_catalog() -> None:
    """Prints all catalog queries categorized."""
    print("=" * 80)
    print("JABUTI-SQL PROVENANCE & TELEMETRY QUERY CATALOG")
    print("=" * 80)
    current_cat = None
    for qid, qdata in CATALOG.items():
        cat = qdata["category"]
        if cat != current_cat:
            current_cat = cat
            print(f"\n📂 [{current_cat.upper()}]")
        print(f"  • {qid:<30} - {qdata['title']}")
        print(f"    └─ {qdata['description']}")
    print("\n" + "=" * 80)


def generate_sql_file(output_path: str) -> None:
    """Generates a standalone, beautifully commented .sql file."""
    lines = [
        "-- ============================================================================",
        "-- JABUTI-SQL PROVENANCE & TELEMETRY QUERY CATALOG",
        "-- Standalone SQL script for DBeaver, TablePlus, or SQLite CLI",
        "-- Compatible with: provenance.db",
        "-- ============================================================================",
        "",
    ]
    current_cat = None
    for idx, (qid, qdata) in enumerate(CATALOG.items(), start=1):
        cat = qdata["category"]
        if cat != current_cat:
            current_cat = cat
            lines.extend([
                "",
                "-- ----------------------------------------------------------------------------",
                f"-- SECTION: {current_cat.upper()}",
                "-- ----------------------------------------------------------------------------",
                "",
            ])
        lines.append(f"-- Query {idx:02d}: {qdata['title']} (ID: {qid})")
        lines.append(f"-- Description: {qdata['description']}")
        clean_sql = qdata["sql"].rstrip(";").strip()
        lines.append(clean_sql + ";")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[SUCCESS] Exported {len(CATALOG)} queries to '{output_path}'")


def generate_markdown_report(db_path: str, output_path: str) -> None:
    """Executes all queries and writes an analytical markdown report."""
    md_lines = [
        "# JABUTI-SQL Provenance & Telemetry Benchmark Report",
        f"**Database**: `{db_path}`  ",
        f"**Queries Executed**: {len(CATALOG)}  ",
        "",
        "---",
        "",
    ]
    for qid, qdata in CATALOG.items():
        cols, rows = run_query(db_path, qid)
        md_lines.append(f"## {qdata['title']}")
        md_lines.append(f"*{qdata['description']}* (ID: `{qid}`)\n")
        if not rows:
            md_lines.append("*(No rows returned)*\n")
            continue
        # Markdown table
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join("---" for _ in cols) + " |"
        md_lines.append(header)
        md_lines.append(sep)
        for r in rows:
            md_lines.append("| " + " | ".join(str(val) for val in r) + " |")
        md_lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"[SUCCESS] Exported full analytical markdown report to '{output_path}'")


# =============================================================================
# CLI Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Catalog of Provenance & Telemetry SQL Queries for provenance.db"
    )
    parser.add_argument(
        "--db_path",
        "-d",
        type=str,
        default="output/qwen2.5-coder_32b-full-run/provenance.db",
        help="Path to provenance.db (default: output/qwen2.5-coder_32b-full-run/provenance.db)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all queries in the catalog",
    )
    parser.add_argument(
        "--run",
        "-r",
        type=str,
        default=None,
        help="Run a specific query by its catalog ID (e.g. semantic_consistency)",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Execute all queries in the catalog and print results",
    )
    parser.add_argument(
        "--export-sql",
        type=str,
        default=None,
        help="Export all catalog queries into a standalone .sql file",
    )
    parser.add_argument(
        "--export-markdown",
        type=str,
        default=None,
        help="Execute all queries and export as a formatted Markdown report",
    )

    args = parser.parse_args()

    # Priority 1: List
    if args.list:
        list_catalog()
        return

    # Priority 2: Export SQL
    if args.export_sql:
        generate_sql_file(args.export_sql)
        return

    # Priority 3: Export Markdown Report
    if args.export_markdown:
        if not os.path.isfile(args.db_path):
            print(f"ERROR: Database file not found: {args.db_path}", file=sys.stderr)
            sys.exit(1)
        generate_markdown_report(args.db_path, args.export_markdown)
        return

    # Priority 4: Run single query
    if args.run:
        if not os.path.isfile(args.db_path):
            print(f"ERROR: Database file not found: {args.db_path}", file=sys.stderr)
            sys.exit(1)
        if args.run not in CATALOG:
            print(f"ERROR: Unknown query ID '{args.run}'. Run --list to see available queries.", file=sys.stderr)
            sys.exit(1)
        qdata = CATALOG[args.run]
        print("\n" + "=" * 80)
        print(f"QUERY: {qdata['title']} (ID: {args.run})")
        print(f"DESCRIPTION: {qdata['description']}")
        print("=" * 80)
        cols, rows = run_query(args.db_path, args.run)
        print_table(cols, rows)
        print()
        return

    # Priority 5: Run all queries
    if args.run_all:
        if not os.path.isfile(args.db_path):
            print(f"ERROR: Database file not found: {args.db_path}", file=sys.stderr)
            sys.exit(1)
        print("\n" + "=" * 80)
        print(f"EXECUTING ALL {len(CATALOG)} QUERIES AGAINST: {args.db_path}")
        print("=" * 80)
        for qid, qdata in CATALOG.items():
            print(f"\n▶ [{qdata['category'].upper()}] {qdata['title']} (ID: {qid})")
            print("-" * 80)
            cols, rows = run_query(args.db_path, qid)
            print_table(cols, rows)
        print("\n" + "=" * 80)
        print("[SUCCESS] All queries executed successfully.")
        print("=" * 80 + "\n")
        return

    # Default action if no flag given
    list_catalog()
    print("Tip: Use --run <query_id> to execute a query, or --run-all to execute all.")


if __name__ == "__main__":
    main()
