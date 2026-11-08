# AkôFlow Remote Deployment & Execution Guide for JABUTI-SQL

This document provides step-by-step instructions for deploying, executing, and verifying the **JABUTI-SQL** autonomous agent benchmark as a parallel scientific workflow on a remote server using **AkôFlow**.

---

## 1. Architecture Overview

The integration models the 69 JABUTI-SQL benchmark tasks as a parallel fan-out / fan-in Directed Acyclic Graph (DAG):

```
                           ┌─────────────────────────┐
                           │     preflight-check     │
                           │ (Verify DB & LLM Health)│
                           └────────────┬────────────┘
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            ▼                           ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│ task-local_jabuti_000 │   │ task-local_jabuti_001 │   │ task-local_jabuti_068 │
│  (run_single_task.py) │   │  (run_single_task.py) │   │  (run_single_task.py) │
└───────────┬───────────┘   └───────────┬───────────┘   └───────────┬───────────┘
            │                           │                           │
            └───────────────────────────┼───────────────────────────┘
                                        ▼
                           ┌─────────────────────────┐
                           │       evaluation        │
                           │  (evaluate_jabuti.py)   │
                           └─────────────────────────┘
```

Each task activity writes standardized artifacts to `/shared/output/<model>/<task_id>/`:
- `result.csv`: Prediction table in RFC 4180 CSV format.
- `trajectory.json`: Step-by-step ReAct cognitive trace.
- `metrics.json`: Decomposed wall-clock latencies (`t_total_ms`, `t_llm_ms`, `t_db_ms`), token usage, and `export_syntax` (`COPY_TO_STDOUT` vs. `PSQL_PLAIN`).
- `task_provenance.json`: W3C PROV-JSON lineage graph.

---

## 2. Remote Server Setup (AkôFlow Engine, PostgreSQL & Images)

### 2.1 Provision the JABUTI-SQL Analytical Database (`jabuti-postgres`)

1. Create the shared Docker bridge network `spider-net` and launch the PostgreSQL 16 container:
   ```bash
   cd methods/spider-agent-jabuti/jabuti_db
   docker compose up -d
   docker compose ps
   ```

2. Load the JABUTI-SQL schema and data dump:
   ```bash
   python3 load_dump.py --host localhost --port 5432
   # Add --full if loading the 143M-row instituicao_estoca_produto table
   cd ..
   ```

3. **(Recommended for Parallel Sweeps)** Provision a read-only PostgreSQL role so concurrent agent containers cannot accidentally mutate or drop tables:
   ```bash
   docker exec -i jabuti-postgres psql -U postgres -d jabuti_sql <<'SQL'
   DO $$
   BEGIN
     IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'jabuti_reader') THEN
       CREATE ROLE jabuti_reader WITH LOGIN PASSWORD 'spider_readonly';
     END IF;
   END
   $$;
   GRANT CONNECT ON DATABASE jabuti_sql TO jabuti_reader;
   GRANT USAGE ON SCHEMA public TO jabuti_reader;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO jabuti_reader;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO jabuti_reader;
   ALTER ROLE jabuti_reader SET default_transaction_read_only = on;
   SQL
   ```

### 2.2 Build the Task Sandbox & Runner Docker Images

1. **Inner Task Sandbox Image (`spider_agent_jabuti-image`)** — spawned dynamically per task (`spider-jabuti-<model>-<task_id>-<uuid>`):
   ```bash
   cd methods/spider-agent-jabuti
   docker build -t spider_agent_jabuti-image spider_agent/images/spider_agent_jabuti-image/
   ```

2. **Outer AkôFlow Activity Runner Image (`spider-agent-runner:latest`)** — executes `run_single_task.py` and `evaluate_jabuti.py` inside AkôFlow activities:
   ```bash
   docker build -t spider-agent-runner:latest -f - . <<'DOCKERFILE'
   FROM python:3.11-slim
   RUN apt-get update && apt-get install -y --no-install-recommends \
       postgresql-client curl docker.io ca-certificates \
       && rm -rf /var/lib/apt/lists/*
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt pandas psycopg2-binary
   COPY . /app
   DOCKERFILE
   ```
   > **Note on Docker-Out-of-Docker (DooD)**: Because `run_single_task.py` spawns an isolated `spider_agent_jabuti-image` sandbox container via the Docker SDK, AkôFlow activity containers running `spider-agent-runner:latest` must mount the host Docker socket (`/var/run/docker.sock:/var/run/docker.sock`) and share `/shared/output` at the identical host path `/shared/output`.

