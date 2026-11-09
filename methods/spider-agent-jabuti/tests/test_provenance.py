import argparse
import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import MagicMock, patch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
for p in (PARENT_DIR, os.path.join(PARENT_DIR, "akoflow"), os.path.join(PARENT_DIR, "provenance")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Mock optional external SDK dependencies if not installed in the bare host Python
for mod_name in [
    "docker",
    "docker.models",
    "docker.models.containers",
    "docker.client",
    "docker.errors",
    "gymnasium",
    "openai",
    "dashscope",
    "groq",
    "google",
    "google.generativeai",
    "tiktoken",
    "requests",
    "pandas",
    "yaml",
]:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        if mod_name == "gymnasium":
            m.Env = object
        elif mod_name == "docker.models.containers":
            m.Container = object
        elif mod_name == "docker.client":
            m.DockerClient = object
        elif mod_name == "docker.errors":
            m.ImageNotFound = Exception
            m.NotFound = Exception
            m.APIError = Exception
        elif mod_name == "openai":
            m.AzureOpenAI = object
            m.OpenAI = object
        elif mod_name == "groq":
            m.Groq = object
        sys.modules[mod_name] = m

from spider_agent.agent.provenance import (
    calculate_file_hash,
    detect_export_syntax,
    build_w3c_prov_record,
)
from spider_agent.agent.action import Bash, Terminate, CreateFile
from spider_agent.agent.agents import PromptAgent
import run_single_task


class TestProvenanceAndTelemetry(unittest.TestCase):
    def test_calculate_file_hash(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("id,total\n1,42\n")
            tmp_path = f.name
        try:
            digest = calculate_file_hash(tmp_path)
            self.assertEqual(len(digest), 64)
            # Deterministic check
            self.assertEqual(digest, calculate_file_hash(tmp_path))
        finally:
            os.remove(tmp_path)

    def test_detect_export_syntax(self):
        # 1. COPY ... TO STDOUT redirected to result.csv
        actions_copy = [
            Bash(code="psql -U postgres jabuti_sql -c '\\dt'"),
            Bash(
                code='psql -U postgres jabuti_sql -c "COPY (SELECT * FROM instituicao) TO STDOUT WITH CSV HEADER" > result.csv'
            ),
            Bash(code="head -n 5 result.csv"),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_copy), "COPY_TO_STDOUT")

        # 2. \copy ... TO STDOUT redirected to result.csv
        actions_copy_meta = [
            Bash(
                code='psql -U postgres jabuti_sql -c "\\copy (SELECT * FROM instituicao) TO STDOUT WITH CSV HEADER" > result.csv'
            ),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_copy_meta), "COPY_TO_STDOUT")

        # 3. \copy ... TO 'result.csv' directly
        actions_copy_file = [
            Bash(
                code="psql -U postgres jabuti_sql -c \"\\copy (SELECT * FROM instituicao) TO 'result.csv' WITH CSV HEADER\""
            ),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_copy_file), "COPY_TO_STDOUT")

        # 4. psql plain query redirected with > result.csv
        actions_psql_plain = [
            Bash(code="psql -U postgres jabuti_sql -c '\\dt'"),
            Bash(
                code="psql -U postgres jabuti_sql -A -F ',' -c \"SELECT * FROM instituicao;\" > result.csv"
            ),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_psql_plain), "PSQL_PLAIN")

        # 5. psql plain query with -o result.csv
        actions_psql_dash_o = [
            Bash(
                code='psql -U postgres jabuti_sql -c "SELECT * FROM instituicao" -o result.csv'
            ),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_psql_dash_o), "PSQL_PLAIN")

        # 6. Exploratory psql query followed by scalar answer (MUST NOT be classified as PSQL_PLAIN)
        actions_exploratory_only = [
            Bash(code="psql -U postgres jabuti_sql -c '\\dt'"),
            Terminate(output="42"),
        ]
        self.assertEqual(detect_export_syntax(actions_exploratory_only), "NONE")

        # 7. Non-psql export to result.csv (e.g. echo or Python)
        actions_echo = [
            Bash(code='echo "header\nval" > result.csv'),
            Terminate(output="result.csv"),
        ]
        self.assertEqual(detect_export_syntax(actions_echo), "NONE")

        # 8. Empty or non-export actions
        actions_none = [
            Bash(code="ls -la"),
            Terminate(output="42"),
        ]
        self.assertEqual(detect_export_syntax(actions_none), "NONE")

    def test_build_w3c_prov_record_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "result.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("tipo,total\nM,10\nE,5\n")

            task_config = {
                "instance_id": "local_jabuti_000",
                "question": "Quantas instituições?",
                "parent_id": 0,
                "persona": "Analista de Dados em Saúde",
                "difficulty": "simple",
            }
            prov = build_w3c_prov_record(
                task_config=task_config,
                model="qwen2.5-coder:32b",
                provider="ollama",
                temperature=0.5,
                top_p=0.9,
                output_dir=tmpdir,
                container_name="spider-jabuti-qwen-local_jabuti_000-123456",
                image_name="spider_agent_jabuti-image",
                step_count=3,
                total_duration_ms=1500.5,
                t_llm_ms=1100.2,
                t_db_ms=350.1,
                tokens_prompt=800,
                tokens_completion=120,
                tokens_total=920,
                exit_code=0,
                start_time_iso="2026-10-29T12:00:00Z",
                end_time_iso="2026-10-29T12:00:02Z",
                has_result_csv=True,
                export_syntax="COPY_TO_STDOUT",
                model_digest="sha256:abcdef",
                db_dump_hash="sha256:123456",
            )

            # Verify top-level W3C PROV sections
            for key in [
                "prefix",
                "entity",
                "activity",
                "agent",
                "wasAssociatedWith",
                "used",
                "wasGeneratedBy",
                "wasDerivedFrom",
            ]:
                self.assertIn(key, prov)

            # Verify Entities
            entities = prov["entity"]
            self.assertIn("jabuti:task:local_jabuti_000", entities)
            self.assertIn("jabuti:db:jabuti_sql", entities)
            self.assertIn("jabuti:model:qwen2.5-coder-32b", entities)
            self.assertIn("jabuti:prediction:qwen2.5-coder-32b:local_jabuti_000", entities)
            self.assertIn("jabuti:metrics:qwen2.5-coder-32b:local_jabuti_000", entities)

            task_entity = entities["jabuti:task:local_jabuti_000"]
            self.assertEqual(task_entity["jabuti:parent_id"], "0")
            self.assertEqual(task_entity["jabuti:persona"], "Analista de Dados em Saúde")
            self.assertEqual(task_entity["jabuti:difficulty"], "simple")

            db_entity = entities["jabuti:db:jabuti_sql"]
            self.assertEqual(db_entity["jabuti:dump_sha256"], "sha256:123456")

            # Verify Activity
            activity = prov["activity"]["jabuti:activity:local_jabuti_000"]
            self.assertEqual(activity["jabuti:status"], "SUCCESS")
            self.assertEqual(activity["jabuti:exit_code"], 0)
            self.assertFalse(activity["jabuti:is_partial"])

            pred_entity = entities["jabuti:prediction:qwen2.5-coder-32b:local_jabuti_000"]
            self.assertEqual(pred_entity["jabuti:export_tool"], "COPY_TO_STDOUT")
            self.assertEqual(pred_entity["jabuti:row_count"], 2)
            self.assertEqual(pred_entity["jabuti:file_sha256"], calculate_file_hash(csv_path))

            metrics_entity = entities["jabuti:metrics:qwen2.5-coder-32b:local_jabuti_000"]
            self.assertEqual(metrics_entity["jabuti:t_llm_ms"], 1100.2)
            self.assertEqual(metrics_entity["jabuti:t_db_ms"], 350.1)
            self.assertEqual(metrics_entity["jabuti:tokens_total"], 920)

            # Verify Agents
            agents = prov["agent"]
            roles = {a.get("jabuti:role") for a in agents.values()}
            self.assertEqual(roles, {"LLMBackend", "PostgreSQLServer", "AkôFlowEngine"})

    @patch("spider_agent.agent.agents.call_llm")
    @patch("spider_agent.agent.agents.get_last_llm_usage")
    def test_agent_latency_and_token_instrumentation(self, mock_usage, mock_call_llm):
        responses = [
            'Thought: Explore tables\nAction: Bash(code="psql -U postgres jabuti_sql -c \'\\dt\'")',
            'Thought: Create scratch file\nAction: CreateFile(path="notes.txt", content="scratch notes")',
            'Thought: Export CSV\nAction: Bash(code="psql -U postgres jabuti_sql -c \\"COPY (SELECT 1) TO STDOUT WITH CSV HEADER\\" > result.csv")',
            'Thought: Done\nAction: Terminate(output="result.csv")',
        ]
        idx = 0

        def fake_llm(payload):
            nonlocal idx
            time.sleep(0.02)
            r = responses[idx]
            idx += 1
            return True, r

        mock_call_llm.side_effect = fake_llm
        mock_usage.return_value = {
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "total_tokens": 125,
        }

        mock_env = MagicMock()
        mock_env.task_config = {
            "instance_id": "local_jabuti_000",
            "question": "Test question",
            "type": "PostgreSQL",
        }

        def fake_step(action):
            if isinstance(action, Terminate):
                return "Terminate", True
            if isinstance(action, CreateFile):
                time.sleep(0.03)  # Host I/O - must NOT be included in t_db_ms
                return "File created.", False
            time.sleep(0.03)  # Container DB call - must be included in t_db_ms
            return "Command executed successfully.", False

        mock_env.step.side_effect = fake_step

        agent = PromptAgent(model="qwen2.5-coder:32b", max_steps=5)
        agent.set_env_and_task(mock_env)
        done, result = agent.run()

        self.assertTrue(done)
        self.assertEqual(result, "result.csv")
        # 4 LLM calls * ~20ms >= 70ms
        self.assertGreaterEqual(agent.t_llm_ms, 70.0)
        # Exactly 2 Bash calls were DB actions (* ~30ms >= 50ms). CreateFile was NOT counted in t_db_ms (< 85ms)
        self.assertGreaterEqual(agent.t_db_ms, 50.0)
        self.assertLess(agent.t_db_ms, 85.0)
        self.assertEqual(agent.tokens_prompt, 400)
        self.assertEqual(agent.tokens_completion, 100)
        self.assertEqual(agent.tokens_total, 500)
        self.assertEqual(agent.export_syntax, "COPY_TO_STDOUT")

    @patch("run_single_task.Spider_Agent_Env")
    @patch("spider_agent.agent.agents.call_llm")
    def test_execute_single_task_writes_provenance_on_failure(self, mock_call_llm, mock_env_cls):
        mock_call_llm.side_effect = RuntimeError("Simulated LLM connection failure")

        def create_mock_env(env_config, task_config, cache_dir, mnt_dir):
            m = MagicMock()
            m.task_config = task_config
            m.post_process.return_value = {}
            return m

        mock_env_cls.side_effect = create_mock_env

        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                task_id="local_jabuti_000",
                test_path="./examples/jabuti.jsonl",
                task_dir=None,
                model="qwen2.5-coder:32b",
                provider="ollama",
                base_url="http://localhost:11434/v1",
                api_key="ollama",
                temperature=0.5,
                top_p=0.9,
                max_tokens=500,
                stop_token=None,
                max_steps=5,
                max_memory_length=10,
                plan=False,
                output_dir=tmpdir,
                overwriting=True,
                retry_failed=False,
                pg_host="jabuti-postgres",
                pg_port=5432,
                docker_network="spider-net",
                image_name=None,
                cache_dir="./cache",
                dry_run=False,
            )
            exit_code = run_single_task.execute_single_task(args)
            self.assertEqual(exit_code, 1)

            metrics_file = os.path.join(tmpdir, "metrics.json")
            prov_file = os.path.join(tmpdir, "task_provenance.json")
            self.assertTrue(os.path.isfile(metrics_file))
            self.assertTrue(os.path.isfile(prov_file))

            with open(metrics_file, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            self.assertEqual(metrics["exit_code"], 1)
            self.assertFalse(metrics["has_result_csv"])
            self.assertIsNone(metrics["csv_sha256"])
            self.assertIn("t_llm_ms", metrics)
            self.assertIn("t_db_ms", metrics)
            self.assertIn("tokens_total", metrics)

            with open(prov_file, "r", encoding="utf-8") as f:
                prov = json.load(f)
            pred_ent = prov["entity"]["jabuti:prediction:qwen2.5-coder-32b:local_jabuti_000"]
            self.assertIsNone(pred_ent["jabuti:file_sha256"])
            self.assertEqual(pred_ent["jabuti:export_tool"], "NONE")

    @patch("run_single_task.Spider_Agent_Env")
    @patch("spider_agent.agent.agents.call_llm")
    @patch("spider_agent.agent.agents.get_last_llm_usage")
    def test_execute_single_task_success_and_timeout(
        self, mock_usage, mock_call_llm, mock_env_cls
    ):
        mock_usage.return_value = {
            "prompt_tokens": 50,
            "completion_tokens": 10,
            "total_tokens": 60,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            def create_mock_env(env_config, task_config, cache_dir, mnt_dir):
                m = MagicMock()
                m.task_config = task_config

                def step_fn(action):
                    if isinstance(action, Terminate):
                        return "Terminate", True
                    # Simulate writing result.csv inside container workspace
                    with open(os.path.join(mnt_dir, "result.csv"), "w", encoding="utf-8") as f:
                        f.write("col1,col2\nval1,100\n")
                    return "COPY 1", False

                m.step.side_effect = step_fn
                m.post_process.return_value = {
                    "added_files": [os.path.join(mnt_dir, "result.csv")],
                    "changed_files": [],
                }
                return m

            mock_env_cls.side_effect = create_mock_env
            mock_call_llm.side_effect = [
                (
                    True,
                    'Thought: Export\nAction: Bash(code="psql -U postgres jabuti_sql -c \\"COPY (SELECT 1) TO STDOUT WITH CSV HEADER\\" > result.csv")',
                ),
                (True, 'Thought: Done\nAction: Terminate(output="result.csv")'),
            ]

            args = argparse.Namespace(
                task_id="local_jabuti_000",
                test_path="./examples/jabuti.jsonl",
                task_dir=None,
                model="qwen2.5-coder:32b",
                provider="ollama",
                base_url="http://localhost:11434/v1",
                api_key="ollama",
                temperature=0.5,
                top_p=0.9,
                max_tokens=500,
                stop_token=None,
                max_steps=5,
                max_memory_length=10,
                plan=False,
                output_dir=tmpdir,
                overwriting=True,
                retry_failed=False,
                pg_host="jabuti-postgres",
                pg_port=5432,
                docker_network="spider-net",
                image_name=None,
                cache_dir="./cache",
                dry_run=False,
            )
            exit_code = run_single_task.execute_single_task(args)
            self.assertEqual(exit_code, 0)

            with open(os.path.join(tmpdir, "metrics.json"), "r", encoding="utf-8") as f:
                metrics = json.load(f)
            self.assertEqual(metrics["exit_code"], 0)
            self.assertEqual(metrics["step_count"], 2)
            self.assertEqual(metrics["tokens_prompt"], 100)
            self.assertEqual(metrics["tokens_completion"], 20)
            self.assertEqual(metrics["tokens_total"], 120)
            self.assertEqual(metrics["export_syntax"], "COPY_TO_STDOUT")
            self.assertTrue(metrics["has_result_csv"])
            self.assertEqual(metrics["csv_row_count"], 1)

            with open(os.path.join(tmpdir, "task_provenance.json"), "r", encoding="utf-8") as f:
                prov = json.load(f)
            pred_ent = prov["entity"]["jabuti:prediction:qwen2.5-coder-32b:local_jabuti_000"]
            self.assertEqual(pred_ent["jabuti:export_tool"], "COPY_TO_STDOUT")
            self.assertEqual(pred_ent["jabuti:row_count"], 1)
            self.assertNotEqual(pred_ent["jabuti:file_sha256"], "none")


if __name__ == "__main__":
    unittest.main()
