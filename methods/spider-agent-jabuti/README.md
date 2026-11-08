# Spider-Agent-JABUTI

An autonomous agent framework adapted from Spider 2.0 to evaluate LLMs on the **JABUTI-SQL** benchmark in isolated Docker environments.

---

## 📌 Overview

**Spider-Agent-JABUTI** brings the agentic execution paradigm of Spider 2.0 to the **JABUTI-SQL** Brazilian healthcare database benchmark. JABUTI-SQL features complex real-world healthcare data stored in PostgreSQL, with 69 natural language tasks in Brazilian Portuguese asked across three distinct personas.

### Key Capabilities
- **PostgreSQL Native Support**: Runs queries directly against a standing PostgreSQL container (`jabuti-postgres`) loaded with the full schema and data.
- **Dockerized Agent Execution**: Each task runs inside an isolated container (`spider_agent_jabuti-image`) connected via a shared bridge network (`spider-net`).
- **Atomic Single-Task & AkôFlow DAG Orchestration**: Supports both sequential batch runs (`run.py`) and atomic container-isolated single-task runs (`run_single_task.py`) orchestrated as parallel fan-out/fan-in workflows via **AkôFlow** (`generate_akoflow_workflow.py`).
- **W3C PROV-DM Scientific Provenance & Telemetry**: Automatically records decomposed latencies (`t_llm_ms`, `t_db_ms`, `t_total_ms`), token usage, SQL export tool adherence (`COPY_TO_STDOUT` vs. `PSQL_PLAIN`), and W3C PROV-JSON lineage graphs (`task_provenance.json`).
- **Queryable SQLite Provenance Store (`ingest_provenance_sqlite.py`)**: Consolidates scattered task provenance JSON files and ReAct trajectories into a self-contained, relational SQLite database (`provenance.db`) with analytical views for instant SQL querying without contaminating the domain PostgreSQL instance.
- **Large-Table Awareness**: Tailored system prompts and materialized views to handle high-cardinality tables safely (such as `instituicao_estoca_produto` with 143M+ rows).
- **Stratified & Semantic Consistency Evaluation**: Measures overall execution accuracy, per-difficulty accuracy, per-persona accuracy, and semantic consistency (whether an agent answers all 3 persona phrasings of the same underlying inquiry).

---

## 🏗️ Architecture

```
                               ┌──────────────────────────────────────────────────────────┐
                               │                    Docker Network                        │
                               │                     (spider-net)                         │
                               │                                                          │
  ┌───────────────────────┐    │  ┌───────────────────────┐      ┌─────────────────────┐  │
  │     Host Runner       │    │  │   Agent Container     │      │  PostgreSQL Server  │  │
  │      (run.py)         │───▶│  │ (spider_agent_jabuti) │─────▶│  (jabuti-postgres)  │  │
  │                       │    │  │                       │ psql │  Database:          │  │
  │  - Orchestration      │    │  │  - Bash/psql action   │      │  jabuti_sql         │  │
  │  - Trajectory logging │    │  │  - Schema & DDL       │      │  (15 tables)        │  │
  └──────────┬────────────┘    │  └───────────────────────┘      └─────────────────────┘  │
             │                 └──────────────────────────────────────────────────────────┘
             ▼
  ┌───────────────────────┐
  │   LLM Service         │
  │ - Ollama (local)      │
  │ - OpenAI / Groq / etc.│
  └───────────────────────┘
```

---

## 📂 Directory Layout