### 2.3 Deploy the AkôFlow Engine & Provenance Metadata Store

1. Start AkôFlow's internal PostgreSQL provenance database (separate from `jabuti-postgres` or hosted in a dedicated `akoflow_prov` database):
   ```bash
   docker run -d \
     --name akoflow-postgres \
     --network spider-net \
     -e POSTGRES_DB=akoflow_prov \
     -e POSTGRES_USER=akoflow \
     -e POSTGRES_PASSWORD=akoflow_secret \
     -p 5433:5432 \
     -v akoflow_pgdata:/var/lib/postgresql/data \
     postgres:16-alpine
   ```

2. Configure and launch the AkôFlow Server daemon (`akoflow-server`):
   ```bash
   export AKOFLOW_DB_DSN="postgres://akoflow:akoflow_secret@localhost:5433/akoflow_prov?sslmode=disable"
   export AKOFLOW_RUNTIME="docker"   # or "kubernetes" / "singularity" depending on cluster
   export AKOFLOW_LISTEN_ADDR="0.0.0.0:8080"

   # Start the AkôFlow orchestrator service
   akoflow-server --port 8080 --db-dsn "$AKOFLOW_DB_DSN"
   ```

3. Configure the LLM Inference Endpoint (Ollama or vLLM):
   - **Ollama (parallel worker pool)**:
     ```bash
     export OLLAMA_HOST="0.0.0.0:11434"
     export OLLAMA_NUM_PARALLEL=8
     ollama serve &
     ollama pull qwen2.5-coder:32b
     ```
   - **vLLM (OpenAI-compatible server)**:
     ```bash
     vllm serve Qwen/Qwen2.5-Coder-32B-Instruct --port 8000 --max-num-seqs 16
     ```

---

## 3. Shared Volume Mounting (`/shared/output`)

All AkôFlow task activities and the final `evaluation` activity read and write artifacts under `/shared/output`.

### 3.1 Single-Node Remote Server Preparation
Create `/shared/output` on the remote host with permissions accessible to the Docker daemon and runner containers:
```bash
sudo mkdir -p /shared/output
sudo chown -R "$USER:$USER" /shared/output
sudo chmod -R 775 /shared/output
```

### 3.2 Option A: NFSv4 Shared Mount (Multi-Node Cluster / Worker Pool)
When AkôFlow dispatches activities across multiple worker nodes:

1. **On the NFS Server (Storage Host `10.0.0.10`)**:
   ```bash
   sudo apt-get update && sudo apt-get install -y nfs-kernel-server
   sudo mkdir -p /srv/nfs/jabuti_output
   sudo chown nobody:nogroup /srv/nfs/jabuti_output
   sudo chmod 777 /srv/nfs/jabuti_output

   echo "/srv/nfs/jabuti_output 10.0.0.0/24(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports
   sudo exportfs -ra
   sudo systemctl enable --now nfs-kernel-server
   ```

2. **On Every AkôFlow Worker Node & Client**:
   ```bash
   sudo apt-get update && sudo apt-get install -y nfs-common
   sudo mkdir -p /shared/output
   sudo mount -t nfs4 10.0.0.10:/srv/nfs/jabuti_output /shared/output

   # Persist across reboots in /etc/fstab:
   echo "10.0.0.10:/srv/nfs/jabuti_output /shared/output nfs4 defaults,_netdev 0 0" | sudo tee -a /etc/fstab
   ```

### 3.3 Option B: SSHFS Mount (Local Workstation ↔ Remote Server Inspection)
To inspect `/shared/output` and run `verify_akoflow_run.py` directly from your local workstation without manually copying files:

```bash
# On local workstation (macOS / Linux):
sudo mkdir -p /shared/output
sudo chown "$USER" /shared/output

sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 \
    user@remote-akoflow-server:/shared/output /shared/output
```
To unmount when finished:
```bash
umount /shared/output   # or: fusermount -u /shared/output on Linux
```

---

## 4. Generating & Submitting the Workflow YAML

