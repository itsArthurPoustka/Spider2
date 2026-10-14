#!/usr/bin/env python3
"""
setup_jabuti.py — One-time setup script for the JABUTI-SQL benchmark
=====================================================================

PURPOSE
-------
Spider-agent-lite expects its benchmark data in a very specific layout:

  1. A JSONL file where each line is a task with fields like ``instance_id``,
     ``question``, ``db``, etc.
  2. A per-task folder under ``examples/<instance_id>/`` containing any files
     the agent needs at runtime (DDL schema, README, credentials, etc.).
  3. Gold result CSVs for evaluation (one per task), produced by executing the
     reference SQL against the real database.

JABUTI-SQL ships as a single ``benchmark.json`` (array of 69 question/SQL
pairs) plus a ``ddl.sql`` schema dump.  This script bridges the two worlds.

WHAT THIS SCRIPT DOES
---------------------
1. **Converts** ``benchmark.json`` → ``examples/jabuti.jsonl``
   - Each entry gets an ``instance_id`` prefixed with ``local_jabuti_`` so that
     ``run.py``'s task-type routing recognises it as a "local" task.
   - The gold SQL is preserved in the JSONL for the evaluation pipeline.

2. **Creates per-task folders** ``examples/local_jabuti_XXX/``
   - Copies the JABUTI-SQL DDL into each folder.
   - Writes a README.md with connection instructions for the agent.

3. **Generates gold CSV results** (optional, requires a running PostgreSQL with
   the jabuti_sql database loaded)
   - Executes each task's reference SQL against ``jabuti_sql``.
   - Saves the result as ``evaluation/gold/<instance_id>.csv``.
   - These CSVs are later used by ``evaluate_jabuti.py``.

USAGE
-----
  # Basic setup (no gold generation):
  python setup_jabuti.py

  # Full setup including gold CSV generation:
  python setup_jabuti.py --generate-gold

  # Custom paths:
  python setup_jabuti.py \\
      --benchmark /path/to/benchmark.json \\
      --ddl /path/to/ddl.sql \\
      --generate-gold \\
      --pg-host localhost --pg-port 5432 --pg-user postgres --pg-dbname jabuti_sql

NOTES
-----
- The ``instance_id`` MUST start with ``local`` for ``run.py`` to route it
  to the local-DB code path (see ``run.py`` line 152–154).
- Questions are in Portuguese.  Column/table names are also in Portuguese.
- The ``parent_id`` field in benchmark.json groups questions that are the same
  underlying query asked from three different personas.  We preserve this
  metadata for per-persona analysis.
"""

import argparse
import json
import os
import pathlib
import shutil
import sys
import textwrap


# ---------------------------------------------------------------------------
# Default paths — checks both Spider2/JABUTI-SQL and sibling JABUTI-SQL
# ---------------------------------------------------------------------------
def resolve_default_path(subpath: str) -> str:
    p1 = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "JABUTI-SQL", subpath))
    if os.path.exists(p1):
        return p1
    p2 = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "JABUTI-SQL", subpath))
    if os.path.exists(p2):
        return p2
    return p1


DEFAULT_BENCHMARK = resolve_default_path(os.path.join("questoes", "benchmark.json"))
DEFAULT_DDL = resolve_default_path(os.path.join("ddl", "ddl.sql"))
DEFAULT_DOCS_DIR = resolve_default_path("docs")