```
methods/spider-agent-jabuti/
├── README.md                          # Main documentation and workflow guide
├── SMOKE_TEST_INSTRUCTIONS.md         # Detailed smoke test walkthrough
├── requirements.txt                   # Host Python environment dependencies
├── run.py                             # Benchmark runner and container orchestrator
├── run_single_task.py                 # Atomic single-task runner with W3C PROV & metrics
├── generate_akoflow_workflow.py       # AkôFlow parallel DAG YAML generator
├── setup_jabuti.py                    # Benchmark setup and gold standard generation
├── get_jabuti_submission_data.py      # Result extractor for predictions
├── evaluate_jabuti.py                 # Ground truth evaluation and stratified scoring
├── ingest_provenance_sqlite.py        # Ingests W3C PROV-JSON & ReAct traces into SQLite
├── test_provenance.py                 # Unit tests for provenance, telemetry & single-task runner
├── test_generate_akoflow_workflow.py  # Unit tests for AkôFlow workflow generator
├── test_verify_akoflow_run.py         # Unit tests for AkôFlow run & provenance verifier
├── test_ingest_provenance_sqlite.py   # Unit tests for SQLite provenance ingestion
├── akoflow/                           # AkôFlow workflow specifications & verification tools
│   ├── README_AKOFLOW.md              # Step-by-step remote AkôFlow deployment & execution guide
│   ├── verify_akoflow_run.py          # Artifact, latency & W3C PROV verification harness
│   ├── workflow_jabuti.yaml           # Full 69-task parallel DAG specification
│   └── workflow_smoke.yaml            # 3-task smoke test DAG specification
├── jabuti_db/                         # Database infrastructure
│   ├── docker-compose.yml             # Standing PostgreSQL service
│   └── load_dump.py                   # Schema and dump loader
├── spider_agent/                      # Core agent package
│   ├── agent/                         # ReAct agent loop, models, action space, prompts
│   ├── configs/                       # Configuration utilities
│   ├── controllers/                   # Execution controllers
│   ├── envs/                          # Gym environment abstraction for Docker
│   └── images/
│       └── spider_agent_jabuti-image/ # Dockerfile and init script for agent container
├── examples/                          # Task definitions and runtime folders
│   ├── jabuti.jsonl                   # 69 task metadata records
│   └── local_jabuti_000/ ... 068/     # Per-task runtime folders (DDL, task README)
├── evaluation/
│   ├── gold/                          # Reference CSVs (ground truth)
│   └── predictions/                   # Extracted prediction outputs
├── output/                            # Raw trajectories and agent results
└── logs/                              # Execution logs
```

---

## 🚀 Quickstart

### 1. Prerequisites
- **Docker Desktop** installed and running.
- Python 3.10+ (or activate `./spider-env`).
- LLM backend available (e.g. Ollama running locally at `localhost:11434` or an API key for cloud providers).

Install Python dependencies:
```bash
pip install -r requirements.txt
```

---

### 2. Database Setup

Navigate to `jabuti_db/` and start the standing PostgreSQL container:
```bash
cd jabuti_db
docker compose up -d
docker compose ps
```

Load the schema and standard tables (~1.22M rows across 14 tables in ~15s):
```bash
python load_dump.py --host localhost --port 5432
cd ..
```
*(To also include all 143M rows of stock data, add `--full` to the load command).*

---

### 3. Build Agent Image

Build the container image used for task execution:
```bash
docker build -t spider_agent_jabuti-image spider_agent/images/spider_agent_jabuti-image/
```

---

### 4. Setup Tasks & Gold Standard Data

Verify or generate the benchmark task directories and ground truth CSVs:
```bash
# Generate tasks and gold results for smoke test (tasks 0, 1, 2)
python setup_jabuti.py --generate-gold --instances 0,1,2 --pg-host localhost --pg-port 5432

# Or generate for all 69 tasks
python setup_jabuti.py --generate-gold --instances all --pg-host localhost --pg-port 5432
```

---

## 🧪 Running Tasks

### Smoke Test (3 Instances: Tasks 0, 1, 2)
Runs the Question 1 trio across all 3 personas querying the `instituicao` table:

```bash
# Option A: Directly using raw local Ollama model name (no "gpt-" required!)
python run.py \
    --model qwen2.5-coder:32b \
    -i 0-3 \
    -s smoke_trio

# Option B: Using provider prefix
python run.py \
    --model ollama/qwen2.5-coder:32b \
    -i 0-3 \
    -s smoke_trio

# Option C: Using legacy alias
python run.py \
    --model gpt-qwen-coder \
    -i 0-3 \
    -s smoke_trio
```

> **Model & Provider Configuration:**
> - `--model <name>`: Accepts raw local model names (e.g. `qwen2.5-coder:32b`, `devstral-small-2:24b`), provider prefixes (`ollama/model`, `openai/gpt-4o`), or legacy names (`gpt-qwen-coder`).
> - `--provider [ollama|openai|azure|deepseek|groq]`: Explicit backend selection (defaults to `ollama`).
> - `--base_url <url>`: Connect to any custom OpenAI-compatible server (e.g. `http://localhost:11434/v1` or vLLM).
> - Colons in model tags (e.g. `:32b`) are automatically sanitized to `_` in experiment directories to prevent Docker volume path conflicts.

> **Task selection flags:**
> - `-i 0-3`: Python slice running indices 0, 1, and 2.
> - `-i 0,1,2,21,22,23`: Comma-separated indices.
> - `-n local_jabuti_000`: Run an individual task by name.
> - `-i all`: Run the entire benchmark suite.

---

### Atomic Single-Task Execution (`run_single_task.py`)

For distributed orchestration (such as **AkôFlow**) or isolated task debugging, `run_single_task.py` runs a single task instance inside a uniquely named Docker sandbox (`spider-jabuti-<model>-<task_id>-<uuid>`) and emits standardized telemetry and W3C PROV artifacts:

