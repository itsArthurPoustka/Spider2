#!/usr/bin/env python3
"""
evaluate_jabuti.py — Evaluate JABUTI-SQL benchmark results
============================================================

PURPOSE
-------
This script evaluates the agent's predictions against gold results for the
JABUTI-SQL benchmark.  It is adapted from Spider2-lite's ``evaluate.py`` with
the following key differences:

1. **No BigQuery/SQLite execution** — All evaluation is execution-result-based
   (the agent already produced CSV files during the run).

2. **PostgreSQL gold execution** — If the gold CSVs don't exist yet, this
   script can optionally connect to a PostgreSQL database to generate them.

3. **Stratified metrics** — Reports accuracy broken down by:
   - Overall accuracy
   - Per-difficulty (easy, medium, hard)
   - Per-persona (Cidadã Leiga, Analista de Dados, Médico Gestor)
   - Per-parent_id (grouped questions — same query, different phrasing)

4. **Detailed JSON report** — Saves a full ``evaluation_report.json`` with
   per-task scores, errors, and metadata for paper writing.

EVALUATION METHOD (for paper documentation)
─────────────────────────────────────────────
The evaluation uses the same column-wise vector matching as Spider2-lite:

- The predicted CSV and gold CSV are loaded as Pandas DataFrames.
- Each column in the gold DataFrame is treated as a "vector".
- For each gold vector, we check if ANY column in the predicted DataFrame
  matches it within a tolerance of 1e-2 for numeric values.
- NULL/NaN values are normalised to 0.
- The match is ORDER-INSENSITIVE within columns (sorted comparison).
- A task scores 1 (correct) only if ALL gold vectors find a match in the
  prediction.
- The final metric is accuracy = correct / total.

This is identical to Spider2-lite's ``compare_pandas_table()`` function
from ``evaluate.py``.  We import it directly to ensure consistency.

USAGE
-----
  # Evaluate predictions against pre-generated gold CSVs:
  python evaluate_jabuti.py \\
      --result_dir evaluation/predictions/gpt-4o-jabuti_test1 \\
      --gold_dir evaluation/gold \\
      --jabuti_jsonl examples/jabuti.jsonl

  # Generate gold CSVs on-the-fly from PostgreSQL:
  python evaluate_jabuti.py \\
      --result_dir evaluation/predictions/gpt-4o-jabuti_test1 \\
      --gold_dir evaluation/gold \\
      --jabuti_jsonl examples/jabuti.jsonl \\
      --generate_gold \\
      --pg_host localhost --pg_dbname jabuti_sql
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime

import pandas as pd


# =============================================================================
# Core comparison functions (adapted from Spider2-lite's evaluate.py)
# =============================================================================
# ADAPTATION NOTE:
# These functions are copied from Spider2-lite's evaluate.py to avoid
# introducing a dependency on that module (which lives in a different
# directory and has its own dependencies like google-cloud-bigquery).
# The logic is IDENTICAL — if Spider2-lite's comparison logic changes,
# this should be updated accordingly.
# =============================================================================

def compare_pandas_table(
    pred: pd.DataFrame,
    gold: pd.DataFrame,
    condition_cols=None,
    ignore_order: bool = True,
) -> int:
    """
    Compare predicted vs gold DataFrames using column-wise vector matching.

    METRIC EXPLANATION (for paper writing):
    ────────────────────────────────────────
    1. Each column in the gold DataFrame is treated as a vector of values.
    2. For each gold column-vector, we search for a matching column-vector
       in the predicted DataFrame.
    3. Two vectors match if:
       a) They have the same length.
       b) For numeric pairs: abs(a - b) <= 1e-2 (tolerance).
       c) For non-numeric pairs: exact string equality.
       d) NaN/NULL values are normalised to 0 before comparison.
    4. If ignore_order=True (default for JABUTI), values within each vector
       are sorted before comparison, so row order doesn't matter.
    5. A task scores 1 ONLY if ALL gold vectors find a match.

    Args:
        pred: Predicted DataFrame from agent's result.csv
        gold: Gold DataFrame from evaluation/gold/<instance_id>.csv
        condition_cols: Optional list of column indices to compare (None=all)
        ignore_order: If True, sort values within columns before comparing

    Returns:
        1 if all gold columns match, 0 otherwise
    """
    tolerance = 1e-2

    def normalize(value):
        """Normalise NULL/NaN to 0 for comparison."""
        if pd.isna(value):
            return 0
        return value

    def vectors_match(v1, v2, tol=tolerance, ignore_order_=False):
        """Check if two value-vectors match within tolerance."""
        v1 = [normalize(x) for x in v1]
        v2 = [normalize(x) for x in v2]

        if ignore_order_:
            v1 = sorted(v1, key=lambda x: (x is None, str(x), isinstance(x, (int, float))))
            v2 = sorted(v2, key=lambda x: (x is None, str(x), isinstance(x, (int, float))))

        if len(v1) != len(v2):
            return False

        for a, b in zip(v1, v2):
            if pd.isna(a) and pd.isna(b):
                continue
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if not math.isclose(float(a), float(b), abs_tol=tol):
                    return False
            elif a != b:
                return False
        return True

    if condition_cols:
        if not isinstance(condition_cols, (list, tuple)):
            condition_cols = [condition_cols]
        gold_cols = gold.iloc[:, condition_cols]
    else:
        gold_cols = gold

    pred_cols = pred
    t_gold_list = gold_cols.transpose().values.tolist()
    t_pred_list = pred_cols.transpose().values.tolist()
    score = 1

    for gold_vector in t_gold_list:
        if not any(
            vectors_match(gold_vector, pred_vector, ignore_order_=ignore_order)
            for pred_vector in t_pred_list
        ):
            score = 0
            break

    return score


# =============================================================================
# Gold result generation (optional)
# =============================================================================

def generate_gold_from_postgres(
    tasks: list,
    gold_dir: str,
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pg_user: str = "postgres",
    pg_password: str = "",
    pg_dbname: str = "jabuti_sql",
):
    """
    Generate gold CSVs by executing reference SQL against PostgreSQL.

    Only generates missing gold files (does not overwrite existing ones).
    """
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 required. Install with: pip install psycopg2-binary")
        sys.exit(1)

    os.makedirs(gold_dir, exist_ok=True)

    conn_params = {"host": pg_host, "port": pg_port, "user": pg_user, "dbname": pg_dbname}
    if pg_password:
        conn_params["password"] = pg_password

    conn = psycopg2.connect(**conn_params)
    generated = 0

    for task in tasks:
        iid = task["instance_id"]
        csv_path = os.path.join(gold_dir, f"{iid}.csv")

        if os.path.exists(csv_path):
            continue

        try:
            df = pd.read_sql_query(task["gold_sql"].strip(), conn)
            df.to_csv(csv_path, index=False)
            generated += 1
        except Exception as e:
            print(f"  [gold-gen] {iid}: ERROR — {e}")

    conn.close()
    if generated > 0:
        print(f"Generated {generated} new gold CSVs in {gold_dir}")


# =============================================================================
# Evaluation functions
# =============================================================================

def evaluate_single_instance(
    instance_id: str,
    pred_dir: str,
    gold_dir: str,
) -> dict:
    """
    Evaluate a single JABUTI-SQL task instance.

    Returns a dict with:
      - instance_id: the task ID
      - score: 1 (correct) or 0 (incorrect)
      - error_info: None if correct, error description otherwise
      - pred_rows: number of rows in predicted CSV
      - gold_rows: number of rows in gold CSV
    """
    result = {
        "instance_id": instance_id,
        "score": 0,
        "error_info": None,
        "pred_rows": 0,
        "gold_rows": 0,
    }

    # Load predicted CSV
    pred_path = Path(pred_dir) / f"{instance_id}.csv"
    if not pred_path.exists():
        result["error_info"] = f"Prediction file not found: {pred_path}"
        return result

    try:
        pred_df = pd.read_csv(pred_path)
        result["pred_rows"] = len(pred_df)
    except Exception as e:
        result["error_info"] = f"Failed to read prediction CSV: {e}"
        return result

    # Load gold CSV
    gold_path = Path(gold_dir) / f"{instance_id}.csv"
    if not gold_path.exists():
        result["error_info"] = f"Gold file not found: {gold_path}"
        return result

    try:
        gold_df = pd.read_csv(gold_path)
        result["gold_rows"] = len(gold_df)
    except Exception as e:
        result["error_info"] = f"Failed to read gold CSV: {e}"
        return result

    # Compare
    try:
        # JABUTI-SQL uses ignore_order=True because:
        # 1. The questions often ask for aggregates (single values), where
        #    order is irrelevant.
        # 2. For multi-row results, the SQL may not have ORDER BY, so
        #    row order depends on the DB engine's internal order.
        score = compare_pandas_table(pred_df, gold_df, ignore_order=True)
        result["score"] = score
        if score == 0:
            result["error_info"] = "Result mismatch"
    except Exception as e:
        result["error_info"] = f"Comparison error: {e}"

    return result


def compute_stratified_metrics(results: list, task_metadata: dict) -> dict:
    """
    Compute stratified accuracy metrics for the evaluation report.

    METRICS EXPLANATION (for paper writing):
    ────────────────────────────────────────
    1. **Overall accuracy**: correct / total across all tasks.

    2. **Per-difficulty**: Accuracy for easy, medium, hard tasks.
       - This measures how well the agent handles queries of increasing
         complexity (simple SELECTs vs multi-table JOINs with CTEs).

    3. **Per-persona**: Accuracy for each persona type.
       - JABUTI-SQL has 3 personas: Cidadã Leiga (lay user), Analista de
         Dados em Saúde (data analyst), Médico Gestor Hospitalar (hospital
         manager).  Each asks the same underlying question in different
         language registers.
       - This metric reveals whether the agent is more accurate with
         technical (SQL-like) phrasing vs natural language phrasing.

    4. **Per-parent_id (semantic group)**: Each parent_id groups 3 questions
       that are semantically identical but asked by different personas.
       - A group is "fully correct" if all 3 variants score 1.
       - A group is "partially correct" if at least 1 variant scores 1.
       - This measures consistency: does the agent get the same answer
         regardless of how the question is phrased?

    Args:
        results: List of per-task evaluation results
        task_metadata: Dict of instance_id → {difficulty, persona, parent_id, ...}

    Returns:
        Dict with stratified metrics
    """
    total = len(results)
    correct = sum(r["score"] for r in results)

    metrics = {
        "overall": {
            "accuracy": correct / total if total > 0 else 0.0,
            "correct": correct,
            "total": total,
        },
        "per_difficulty": {},
        "per_persona": {},
        "per_parent_group": {},
    }

    # Per-difficulty
    difficulty_groups = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in results:
        meta = task_metadata.get(r["instance_id"], {})
        diff = meta.get("difficulty", "unknown")
        difficulty_groups[diff]["total"] += 1
        difficulty_groups[diff]["correct"] += r["score"]

    for diff, counts in sorted(difficulty_groups.items()):
        metrics["per_difficulty"][diff] = {
            "accuracy": counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0,
            **counts,
        }

    # Per-persona
    persona_groups = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in results:
        meta = task_metadata.get(r["instance_id"], {})
        persona = meta.get("persona", "unknown")
        persona_groups[persona]["total"] += 1
        persona_groups[persona]["correct"] += r["score"]

    for persona, counts in sorted(persona_groups.items()):
        metrics["per_persona"][persona] = {
            "accuracy": counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0,
            **counts,
        }

    # Per-parent_id group (semantic consistency)
    parent_groups = defaultdict(list)
    for r in results:
        meta = task_metadata.get(r["instance_id"], {})
        parent_id = meta.get("parent_id")
        if parent_id is not None:
            parent_groups[parent_id].append(r["score"])

    fully_correct = 0
    partially_correct = 0
    total_groups = len(parent_groups)

    for parent_id, scores in parent_groups.items():
        if all(s == 1 for s in scores):
            fully_correct += 1
        if any(s == 1 for s in scores):
            partially_correct += 1

    metrics["per_parent_group"] = {
        "total_groups": total_groups,
        "fully_correct": fully_correct,
        "partially_correct": partially_correct,
        "fully_correct_rate": fully_correct / total_groups if total_groups > 0 else 0.0,
        "partially_correct_rate": partially_correct / total_groups if total_groups > 0 else 0.0,
    }

    return metrics


def print_metrics(metrics: dict):
    """Pretty-print the evaluation metrics."""
    print("\n" + "=" * 70)
    print("JABUTI-SQL EVALUATION RESULTS")
    print("=" * 70)

    overall = metrics["overall"]
    print(f"\n📊 Overall Accuracy: {overall['accuracy']:.4f} "
          f"({overall['correct']}/{overall['total']})")

    print("\n📈 Per Difficulty:")
    print(f"  {'Difficulty':<12} {'Accuracy':>10} {'Correct':>10} {'Total':>10}")
    print(f"  {'─' * 12} {'─' * 10} {'─' * 10} {'─' * 10}")
    for diff, counts in sorted(metrics["per_difficulty"].items()):
        print(f"  {diff:<12} {counts['accuracy']:>10.4f} "
              f"{counts['correct']:>10} {counts['total']:>10}")

    print("\n👤 Per Persona:")
    print(f"  {'Persona':<35} {'Accuracy':>10} {'Correct':>10} {'Total':>10}")
    print(f"  {'─' * 35} {'─' * 10} {'─' * 10} {'─' * 10}")
    for persona, counts in sorted(metrics["per_persona"].items()):
        label = persona[:35]
        print(f"  {label:<35} {counts['accuracy']:>10.4f} "
              f"{counts['correct']:>10} {counts['total']:>10}")

    groups = metrics["per_parent_group"]
    print(f"\n🔗 Semantic Consistency (parent groups):")
    print(f"  Total groups:           {groups['total_groups']}")
    print(f"  Fully correct (all 3):  {groups['fully_correct']} "
          f"({groups['fully_correct_rate']:.4f})")
    print(f"  Partially correct (≥1): {groups['partially_correct']} "
          f"({groups['partially_correct_rate']:.4f})")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate JABUTI-SQL benchmark results"
    )
    parser.add_argument(
        "--result_dir", type=str, required=True,
        help="Directory containing predicted CSVs (one per instance)"
    )
    parser.add_argument(
        "--gold_dir", type=str, default="evaluation/gold",
        help="Directory containing gold CSVs"
    )
    parser.add_argument(
        "--jabuti_jsonl", type=str, default="examples/jabuti.jsonl",
        help="Path to jabuti.jsonl for task metadata"
    )
    parser.add_argument(
        "--output_report", type=str, default=None,
        help="Path to save JSON evaluation report (default: <result_dir>/evaluation_report.json)"
    )
    # Optional: generate gold on-the-fly
    parser.add_argument("--generate_gold", action="store_true")
    parser.add_argument("--instances", default="all",
                        help="Filter instances to generate gold for (e.g. '0,1,2,21,22,23' or 'all')")
    parser.add_argument("--pg_host", default="localhost")
    parser.add_argument("--pg_port", type=int, default=5432)
    parser.add_argument("--pg_user", default="postgres")
    parser.add_argument("--pg_password", default="")
    parser.add_argument("--pg_dbname", default="jabuti_sql")

    args = parser.parse_args()

    # Load task metadata from JSONL
    task_metadata = {}
    tasks_list = []
    if os.path.exists(args.jabuti_jsonl):
        with open(args.jabuti_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                task = json.loads(line)
                task_metadata[task["instance_id"]] = {
                    "difficulty": task.get("difficulty", "unknown"),
                    "persona": task.get("persona", "unknown"),
                    "parent_id": task.get("parent_id"),
                    "gold_sql": task.get("gold_sql", ""),
                }
                tasks_list.append(task)
    else:
        print(f"WARNING: {args.jabuti_jsonl} not found — no metadata for stratified metrics")

    # Optionally generate gold CSVs
    if args.generate_gold and tasks_list:
        gold_tasks = tasks_list
        if args.instances != "all":
            selected_ids = set()
            for part in args.instances.split(","):
                part = part.strip()
                if part.isdigit():
                    selected_ids.add(f"local_jabuti_{int(part):03d}")
                else:
                    selected_ids.add(part)
            gold_tasks = [t for t in tasks_list if t["instance_id"] in selected_ids]

        generate_gold_from_postgres(
            gold_tasks,
            args.gold_dir,
            pg_host=args.pg_host,
            pg_port=args.pg_port,
            pg_user=args.pg_user,
            pg_password=args.pg_password,
            pg_dbname=args.pg_dbname,
        )

    # Discover predicted task IDs
    if not os.path.exists(args.result_dir):
        print(f"ERROR: Result directory not found: {args.result_dir}")
        sys.exit(1)

    pred_ids = sorted(
        Path(f).stem
        for f in os.listdir(args.result_dir)
        if f.endswith(".csv") and f.startswith("local_jabuti_")
    )

    if not pred_ids:
        print("No JABUTI prediction files found in result_dir")
        sys.exit(1)

    print(f"Found {len(pred_ids)} predictions to evaluate")

    # Evaluate each instance
    results = []
    for instance_id in pred_ids:
        result = evaluate_single_instance(instance_id, args.result_dir, args.gold_dir)
        results.append(result)
        status = "✅" if result["score"] == 1 else "❌"
        error_suffix = f" — {result['error_info']}" if result["error_info"] else ""
        print(f"  {status} {instance_id}{error_suffix}")

    # Compute metrics
    metrics = compute_stratified_metrics(results, task_metadata)
    print_metrics(metrics)

    # Save detailed report
    report_path = args.output_report or os.path.join(args.result_dir, "evaluation_report.json")
    report = {
        "timestamp": datetime.now().isoformat(),
        "result_dir": args.result_dir,
        "gold_dir": args.gold_dir,
        "metrics": metrics,
        "per_task_results": results,
    }

    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
