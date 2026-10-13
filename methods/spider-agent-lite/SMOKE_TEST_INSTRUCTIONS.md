# JABUTI-SQL Smoke Test Instructions

This guide provides step-by-step instructions to verify the adapted **spider-agent-lite** pipeline on the JABUTI-SQL benchmark.

The smoke test runs against **Task 0 (`local_jabuti_000`)**, which queries the `instituicao` table (fully populated with all 610,321 rows in the current dump).

---

## Prerequisites

1. **Docker Desktop** running on your machine.
2. Python environment with dependencies installed:
   ```bash
   pip install psycopg2-binary pandas docker tqdm
   ```
3. An LLM API key set in your environment (or local model server running):
   ```bash
   export OPENAI_API_KEY="your-api-key"
   # If using a local model or Ollama, configure host in spider_agent/agent/models.py
   ```

---

## Step 1: Start the PostgreSQL Database

Navigate to the `jabuti_db` folder and start the PostgreSQL container:

```bash
cd methods/spider-agent-lite/jabuti_db
docker compose up -d
```

Verify that the container is running and healthy:
```bash
docker compose ps
```

*Expected output:* `jabuti-postgres` is `Up` and port `5432` is bound to `0.0.0.0:5432`.

---

## Step 2: Load the Schema and Data

Run the loader script to create all tables and load the complete tables:

```bash
python load_dump.py --host localhost --port 5432
```

*Note:* This takes ~10–15 seconds and populates the 5 complete tables (`catmat`, `endereco`, `fabricante`, `fornecedor`, `instituicao`).

*Expected output:*
```
Database loading finished in ~12 seconds!
Row counts in database:
  - catmat                        :     16,953 rows
  - endereco                      :    442,672 rows
  - fabricante                    :        751 rows
  - fornecedor                    :      1,083 rows
  - instituicao                   :    610,321 rows
```

*(Optional: To also load the ~9.36M rows of `instituicao_estoca_produto`, add `--include-partial-stock`)*

---

## Step 3: Generate the Benchmark Files & Gold Results

Return to `methods/spider-agent-lite` and generate the JSONL benchmark, per-task folders, and gold CSVs for the smoke test questions (0, 1, and 2):

```bash
cd ..
python setup_jabuti.py --generate-gold --instances 0,1,2 --pg-host localhost --pg-port 5432
```

*Expected output:*
- `examples/jabuti.jsonl` created with 69 tasks.
- 69 task folders created under `examples/local_jabuti_XXX/`.
- 3 gold CSV files created under `evaluation/gold/`:
  - `evaluation/gold/local_jabuti_000.csv`
  - `evaluation/gold/local_jabuti_001.csv`
  - `evaluation/gold/local_jabuti_002.csv`

---

## Step 4: Build the Agent Docker Image

Build the container image used by the agent during evaluation:

```bash
docker build -t spider_agent_jabuti-image spider_agent/images/spider_agent_jabuti-image/
```

Verify the image exists:
```bash
docker images | grep spider_agent_jabuti-image
```

---

## Step 5: Run the Agent on Task 0

Run the agent on instance 0 (`local_jabuti_000`):

```bash
python run.py \
    --model gpt-4o \
    --test_path examples/jabuti.jsonl \
    --pg_only \
    -i 0-1 \
    -s smoke_test1
```

*(Replace `gpt-4o` with your model identifier, e.g. `gpt-4o-mini`, `deepseek-chat`, etc.)*

What happens during execution:
1. `run.py` launches a container from `spider_agent_jabuti-image` attached to `spider-net`.
2. The agent inspects `ddl.sql` and uses `psql -c "..."` to query `jabuti_sql` on `jabuti-postgres`.
3. The agent saves its final answer to `result.csv` in `/workspace` and terminates.
4. Output trajectory and files are saved to `output/gpt-4o-smoke_test1/local_jabuti_000/`.

---

## Step 6: Extract the Submission Results

Extract the agent's prediction file:

```bash
python get_jabuti_submission_data.py \
    --experiment_suffix gpt-4o-smoke_test1 \
    --results_folder_name evaluation/predictions/gpt-4o-smoke_test1
```

*Expected output:*
```
Processed 1 JABUTI tasks → evaluation/predictions/gpt-4o-smoke_test1
Metadata saved to evaluation/predictions/gpt-4o-smoke_test1/submission_metadata.jsonl
```

Verify that `evaluation/predictions/gpt-4o-smoke_test1/local_jabuti_000.csv` was created.

---

## Step 7: Evaluate Against Ground Truth

Evaluate the predicted CSV against the gold result:

```bash
python evaluate_jabuti.py \
    --result_dir evaluation/predictions/gpt-4o-smoke_test1 \
    --gold_dir evaluation/gold \
    --jabuti_jsonl examples/jabuti.jsonl
```

*Expected output:*
```
Found 1 predictions to evaluate
  ✅ local_jabuti_000

======================================================================
JABUTI-SQL EVALUATION RESULTS
======================================================================

📊 Overall Accuracy: 1.0000 (1/1)

📈 Per Difficulty:
  Difficulty     Accuracy    Correct      Total
  ──────────── ────────── ────────── ──────────
  simple           1.0000          1          1

👤 Per Persona:
  Persona                               Accuracy    Correct      Total
  ─────────────────────────────────── ────────── ────────── ──────────
  Cidadã Leiga                            1.0000          1          1

======================================================================
📄 Full report saved to: evaluation/predictions/gpt-4o-smoke_test1/evaluation_report.json
```

---

## Troubleshooting

- **Container connection issues (`could not connect to server: Connection refused`)**:
  - Verify that `jabuti-postgres` is attached to `spider-net`:
    ```bash
    docker network inspect spider-net
    ```
  - Both `jabuti-postgres` and the task container must be on `spider-net`.
- **Permission errors on host (`FATAL: role "datalake_user" does not exist`)**:
  - Re-run `python load_dump.py` to ensure `datalake_user` is created.
- **Stopping the database when done**:
  ```bash
  cd methods/spider-agent-lite/jabuti_db
  docker compose down
  ```