```bash
python run_single_task.py \
    --task_id local_jabuti_000 \
    --test_path ./examples/jabuti.jsonl \
    --model qwen2.5-coder:32b \
    --provider ollama \
    --base_url http://localhost:11434/v1 \
    --output_dir output/single_run/local_jabuti_000 \
    --max_steps 20
```

#### POSIX Exit Codes
- `0`: Task completed normally (`result.csv` generated).
- `1`: Task aborted due to exception, repeated identical action loop, or missing `result.csv`.
- `2`: Task timed out (exceeded `--max_steps`).

#### Per-Task Output Artifact Contract
Every task execution writes the following files into `--output_dir`:
- `result.csv`: Normalized RFC 4180 CSV prediction table for evaluation.
- `trajectory.json`: Full micro-step ReAct trace (thoughts, actions, observations).
- `metrics.json`: Decomposed wall-clock latencies (`t_total_ms`, `t_llm_ms`, `t_db_ms`), token usage (`tokens_prompt`, `tokens_completion`, `tokens_total`), `step_count`, `export_syntax` (`COPY_TO_STDOUT`, `PSQL_PLAIN`, or `NONE`), and `exit_code`.
- `task_provenance.json`: W3C PROV-JSON document linking `TaskSpec`, `DatabaseState`, `ModelVersion`, `DockerContainer`, `PredictionOutput`, `Metrics`, and `TrajectoryJSON` entities across `LLMBackend`, `PostgreSQLServer`, and `AkôFlowEngine` agents.
- `spider/result.json`: Backwards-compatible Spider2 trajectory/result file.
- `task.log`: Detailed `DEBUG`-level log for the task execution.

---

### AkôFlow Workflow Generation (`generate_akoflow_workflow.py`)

Generate an AkôFlow workflow YAML specification modeling the benchmark sweep as a parallel fan-out/fan-in DAG (`preflight-check` → `task-local_jabuti_000`..`N` → `evaluation`):

```bash
# Generate 3-instance smoke test workflow
python generate_akoflow_workflow.py \
    --model qwen2.5-coder:32b \
    --instances 0,1,2 \
    --output_yaml akoflow/workflow_smoke.yaml

# Generate full 69-instance benchmark workflow
python generate_akoflow_workflow.py \
    --model qwen2.5-coder:32b \
    --instances all \
    --output_yaml akoflow/workflow_jabuti.yaml
```

> **Generator CLI Options:**
> - `--model`: Target LLM model name (default: `qwen2.5-coder:32b`).
> - `--instances`: Subset filter (`all`, comma-separated indices like `0,1,2`, ranges like `0-5`, or task IDs like `local_jabuti_000`).
> - `--output_yaml`: Output YAML path (default: `akoflow/workflow_jabuti.yaml`).
> - `--namespace`: AkôFlow namespace (default: `escience-jabuti`).
> - `--image`: Base runner image (default: `spider-agent-runner:latest`).
> - `--cpu_limit` / `--memory_limit`: Per-activity resource limits (defaults: `"1"` and `"2Gi"`).
> - See [`akoflow/README_AKOFLOW.md`](./akoflow/README_AKOFLOW.md) for complete remote server deployment, NFS/SSHFS shared volume setup, workflow submission, and provenance verification instructions.

### AkôFlow Run & Provenance Verification (`akoflow/verify_akoflow_run.py`)

Verify that all expected tasks produced non-empty `result.csv`, `metrics.json`, and valid W3C PROV `task_provenance.json` records (with matching SHA256 digests), aggregate decomposed latencies ($T_{LLM}$ vs. $T_{DB}$), and optionally check AkôFlow's `/provenance/` REST API:

```bash
python akoflow/verify_akoflow_run.py \
    --results_dir output/test_phase2 \
    --expected_tasks 0,1,2
```

---

## 📊 Evaluation & Metrics

### Option A: Evaluate `run_single_task.py` / AkôFlow Output Directory Directly
`evaluate_jabuti.py` natively discovers nested `<result_dir>/<instance_id>/result.csv` task directories produced by `run_single_task.py`:
```bash
python evaluate_jabuti.py \
    --result_dir output/single_run \
    --gold_dir evaluation/gold \
    --jabuti_jsonl examples/jabuti.jsonl
```

