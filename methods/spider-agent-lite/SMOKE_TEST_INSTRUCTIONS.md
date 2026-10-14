# JABUTI-SQL Smoke Test Instructions

This guide provides step-by-step instructions to verify the adapted **spider-agent-lite** pipeline on the JABUTI-SQL benchmark.

The smoke test runs against the **3-persona trio for Question 1 (Tasks 0, 1, and 2 — `local_jabuti_000`, `001`, `002`)**, which queries the `instituicao` table (fully populated with all 610,321 rows in the current dump).

This verifies:
- End-to-end container networking and PostgreSQL execution.
- All 3 user personas (*Cidadã Leiga*, *Analista de Dados em Saúde*, *Médico Gestor Hospitalar*).
- The **Semantic Consistency** evaluation metric (whether all 3 persona variants of the same query produce the correct answer).

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

*Note:* This takes ~14 seconds and populates the 14 core tables (`catmat`, `endereco`, `fabricante`, `fornecedor`, `instituicao`, `leitos`, `macrorregiao_de_saude`, `mantenedora`, `mantenedora_compra_produto`, `municipio`, `produto`, `regiao_de_saude`, `regiao_do_brasil`, `unidade_federativa` — ~1.22M rows total), refreshing `mv_leitos_mais_recente`.

*Expected output:*
```
Database loading finished in ~14 seconds!
Row counts in database:
  - catmat                        :     16,953 rows
  - endereco                      :    442,672 rows
  - fabricante                    :        751 rows
  - fornecedor                    :      1,083 rows
  - instituicao                   :    610,321 rows
  - leitos                        :     86,147 rows
  - macrorregiao_de_saude         :        121 rows
  - mantenedora                   :      7,390 rows
  - mantenedora_compra_produto    :     26,215 rows
  - municipio                     :      5,570 rows
  - mv_leitos_mais_recente        :      7,369 rows
  - produto                       :     20,875 rows
  - regiao_de_saude               :        439 rows
  - regiao_do_brasil              :          5 rows
  - unidade_federativa            :         27 rows
  TOTAL ROWS                      :  1,225,938 rows
```

*(Optional: To also load the 143,009,579 rows of `instituicao_estoca_produto`, add `--full`)*

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

*(Note: To also include tasks 21, 22, and 23 for join testing, use `--instances 0,1,2,21,22,23`)*

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

## Step 5: Run the Agent on the Smoke Test Tasks

Run the agent on tasks 0, 1, and 2:

```bash
python run.py \
    --model gpt-4o \
    --test_path examples/jabuti.jsonl \
    --pg_only \
    -i 0-3 \
    -s smoke_test1
```

*(Replace `gpt-4o` with your model identifier, e.g. `gpt-4o-mini`, `gpt-qwen-coder`, etc.)*

> **Understanding `-i` task selection:**
> - `-i 0-3` is a Python slice `[0:3]`, running indices **0, 1, and 2** (`local_jabuti_000`, `001`, `002`).
> - You can also pass comma-separated indices, such as `-i 0,1,2` or `-i 0,1,2,21,22,23`.
> - To run a single task: `-i 0-1` or `--example_name local_jabuti_000`.

What happens during execution:
1. `run.py` launches a container for each task from `spider_agent_jabuti-image` attached to `spider-net`.
2. The agent inspects `ddl.sql` and uses `psql -c "..."` to query `jabuti_sql` on `jabuti-postgres`.
3. The agent saves its final answer to `result.csv` in `/workspace` and terminates.
4. Output trajectories and results are saved to `output/gpt-4o-smoke_test1/local_jabuti_XXX/`.

---

## Step 6: Extract the Submission Results

Extract the agent's prediction files:

```bash
python get_jabuti_submission_data.py \
    --experiment_suffix gpt-4o-smoke_test1 \
    --results_folder_name evaluation/predictions/gpt-4o-smoke_test1
```

*Expected output:*
```
Processed 3 JABUTI tasks → evaluation/predictions/gpt-4o-smoke_test1
Metadata saved to evaluation/predictions/gpt-4o-smoke_test1/submission_metadata.jsonl
```

Verify that predictions were extracted:
- `evaluation/predictions/gpt-4o-smoke_test1/local_jabuti_000.csv`
- `evaluation/predictions/gpt-4o-smoke_test1/local_jabuti_001.csv`
- `evaluation/predictions/gpt-4o-smoke_test1/local_jabuti_002.csv`

---

## Step 7: Evaluate Against Ground Truth

Evaluate the predicted CSVs against the gold results:

```bash
python evaluate_jabuti.py \
    --result_dir evaluation/predictions/gpt-4o-smoke_test1 \
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
📄 Full report saved to: evaluation/predictions/gpt-4o-smoke_test1/evaluation_report.json
```

---

## Expanding the Smoke Test to 6 Tasks (Adding Multi-Table Joins)

If you want a more rigorous smoke test that tests SQL `JOIN` capabilities across multiple tables, you can include **Tasks 21, 22, and 23 (`local_jabuti_021`, `022`, `023`)**.

These tasks join `instituicao` (610K rows) with `endereco` (442K rows) to filter institutions by address. Both tables are 100% complete in the database.

1. **Generate gold for all 6 tasks:**
   ```bash
   python setup_jabuti.py --generate-gold --instances 0,1,2,21,22,23 --pg-host localhost --pg-port 5432
   ```

2. **Run the 6 tasks:**
   ```bash
   python run.py \
       --model gpt-4o \
       --test_path examples/jabuti.jsonl \
       --pg_only \
       -i 0,1,2,21,22,23 \
       -s smoke_6tasks
   ```

3. **Extract & evaluate:**
   ```bash
   python get_jabuti_submission_data.py --experiment_suffix gpt-4o-smoke_6tasks --results_folder_name evaluation/predictions/gpt-4o-smoke_6tasks
   python evaluate_jabuti.py --result_dir evaluation/predictions/gpt-4o-smoke_6tasks --gold_dir evaluation/gold --jabuti_jsonl examples/jabuti.jsonl
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