def convert_benchmark_to_jsonl(benchmark_path: str, output_path: str) -> list:
    """
    Convert JABUTI-SQL ``benchmark.json`` → spider-agent-lite ``jabuti.jsonl``.

    Returns the list of task dicts for further processing.

    Mapping decisions (documented for paper writing):
    - ``instance_id``: ``local_jabuti_<NNN>`` — the ``local`` prefix is
      mandatory for spider-agent-lite's task-type routing.
    - ``question``: kept verbatim from the benchmark (Portuguese).
    - ``gold_sql``: the reference SQL, used only during evaluation.
    - ``difficulty``: preserved for stratified metric reporting.
    - ``persona``: preserved for per-persona metric reporting.
    - ``parent_id``: links triples of questions (same query, different persona).
      If parent_id is missing/null in benchmark.json, groups by triple (id // 3).
    - ``db``: always ``jabuti_sql`` — matches the PostgreSQL database name.
    """
    with open(benchmark_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    tasks = []
    for item in items:
        parent_id = item.get("parent_id")
        if parent_id is None:
            parent_id = item["id"] // 3

        task = {
            "instance_id": f"local_jabuti_{item['id']:03d}",
            "question": item["question"],
            "gold_sql": item["sql"],
            "difficulty": item["difficulty"],
            "persona": item["persona"]["role"],
            "persona_description": item["persona"]["description"],
            "parent_id": parent_id,
            "db": "jabuti_sql",
            # Spider-agent-lite uses this field in agents.py to pick the
            # system prompt.  We set it here so it doesn't need to be inferred.
            "type": "PostgreSQL",
        }
        tasks.append(task)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        for task in tasks:
            out.write(json.dumps(task, ensure_ascii=False) + "\n")

    print(f"[setup_jabuti] Written {len(tasks)} tasks to {output_path}")
    return tasks


def create_example_folders(
    tasks: list,
    ddl_path: str,
    docs_dir: str,
    examples_dir: str = "examples",
):
    """
    Create per-task folders under ``examples/<instance_id>/``.

    Each folder contains:
    - ``ddl.sql``  — the full PostgreSQL schema so the agent can ``cat`` it.
    - ``README.md`` — human-readable instructions for the agent (and for you).
    - ``dicionario_dados_Jabuti.pdf`` — the data dictionary (if available).
    """
    for task in tasks:
        iid = task["instance_id"]
        folder = pathlib.Path(examples_dir) / iid
        folder.mkdir(parents=True, exist_ok=True)

        # Copy DDL
        if os.path.exists(ddl_path):
            shutil.copy(ddl_path, folder / "ddl.sql")

        # Copy data dictionary PDF if available
        dict_pdf = os.path.join(docs_dir, "dicionario_dados_Jabuti.pdf")
        if os.path.exists(dict_pdf):
            shutil.copy(dict_pdf, folder / "dicionario_dados_Jabuti.pdf")

        # Write README
        readme_content = textwrap.dedent(f"""\
            # JABUTI-SQL — Task {iid}

            ## Database
            - **Engine**: PostgreSQL (running inside this container)
            - **Database name**: `jabuti_sql`
            - **Connect**: `psql -U postgres jabuti_sql`

            ## Schema
            The full DDL is in `ddl.sql`.  Run `cat ddl.sql` to inspect it.
            There are 15 tables with Portuguese column names.

            ## Key tables
            | Table | Rows | Description |
            |---|---|---|
            | instituicao | 610K | Health institutions |
            | instituicao_estoca_produto | 143M | Stock records (LARGE!) |
            | mantenedora_compra_produto | 26K | Purchase records |
            | leitos | 86K | Hospital beds |
            | produto | 20K | Products |
            | municipio | 5.5K | Municipalities |
            | mv_estoque_mais_recente | — | Materialized view: latest stock |
            | mv_leitos_mais_recente | — | Materialized view: latest beds |

            ## Warning
            - `instituicao_estoca_produto` has 143 MILLION rows.
              **Never run `SELECT *` without LIMIT** on this table.
            - Use the materialized views (`mv_estoque_mais_recente`,
              `mv_leitos_mais_recente`) when you need only the latest snapshot.
            - All names are in Portuguese.

            ## Task
            **Question**: {task['question']}
            **Difficulty**: {task['difficulty']}
            **Persona**: {task['persona']}
        """)
        (folder / "README.md").write_text(readme_content, encoding="utf-8")

    print(f"[setup_jabuti] Created {len(tasks)} example folders in {examples_dir}/")


def generate_gold_results(
    tasks: list,
    gold_dir: str = "evaluation/gold",
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pg_user: str = "postgres",
    pg_password: str = "",
    pg_dbname: str = "jabuti_sql",
):
    """
    Execute each task's gold SQL against PostgreSQL and save as CSV.

    These CSVs are the ground truth used by ``evaluate_jabuti.py``.

    IMPORTANT FOR PAPER WRITING:
    - The gold CSVs are generated from the *exact* SQL in benchmark.json.
    - Evaluation compares the agent's result.csv against these gold CSVs
      using column-wise vector matching with 1e-2 tolerance for numerics.
    - NULL values are normalised to 0 for comparison.
    """
    try:
        import psycopg2
        import pandas as pd
    except ImportError:
        print(
            "[setup_jabuti] ERROR: psycopg2 and pandas are required for gold "
            "generation. Install with: pip install psycopg2-binary pandas"
        )
        sys.exit(1)

    os.makedirs(gold_dir, exist_ok=True)

    conn_params = {
        "host": pg_host,
        "port": pg_port,
        "user": pg_user,
        "dbname": pg_dbname,
    }
    if pg_password:
        conn_params["password"] = pg_password

    conn = psycopg2.connect(**conn_params)
    success_count = 0
    error_count = 0

    for task in tasks:
        iid = task["instance_id"]
        gold_sql = task["gold_sql"].strip()
        csv_path = os.path.join(gold_dir, f"{iid}.csv")

        try:
            df = pd.read_sql_query(gold_sql, conn)
            df.to_csv(csv_path, index=False)
            success_count += 1
            print(f"  [gold] {iid}: {len(df)} rows → {csv_path}")
        except Exception as e:
            error_count += 1
            print(f"  [gold] {iid}: ERROR — {e}")

    conn.close()
    print(
        f"[setup_jabuti] Gold generation complete: "
        f"{success_count} OK, {error_count} errors"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Setup JABUTI-SQL benchmark for spider-agent-lite"
    )
    parser.add_argument(
        "--benchmark", default=DEFAULT_BENCHMARK,
        help="Path to JABUTI-SQL benchmark.json"
    )
    parser.add_argument(
        "--ddl", default=DEFAULT_DDL,
        help="Path to JABUTI-SQL ddl.sql"
    )
    parser.add_argument(
        "--docs-dir", default=DEFAULT_DOCS_DIR,
        help="Path to JABUTI-SQL docs/ directory"
    )
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument(
        "--output-jsonl", default=os.path.join(base_dir, "examples", "jabuti.jsonl"),
        help="Output JSONL path"
    )
    parser.add_argument(
        "--examples-dir", default=os.path.join(base_dir, "examples"),
        help="Directory for per-task example folders"
    )
    parser.add_argument(
        "--generate-gold", action="store_true",
        help="Generate gold CSVs by running reference SQL against PostgreSQL"
    )
    parser.add_argument(
        "--instances", default="all",
        help="Comma-separated instance IDs or integer IDs (e.g. '0,1,2,21,22,23' or 'all')"
    )
    parser.add_argument(
        "--gold-dir", default=os.path.join(base_dir, "evaluation", "gold"),
        help="Directory for gold result CSVs"
    )
    # PostgreSQL connection options (only used with --generate-gold)
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument("--pg-password", default="")
    parser.add_argument("--pg-dbname", default="jabuti_sql")

    args = parser.parse_args()

    # Resolve paths
    benchmark_path = os.path.abspath(args.benchmark)
    ddl_path = os.path.abspath(args.ddl)
    docs_dir = os.path.abspath(args.docs_dir)

    if not os.path.exists(benchmark_path):
        print(f"ERROR: benchmark.json not found at {benchmark_path}")
        sys.exit(1)

    # Step 1: Convert benchmark.json → jabuti.jsonl
    tasks = convert_benchmark_to_jsonl(benchmark_path, args.output_jsonl)

    # Step 2: Create per-task example folders
    create_example_folders(tasks, ddl_path, docs_dir, args.examples_dir)

    # Step 3: Optionally generate gold CSVs
    if args.generate_gold:
        gold_tasks = tasks
        if args.instances != "all":
            selected_ids = set()
            for part in args.instances.split(","):
                part = part.strip()
                if part.isdigit():
                    selected_ids.add(f"local_jabuti_{int(part):03d}")
                else:
                    selected_ids.add(part)
            gold_tasks = [t for t in tasks if t["instance_id"] in selected_ids]
            print(f"[setup_jabuti] Filtered to {len(gold_tasks)} tasks for gold generation: {sorted(selected_ids)}")

        generate_gold_results(
            gold_tasks,
            gold_dir=args.gold_dir,
            pg_host=args.pg_host,
            pg_port=args.pg_port,
            pg_user=args.pg_user,
            pg_password=args.pg_password,
            pg_dbname=args.pg_dbname,
        )

    print("\n[setup_jabuti] Setup complete!")
    print("Next steps:")
    print("  1. Start the JABUTI database:")
    print("     cd jabuti_db && docker compose up -d && python load_dump.py")
    print("  2. Build the agent Docker image:")
    print("     docker build -t spider_agent_jabuti-image spider_agent/images/spider_agent_jabuti-image/")
    print("  3. Run smoke test (questions 0,1,2):")
    print("     python run.py --model <model> --test_path examples/jabuti.jsonl --pg_only -i 0-3 -s jabuti_smoke")
    print("  4. Extract results:")
    print("     python get_jabuti_submission_data.py --experiment_suffix <model>-jabuti_smoke")
    print("  5. Evaluate:")
    print("     python evaluate_jabuti.py --result_dir evaluation/predictions/<model>-jabuti_smoke")



if __name__ == "__main__":
    main()