### 4.1 Generate the AkôFlow Workflow Specification
Use `generate_akoflow_workflow.py` to generate either a 3-task smoke test workflow or the full 69-task benchmark sweep:

```bash
cd methods/spider-agent-jabuti

# 1. Generate 3-instance smoke test DAG (tasks 000, 001, 002)
python3 generate_akoflow_workflow.py \
    --model qwen2.5-coder:32b \
    --instances 0,1,2 \
    --output_yaml akoflow/workflow_smoke.yaml

# 2. Generate full 69-instance benchmark DAG (tasks 000..068)
python3 generate_akoflow_workflow.py \
    --model qwen2.5-coder:32b \
    --instances all \
    --output_yaml akoflow/workflow_jabuti.yaml
```

### 4.2 Submit via AkôFlow CLI
```bash
# Submit the 3-task smoke test workflow
akoflow apply -f akoflow/workflow_smoke.yaml

# Or submit the full 69-task workflow
akoflow apply -f akoflow/workflow_jabuti.yaml
```

### 4.3 Submit via AkôFlow REST API
If submitting directly over HTTP to the AkôFlow server (`http://remote-akoflow-server:8080`):
```bash
curl -X POST http://remote-akoflow-server:8080/workflows/ \
    -H "Content-Type: application/x-yaml" \
    --data-binary @akoflow/workflow_smoke.yaml
```

---

## 5. Monitoring Execution & Pulling Provenance Graphs

### 5.1 Monitor Workflow & Activity Progress
```bash
# Check overall workflow status via CLI
akoflow get workflows -n escience-jabuti

# Inspect individual activity statuses (preflight-check, task-local_jabuti_XXX, evaluation)
akoflow get activities -n escience-jabuti -w jabuti-sql-benchmark-qwen2.5-coder-32b

# Stream logs for a specific task activity
akoflow logs -n escience-jabuti task-local_jabuti_000

# Or poll status via REST API
curl -s http://remote-akoflow-server:8080/workflows/escience-jabuti/jabuti-sql-benchmark-qwen2.5-coder-32b | python3 -m json.tool
```

### 5.2 Run the Verification Harness (`verify_akoflow_run.py`)
Once the workflow finishes, run `verify_akoflow_run.py` against the output directory to validate artifact integrity (`result.csv`, `metrics.json`, `task_provenance.json`), aggregate decomposed latencies ($T_{LLM}$ vs. $T_{DB}$), and optionally cross-check AkôFlow's `/provenance/` REST endpoint:

```bash
# Local / Shared Volume Verification (3-instance smoke test):
python3 methods/spider-agent-jabuti/akoflow/verify_akoflow_run.py \
    --results_dir /shared/output/qwen2.5-coder:32b \
    --expected_tasks 0,1,2 \
    --output_json /shared/output/qwen2.5-coder:32b/verification_report.json

# Full Verification + Remote AkôFlow /provenance/ API Cross-Check:
python3 methods/spider-agent-jabuti/akoflow/verify_akoflow_run.py \
    --results_dir /shared/output/qwen2.5-coder:32b \
    --expected_tasks all \
    --akoflow_api_url http://remote-akoflow-server:8080 \
    --workflow_name jabuti-sql-benchmark-qwen2.5-coder-32b \
    --namespace escience-jabuti \
    --require_api \
    --output_json /shared/output/qwen2.5-coder:32b/verification_report.json
```

### 5.3 Pull Final Provenance Graphs & Evaluation Reports

1. **Pull AkôFlow Engine-Level Provenance Record**:
   ```bash
   curl -s "http://remote-akoflow-server:8080/provenance/?namespace=escience-jabuti&workflow=jabuti-sql-benchmark-qwen2.5-coder-32b" \
       -o /shared/output/qwen2.5-coder:32b/akoflow_engine_provenance.json
   ```

2. **Sync Full Artifact Bundle to Local Workstation (if not using SSHFS)**:
   ```bash
   rsync -avzP user@remote-akoflow-server:/shared/output/qwen2.5-coder:32b/ \
       ./output/akoflow_remote_qwen2.5-coder_32b/
   ```

3. **Inspect Stratified Accuracy Report**:
   The final `evaluation` activity automatically generates `/shared/output/<model>/evaluation_report.json` with overall accuracy, per-difficulty accuracy (`simple`, `medium`, `hard`), per-persona accuracy, and semantic group consistency.

