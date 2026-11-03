# Spider-Agent-JABUTI

An autonomous agent framework adapted from Spider 2.0 to evaluate LLMs on the **JABUTI-SQL** benchmark in isolated Docker environments.

---

## 📌 Overview

**Spider-Agent-JABUTI** brings the agentic execution paradigm of Spider 2.0 to the **JABUTI-SQL** Brazilian healthcare database benchmark. JABUTI-SQL features complex real-world healthcare data stored in PostgreSQL, with 69 natural language tasks in Brazilian Portuguese asked across three distinct personas.

### Key Capabilities
- **PostgreSQL Native Support**: Runs queries directly against a standing PostgreSQL container (`jabuti-postgres`) loaded with the full schema and data.
- **Dockerized Agent Execution**: Each task runs inside an isolated container (`spider_agent_jabuti-image`) connected via a shared bridge network (`spider-net`).
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
├── setup_jabuti.py                    # Benchmark setup and gold standard generation
├── get_jabuti_submission_data.py      # Result extractor for predictions
├── evaluate_jabuti.py                 # Ground truth evaluation and stratified scoring
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

## 📊 Evaluation & Metrics

### 1. Extract Prediction CSVs
After running `run.py`, collect and normalize the output predictions:
```bash
python get_jabuti_submission_data.py \
    --experiment_suffix gpt-qwen-coder-smoke_trio \
    --results_folder_name evaluation/predictions/gpt-qwen-coder-smoke_trio
```

### 2. Run Evaluation
Compare predictions against ground truth gold CSVs:
```bash
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

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `ollama` | API key or token for LLM API |
| `JABUTI_PG_HOST` | `jabuti-postgres` | PostgreSQL hostname inside Docker network |
| `JABUTI_PG_PORT` | `5432` | PostgreSQL port |
| `SPIDER_DOCKER_NETWORK` | `spider-net` | Bridge network connecting agent and database |

---

## 🛠️ Maintenance & Refactoring Notes

- **Function Logic Preservation**: Core action resolution, environment lifecycle, and controller bindings follow the standard Spider-Agent contract to ensure compatibility with future planned refactoring.
- **Isolation**: All JABUTI-SQL execution logic resides exclusively within this directory (`methods/spider-agent-jabuti`).
