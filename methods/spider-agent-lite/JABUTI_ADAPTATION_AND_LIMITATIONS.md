# JABUTI-SQL Benchmark Adaptation & Limitations Report

This document details the adaptation of **spider-agent-lite** for the **JABUTI-SQL** benchmark, all changes and bug fixes implemented, the current limitations of the dataset dump, and recommended next steps.

---

## 1. Executive Summary

JABUTI-SQL (*Joint Annotated Benchmark for User-centric Text-to-SQL In Real Health Data*) is a Brazilian text-to-SQL benchmark consisting of 69 natural language questions across three distinct user personas (*Cidadã Leiga*, *Analista de Dados em Saúde*, *Médico Gestor Hospitalar*) querying a PostgreSQL database of DATASUS public health records (15 relational tables).

Spider-agent-lite was adapted to support JABUTI-SQL as a local PostgreSQL benchmark without invasive modifications to core agent actions. By hosting PostgreSQL in a persistent, shared container and leveraging the `Bash` action with `psql`, the agent interacts with the database natively while preserving full compatibility with Spider 2.0.

---

## 2. Summary of Changes and Fixes

### A. Database Service & Loading Architecture (`jabuti_db/`)
- **`jabuti_db/docker-compose.yml`**: Provisions a dedicated PostgreSQL 16 service (`jabuti-postgres`) on a shared Docker bridge network (`spider-net`), exposing port `5432` and mounting persistent storage `jabuti_pgdata`. This avoids the fatal flaw of re-creating and loading the database inside each ephemeral task container.
- **`jabuti_db/load_dump.py`**:
  - Pre-creates the `datalake_user` role required by `ddl.sql` table ownership statements.
  - Safely handles pg_dump 16.10 headers (`\restrict`) that break older clients.
  - Executes `ddl.sql` to instantiate all 15 tables, sequences, constraints, and views (`v_endereco_completo`, `v_produto_completo`, `mv_estoque_mais_recente`, `mv_leitos_mais_recente`).
  - Streams `COPY` data blocks from `dump.sql` directly into PostgreSQL.
  - Automatically recovers from truncated `COPY` blocks by discarding broken partial lines and terminating with `\.`.
  - Supports loading only the 5 complete tables (~1.07M rows in ~10 seconds) or including the partial stock records.

### B. Setup & Data Preparation (`setup_jabuti.py`)
- **Dynamic Path Resolution**: Checks both local repository copy (`Spider2/JABUTI-SQL/`) and sibling directory (`../../../JABUTI-SQL/`).
- **Semantic Triple Grouping (`parent_id`)**: In `benchmark.json`, questions are structured in sets of 3 (the same query phrased for three personas), but `parent_id` was stored as `null`. `setup_jabuti.py` now maps `parent_id = id // 3`, allowing semantic consistency across personas to be evaluated.
- **Selective Gold Generation (`--instances`)**: Added `--instances` flag to `setup_jabuti.py` to allow generating gold CSVs for specific tasks (e.g., `--instances 0,1,2,21,22,23`) without failing on missing tables.
- **Per-Task Folders**: Generates `examples/local_jabuti_XXX/` containing `ddl.sql`, `README.md` (with PostgreSQL schema instructions and table volume warnings), and data dictionary PDF.

### C. Agent Runner & Environment (`run.py` & `spider_agent/`)
- **Docker Image Correction**: Fixed a bug where `run.py` specified `spider_agent_postgres-image` (which initialized a different database `xlangdb`). It now routes PostgreSQL tasks to `spider_agent_jabuti-image`.
- **Docker Network & Env Injection**: In `run.py`, when `task_type == 'pg'`, the container attaches to `--docker_network` (default `spider-net`) and receives `PGHOST`, `PGPORT`, `PGUSER`, and `PGDATABASE`.
- **Task ID Matcher Bug Fix**: Fixed a bug in `run.py` where `--example_name` matched against `task["id"]` instead of `task["instance_id"]`, which caused `KeyError: 'id'`.
- **Client Image (`spider_agent_jabuti-image`)**: Updated `Dockerfile` and `init.sh` to install PostgreSQL client tools and configure default environment variables (`/etc/profile.d/jabuti.sh`) so commands like `psql -c "..."` connect to the database service seamlessly.

