# JABUTI-SQL Smoke Test Instructions

This guide provides step-by-step instructions to verify the **spider-agent-jabuti** pipeline on the JABUTI-SQL benchmark.

The smoke test runs against the **3-persona trio for Question 1 (Tasks 0, 1, and 2 — `local_jabuti_000`, `001`, `002`)**, which queries the `instituicao` table (fully populated with all 610,321 rows in the standard database setup).

This verifies:
- End-to-end container networking (`spider-net`) and PostgreSQL execution (`jabuti_sql`).
- All 3 user personas (*Cidadã Leiga*, *Analista de Dados em Saúde*, *Médico Gestor Hospitalar*).
- The **Semantic Consistency** evaluation metric (whether all 3 persona variants of the same query produce the correct answer).

---

## Prerequisites

1. **Docker Desktop** running on your machine.
2. Python environment with dependencies installed:
   ```bash
   pip install -r requirements.txt
   ```
3. An LLM backend running (e.g. Ollama with `gpt-qwen-coder` on `http://localhost:11434` or OpenAI API key).

---

## Step 1: Verify PostgreSQL Database

Ensure the PostgreSQL container is running:
```bash
cd jabuti_db
docker compose up -d
docker compose ps
```

*Expected output:* `jabuti-postgres` is `Up` and port `5432` is bound to `0.0.0.0:5432`.

If data is not yet loaded, run:
```bash
python load_dump.py --host localhost --port 5432
cd ..
```

---

## Step 2: Build the Agent Docker Image

Ensure the task container image is built:
```bash
docker build -t spider_agent_jabuti-image spider_agent/images/spider_agent_jabuti-image/
```

Verify that the image exists:
```bash
docker images | grep spider_agent_jabuti-image
```

---

## Step 3: Run the Agent on the 3 Smoke Test Tasks

Run the agent on tasks 0, 1, and 2 (`local_jabuti_000`, `001`, `002`). You can pass raw local model names directly (e.g. `qwen2.5-coder:32b` or `devstral-small-2:24b`) without prepending `gpt-`:

```bash
python run.py \
    --model qwen2.5-coder:32b \
    -i 0-3 \
    -s smoke_test
```
*(Legacy alias `gpt-qwen-coder` is also supported for backward compatibility).*

> **Task selection notes:**
> - `-i 0-3` is a Python slice `[0:3]`, executing tasks 0, 1, and 2.
> - `--test_path` defaults to `./examples/jabuti.jsonl` and `--pg_only` is enabled by default.
> - Output trajectories and answers are saved under `output/<model_name>-smoke_test/local_jabuti_XXX/` (colons in model tags are safely sanitized to underscores).

---

## Step 4: Extract Submission Results

Extract the agent's prediction files into standard evaluation format:

```bash
python get_jabuti_submission_data.py \
    --experiment_suffix gpt-qwen-coder-smoke_test \
    --results_folder_name evaluation/predictions/gpt-qwen-coder-smoke_test
```

*Expected output:*
```
Processed 3 JABUTI tasks → evaluation/predictions/gpt-qwen-coder-smoke_test
Metadata saved to evaluation/predictions/gpt-qwen-coder-smoke_test/submission_metadata.jsonl
```

---

## Step 5: Evaluate Against Ground Truth

Evaluate the predicted CSVs against the gold results:

```bash
python evaluate_jabuti.py \
    --result_dir evaluation/predictions/gpt-qwen-coder-smoke_test \
    --gold_dir evaluation/gold \
    --jabuti_jsonl examples/jabuti.jsonl
```

*Expected output:*
```
Found 3 predictions to evaluate
  ✅ local_jabuti_000
  ✅ local_jabuti_001
  ✅ local_jabuti_002

======================================================================
JABUTI-SQL EVALUATION RESULTS
======================================================================

📊 Overall Accuracy: 1.0000 (3/3)

📈 Per Difficulty:
  Difficulty     Accuracy    Correct      Total
  ──────────── ────────── ────────── ──────────
  simple           1.0000          3          3

👤 Per Persona:
  Persona                               Accuracy    Correct      Total
  ─────────────────────────────────── ────────── ────────── ──────────
  Cidadã Leiga                            1.0000          1          1
  Analista de Dados em Saúde              1.0000          1          1
  Médico Gestor Hospitalar                1.0000          1          1

🔗 Semantic Consistency (parent groups):
  Total groups:           1
  Fully correct (all 3):  1 (1.0000)
  Partially correct (≥1): 1 (1.0000)

======================================================================
📄 Full report saved to: evaluation/predictions/gpt-qwen-coder-smoke_test/evaluation_report.json
```

---

## Optional: 6-Task Smoke Test (Adding Multi-Table Joins)

To test join capabilities across multiple tables (`instituicao` + `endereco`):

```bash
python run.py \
    --model gpt-qwen-coder \
    -i 0,1,2,21,22,23 \
    -s smoke_join
```

Extract and evaluate:
```bash
python get_jabuti_submission_data.py --experiment_suffix gpt-qwen-coder-smoke_join --results_folder_name evaluation/predictions/gpt-qwen-coder-smoke_join
python evaluate_jabuti.py --result_dir evaluation/predictions/gpt-qwen-coder-smoke_join --gold_dir evaluation/gold --jabuti_jsonl examples/jabuti.jsonl
```

---

## Troubleshooting

- **Container connection issues (`could not connect to server: Connection refused`)**:
  - Verify that `jabuti-postgres` is attached to `spider-net`:
    ```bash
    docker network inspect spider-net
    ```
- **Stopping database when finished**:
  ```bash
  cd jabuti_db
  docker compose down
  ```
