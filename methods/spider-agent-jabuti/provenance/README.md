# JABUTI-SQL Provenance & Analytical Store

This directory provides the tools to ingest, organize, and query scientific provenance and execution telemetry collected during JABUTI-SQL benchmark runs.

---

## 🏗️ Architecture & Isolation

```
       Experimental Target                       Metadata & Lineage Store
 ┌───────────────────────────────┐              ┌───────────────────────────────┐
 │     PostgreSQL 16 Engine      │              │       SQLite Database         │
 │       (jabuti-postgres)       │   ISOLATED   │        (provenance.db)        │
 │           Port 5432           │  ──────────► │    (Self-Contained File)      │
 ├───────────────────────────────┤              ├───────────────────────────────┤
 │ • 15 domain healthcare tables │              │ • runs                        │
 │ • 143M stock records          │              │ • task_provenance             │
 │ • Queriable BY the agent      │              │ • task_steps (ReAct trace)    │
 └───────────────────────────────┘              └───────────────────────────────┘
```

> **Why Database Isolation?**  
> Provenance data is strictly kept separate from the `jabuti_sql` PostgreSQL instance. Storing logs or telemetry inside `jabuti_sql` would contaminate the database schema, expose metadata tables to the agent when it executes `\dt`, and risk accidental corruption from agent-generated SQL queries.

---

## 📂 Files in this Directory

| File | Purpose |
| :--- | :--- |
| **`ingest_provenance_sqlite.py`** | Scans run outputs, parses `task_provenance.json`, `metrics.json`, `evaluation_report.json`, and `spider/result.json`, and ingests them into `provenance.db`. |
| **`provenance_queries.py`** | Executable catalog of 18 analytical SQL queries (usable via CLI or as an importable Python library). |
| **`provenance_queries.sql`** | Standalone SQL script with all 18 queries and block comments for GUI tools (DBeaver, TablePlus, VS Code). |

---

## 🚀 Quickstart

### 1. Ingest a Run into SQLite
```bash
python ingest_provenance_sqlite.py \
    --results_dir ../output/qwen2.5-coder_32b-full-run
```
This creates `provenance.db` directly inside the run directory.

*(To compare multiple models in a single shared database, pass `--db_path ../output/benchmark_provenance.db`).*

### 2. Query the Catalog via CLI
```bash
# List all 18 queries:
python provenance_queries.py --list

# Run a specific query (e.g. semantic consistency):
python provenance_queries.py \
    --db_path ../output/qwen2.5-coder_32b-full-run/provenance.db \
    --run semantic_consistency

# Execute all queries and display formatted tables:
python provenance_queries.py \
    --db_path ../output/qwen2.5-coder_32b-full-run/provenance.db \
    --run-all

# Export a complete Markdown report:
python provenance_queries.py \
    --db_path ../output/qwen2.5-coder_32b-full-run/provenance.db \
    --export-markdown ../output/qwen2.5-coder_32b-full-run/analysis_report.md
```

### 3. Open in a Database GUI
Open `provenance.db` in **DBeaver**, **TablePlus**, or **VS Code SQLite Viewer** and run queries from `provenance_queries.sql`.

---

## 📊 Database Schema & Views

### Tables
* **`runs`**: Top-level experiment record (`run_id`, `model`, `provider`, `accuracy`, `avg_llm_sec`, `avg_db_sec`, `total_duration_sec`).
* **`task_provenance`**: Detailed task record (69 rows) with persona, difficulty, parent group, decomposed latencies ($T_{Total}$, $T_{LLM}$, $T_{DB}$, $T_{Other}$), token counts, export syntax, exit code, correctness (`is_correct`), and full `raw_prov_json`.
* **`task_steps`**: Full ReAct cognitive step trace (thoughts, actions, action types, parsed SQL queries, observations).

### Pre-Built Views
* **`v_persona_summary`**: Aggregates accuracy %, average LLM latency, and average ReAct steps across the 3 personas.
* **`v_difficulty_summary`**: Aggregates performance across `simple`, `medium`, and `hard` questions.
* **`v_sql_actions`**: Extracts all SQL queries executed by the model during the benchmark.