### D. Submission Extraction & Evaluation (`get_jabuti_submission_data.py` & `evaluate_jabuti.py`)
- **Metadata Enrichment**: Preserves `difficulty`, `persona`, and `parent_id` during extraction.
- **Selective Gold Generation in Evaluator**: Added `--instances` to `evaluate_jabuti.py` to generate gold CSVs for targeted subsets on-the-fly.
- **Stratified Metrics**: Evaluates predictions using order-insensitive column-vector matching (tolerance 1e-2 for numerics), reporting:
  - Overall accuracy
  - Per-difficulty accuracy (`simple`, `medium`, `hard`)
  - Per-persona accuracy
  - Parent query semantic consistency (all 3 variants correct vs. at least 1 correct)

### E. Repository Cleanliness (`.gitignore`)
- Completely ignored `JABUTI-SQL/` and `dump.sql` (556 MB) to prevent accidental commits over GitHub file size limits.

---

## 3. Current Limitations

### 1. Truncated Database Dump (`dump.sql`)
The official `dump.sql` file downloaded from Hugging Face (`BotelhoMS/JABUTI-SQL`, size `556,269,568` bytes) is **incomplete at the source**:
- It terminates prematurely at line 9,368,406 during the `COPY` block for `instituicao_estoca_produto` (~9.36M of the reported 143M rows).
- The subsequent tables have **0 data rows**:
  - `leitos` (reported: 86,147 rows)
  - `mantenedora` (reported: 7,390 rows)
  - `mantenedora_compra_produto` (reported: 26,215 rows)
  - `municipio` (reported: 5,570 rows)
  - `produto` (reported: 20,875 rows)
  - `regiao_de_saude` (reported: 439 rows)
  - `macrorregiao_de_saude` (reported: 121 rows)
  - `unidade_federativa` (reported: 27 rows)
  - `regiao_do_brasil` (reported: 5 rows)
- Because the dump was cut off, the post-data commands (such as primary keys, foreign key constraints, secondary indexes, and view refreshes) were never written to `dump.sql`. Our `load_dump.py` addresses this by applying `ddl.sql` first.

### 2. Question Feasibility with the Current Dump
Based on table analysis across all 69 gold queries in `benchmark.json`:
- **6 questions are 100% answerable with exact ground truth**:
  - `local_jabuti_000`, `001`, `002`: Active institutions grouped by management type (`instituicao` table — 610,321 rows present).
  - `local_jabuti_021`, `022`, `023`: Institutions filtered by address details (`instituicao` + `endereco` tables — 442,672 rows present).
- **6 questions run against partial data**:
  - `local_jabuti_009`, `010`, `011`, `024`, `025`, `026`: Query `instituicao_estoca_produto`. They will execute without SQL error, but aggregate counts will reflect only the 9.36M loaded rows rather than 143M rows.
- **57 questions are blocked**:
  - Require missing tables (`leitos`, `mantenedora_compra_produto`, `municipio`, etc.) or views depending on them (`v_endereco_completo`). Queries will execute but return empty result sets.

3. **Upstream Spider2 Parser Fix (`Bash` Action)**:
   - In `spider-agent-lite/spider_agent/agent/action.py`, the original parser used `re.findall(r'Bash\(code=(.*?)\)', text)`, which was non-greedy and prematurely clipped shell commands at the first internal closing parenthesis `)` (e.g. `COUNT(*)`, subqueries, or python one-liners).
   - We updated `action.py` to match escaped quotes and balanced parenthesis bounds (backporting the fix the authors previously made in `spider-agent-dbt`).
   - We also sanitized Docker container names in `run.py` to replace `:` and invalid characters with `-`, preventing Docker API 400 Bad Request errors when using tagged model names like `qwen2.5-coder:32b`.

---

## 4. Next Steps

1. **Perform Smoke Test**:
   - Run the smoke test instructions outlined in `SMOKE_TEST_INSTRUCTIONS.md` on instances `000`, `001`, and `002` to confirm the entire loop (Docker → agent → PostgreSQL → extraction → evaluation) functions as expected.
2. **Contact JABUTI-SQL Authors**:
   - Open an issue or discussion on Hugging Face (`BotelhoMS/JABUTI-SQL`) or Zenodo (`10.5281/zenodo.21048827`).
   - Request an updated, complete database export.
   - *Recommendation*: Suggest exporting using PostgreSQL custom format (`pg_dump -Fc -Z 6 -d jabuti_sql -f jabuti_sql.dump`), which compresses ~10x smaller than raw text and allows multi-threaded restoration (`pg_restore -j 4`).
3. **Full Benchmark Execution**:
   - Once the complete dump is received, re-run `python load_dump.py` and generate all 69 gold CSVs with `python setup_jabuti.py --generate-gold`.
   - Run `python run.py --test_path examples/jabuti.jsonl --pg_only -s full_eval` across all 69 questions.