### Option B: Extract & Evaluate Batch `run.py` Outputs
After running `run.py`, extract flat prediction CSVs and evaluate:
```bash
python get_jabuti_submission_data.py \
    --experiment_suffix gpt-qwen-coder-smoke_trio \
    --results_folder_name evaluation/predictions/gpt-qwen-coder-smoke_trio

python evaluate_jabuti.py \
    --result_dir evaluation/predictions/gpt-qwen-coder-smoke_trio \
    --gold_dir evaluation/gold \
    --jabuti_jsonl examples/jabuti.jsonl
```

### Reported Metrics:
1. **Overall Accuracy**: Fraction of tasks matching gold CSVs within 1e-2 numerical tolerance.
2. **Stratified by Difficulty**: Accuracy across `simple`, `medium`, and `hard` questions.
3. **Stratified by Persona**:
   - `Cidadã Leiga` (Everyday Citizen)
   - `Analista de Dados em Saúde` (Health Data Analyst)
   - `Médico Gestor Hospitalar` (Hospital Medical Manager)
4. **Semantic Consistency**: Fraction of question groups where all three persona formulations resulted in the correct answer.

---

## 🗄️ Queryable Provenance Store (`ingest_provenance_sqlite.py`)

While W3C PROV-JSON files (`task_provenance.json`) and granular telemetry (`metrics.json`) provide a standardized, auditable lineage record per task, analyzing 69 individual JSON files manually is cumbersome.

The **SQLite Provenance Ingestion Harness** (`ingest_provenance_sqlite.py`) consolidates task-level provenance, telemetry, evaluation scores, and step-by-step ReAct trajectories into a self-contained, relational SQLite database (`provenance.db`).

### Why an Isolated Database?
- **Domain Database Integrity**: Provenance metadata is strictly isolated from `jabuti-postgres` (`jabuti_sql` on port 5432). Storing logs or telemetry inside `jabuti_sql` would pollute the schema, risk exposing tables to the agent during `\dt` commands, and allow potential corruption from agent SQL queries.
- **Zero-Dependency Portability**: Built with Python's standard `sqlite3` library, requiring no external database servers, background services, or network configuration.
- **Complete Lineage Preservation**: Exposes structured relational columns for rapid filtering and aggregation while preserving the raw W3C PROV-JSON payload in a `raw_prov_json` column.

### Ingestion Usage

```bash
# Ingest a specific run into <results_dir>/provenance.db:
python ingest_provenance_sqlite.py \
    --results_dir output/qwen2.5-coder_32b-full-run

# Ingest into a shared multi-run database (for side-by-side model comparison):
python ingest_provenance_sqlite.py \
    --results_dir output/qwen2.5-coder_32b-full-run \
    --db_path output/benchmark_provenance.db
```

### Database Schema & Analytical Views

| Entity | Type | Description |
|---|---|---|
| **`runs`** | Table | Top-level benchmark experiment record (`run_id`, `model`, `provider`, `accuracy`, `avg_llm_sec`, `avg_db_sec`, `total_duration_sec`). |
| **`task_provenance`** | Table | Granular per-task record (69 rows) with persona, difficulty, parent group, prompt text & hash, decomposed latencies ($T_{Total}$, $T_{LLM}$, $T_{DB}$, $T_{Other}$), token counts, export syntax, exit code, correctness (`is_correct`), and full `raw_prov_json`. |
| **`task_steps`** | Table | Full ReAct cognitive steps trace (thoughts, actions, action types, parsed SQL queries, observations). |
| **`v_persona_summary`** | View | Pre-computed aggregation by persona (task count, accuracy %, avg LLM latency, avg ReAct steps). |
| **`v_difficulty_summary`** | View | Pre-computed aggregation by difficulty tier (`simple`, `medium`, `hard`). |
| **`v_sql_actions`** | View | Extracted SQL commands and queries executed by the model during the benchmark. |

### Querying the Provenance Store

#### 1. Via CLI (`--query` flag)
```bash
python ingest_provenance_sqlite.py \
    --results_dir output/qwen2.5-coder_32b-full-run \
    --query "SELECT * FROM v_difficulty_summary;"
```

#### 2. Via `sqlite3` CLI
```bash
sqlite3 output/qwen2.5-coder_32b-full-run/provenance.db \
  "SELECT persona, COUNT(*), ROUND(AVG(is_correct)*100, 1) AS acc_pct, ROUND(AVG(t_llm_ms)/1000, 1) AS avg_llm_sec FROM task_provenance GROUP BY persona;"
```

#### 3. In Python / Jupyter Notebooks
```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("output/qwen2.5-coder_32b-full-run/provenance.db")
df_prov = pd.read_sql("SELECT * FROM task_provenance", conn)
df_steps = pd.read_sql("SELECT * FROM task_steps", conn)
```

#### 4. In Database GUIs
Open `provenance.db` directly in **DBeaver**, **TablePlus**, **DB Browser for SQLite**, or the **VS Code SQLite Viewer** extension to run interactive queries and export charts.

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `ollama` | API key or token for LLM API |
| `OPENAI_BASE_URL` / `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL for LLM inference |
| `LLM_PROVIDER` | `ollama` | Default LLM provider (`ollama`, `openai`, `azure`, `deepseek`, `groq`) |
| `LLM_WEIGHTS_DIGEST` | *(auto-detected)* | Optional override for model weights SHA256 digest in W3C PROV |
| `JABUTI_PG_HOST` | `jabuti-postgres` | PostgreSQL hostname inside Docker network |
| `JABUTI_PG_PORT` | `5432` | PostgreSQL port |
| `JABUTI_DB_DUMP_SHA256` | *(auto-detected)* | Optional override for PostgreSQL dump SHA256 digest in W3C PROV |
| `SPIDER_DOCKER_NETWORK` | `spider-net` | Bridge network connecting agent and database |

---

## 🐛 Debugging & Troubleshooting

### 1. Run Unit & Integration Tests
Verify W3C PROV generation, latency/token instrumentation, export syntax classification, single-task failure handling, and AkôFlow YAML generation without needing a live LLM or database:
```bash
python3 test_provenance.py -v
python3 test_generate_akoflow_workflow.py -v
python3 test_verify_akoflow_run.py -v
python3 test_ingest_provenance_sqlite.py -v
```

### 2. Dry-Run Validation (`--dry_run`)
Test CLI parsing, task resolution, container naming, and output artifact creation (`result.csv`, `trajectory.json`, `metrics.json`, `task_provenance.json`) without launching a Docker container or calling an LLM:
```bash
python3 run_single_task.py \
    --task_id local_jabuti_000 \
    --model qwen2.5-coder:32b \
    --output_dir output/dry_run/local_jabuti_000 \
    --dry_run
```

### 3. Inspecting Task Logs, Trajectories & Provenance
When debugging a failed or low-accuracy task in `<output_dir>`:
- **Execution Log**: Check `<output_dir>/task.log` for full `DEBUG` logs (including raw LLM responses and Docker container setup).
- **Step-by-Step Trajectory**: Inspect `<output_dir>/trajectory.json` to see each ReAct turn (`thought`, `action`, `observation`).
- **Decomposed Latencies & Exit Status**: Inspect `<output_dir>/metrics.json` to compare LLM inference wait time (`t_llm_ms`) vs. database execution time (`t_db_ms`), check `export_syntax` (`COPY_TO_STDOUT` vs. `PSQL_PLAIN`), and verify `exit_code`.
- **W3C PROV Graph**: Inspect `<output_dir>/task_provenance.json` to verify `jabuti:status` (`SUCCESS`, `TIMEOUT`, `FAILURE`), `jabuti:is_partial`, and entity SHA256 checksums.

### 4. Re-running or Overwriting Tasks
By default, `run_single_task.py` skips tasks that already have a `result.csv` or `spider/result.json` in `--output_dir`:
- Pass `--overwriting` to force a fresh run and clean previous artifacts in `--output_dir`.
- Pass `--retry_failed` to re-run only tasks whose previous execution did not finish cleanly.

### 5. Common Infrastructure Checks
- **PostgreSQL Connectivity**:
  ```bash
  docker exec -it jabuti-postgres pg_isready -U postgres -d jabuti_sql
  ```
- **Docker Network Inspection**:
  Ensure `jabuti-postgres` is attached to `spider-net`:
  ```bash
  docker network inspect spider-net
  ```
- **Ollama / LLM Endpoint Availability**:
  ```bash
  curl -sf http://localhost:11434/v1/models | python3 -m json.tool
  ```
  *(Note: When running agent containers on Linux that connect to Ollama on the host, ensure Ollama binds to `0.0.0.0:11434` or pass `--base_url http://host.docker.internal:11434/v1`).*
- **Orphaned Sandbox Containers**:
  `run_single_task.py` destroys its container in a `finally` block and traps `SIGINT`/`SIGTERM`, but if a process was killed with `SIGKILL`, clean up leftover containers with:
  ```bash
  docker ps -a --filter "name=spider-jabuti-" -q | xargs -r docker rm -f
  ```

---

## 🛠️ Maintenance & Refactoring Notes

- **Function Logic Preservation**: Core action resolution, environment lifecycle, and controller bindings follow the standard Spider-Agent contract to ensure compatibility with future planned refactoring.
- **Isolation**: All JABUTI-SQL execution logic resides exclusively within this directory (`methods/spider-agent-jabuti`).
