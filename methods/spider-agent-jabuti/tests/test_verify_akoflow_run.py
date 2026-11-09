import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
for p in (PARENT_DIR, os.path.join(PARENT_DIR, "akoflow"), os.path.join(PARENT_DIR, "provenance")):
    if p not in sys.path:
        sys.path.insert(0, p)

from spider_agent.agent.provenance import build_w3c_prov_record, calculate_file_hash
import verify_akoflow_run as verifier


def _create_synthetic_task_output(
    base_dir: str,
    task_id: str,
    t_total_ms: float = 15000.0,
    t_llm_ms: float = 13500.0,
    t_db_ms: float = 450.0,
    step_count: int = 3,
    exit_code: int = 0,
    export_syntax: str = "COPY_TO_STDOUT",
) -> str:
    """Creates a realistic synthetic task output directory for offline testing."""
    task_dir = os.path.join(base_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)

    csv_path = os.path.join(task_dir, "result.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("tipo_gestao,total\nM,120\nE,45\n")

    csv_sha = calculate_file_hash(csv_path)

    metrics = {
        "instance_id": task_id,
        "model": "qwen2.5-coder:32b",
        "provider": "ollama",
        "step_count": step_count,
        "max_steps": 20,
        "finished": exit_code == 0,
        "done": exit_code == 0,
        "exit_code": exit_code,
        "t_total_ms": t_total_ms,
        "t_llm_ms": t_llm_ms,
        "t_db_ms": t_db_ms,
        "tokens_prompt": 1200,
        "tokens_completion": 180,
        "tokens_total": 1380,
        "export_syntax": export_syntax,
        "result_output": "result.csv",
        "has_result_csv": True,
        "csv_row_count": 2,
        "csv_sha256": csv_sha,
        "start_time": "2026-11-05T12:00:00+00:00",
        "end_time": "2026-11-05T12:00:15+00:00",
        "error": None,
    }
    with open(os.path.join(task_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    with open(os.path.join(task_dir, "trajectory.json"), "w", encoding="utf-8") as f:
        json.dump({"trajectory": [{"step": i} for i in range(step_count)]}, f)

    task_config = {
        "instance_id": task_id,
        "question": f"Pergunta de teste para {task_id}",
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
        output_dir=task_dir,
        container_name=f"spider-jabuti-qwen2.5-coder-32b-{task_id}-abc123",
        image_name="spider_agent_jabuti-image",
        step_count=step_count,
        total_duration_ms=t_total_ms,
        t_llm_ms=t_llm_ms,
        t_db_ms=t_db_ms,
        tokens_prompt=1200,
        tokens_completion=180,
        tokens_total=1380,
        exit_code=exit_code,
        start_time_iso="2026-11-05T12:00:00+00:00",
        end_time_iso="2026-11-05T12:00:15+00:00",
        has_result_csv=True,
        export_syntax=export_syntax,
        model_digest="sha256:dummyweightsdigest",
        db_dump_hash="sha256:dummydbdumphash",
    )
    with open(os.path.join(task_dir, "task_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=2)

    return task_dir


class TestVerifyAkoflowRun(unittest.TestCase):
    def test_verify_valid_smoke_run_and_latency_aggregation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_synthetic_task_output(
                tmpdir, "local_jabuti_000", t_total_ms=10000.0, t_llm_ms=9000.0, t_db_ms=300.0, step_count=2
            )
            _create_synthetic_task_output(
                tmpdir, "local_jabuti_001", t_total_ms=20000.0, t_llm_ms=18000.0, t_db_ms=600.0, step_count=4
            )
            _create_synthetic_task_output(
                tmpdir, "local_jabuti_002", t_total_ms=15000.0, t_llm_ms=13500.0, t_db_ms=450.0, step_count=3
            )

            report_json = os.path.join(tmpdir, "verification_report.json")
            args = verifier.parse_args(
                [
                    "--results_dir",
                    tmpdir,
                    "--expected_tasks",
                    "0,1,2",
                    "--output_json",
                    report_json,
                ]
            )
            exit_code, report = verifier.run_verification(args)
            self.assertEqual(exit_code, 0)
            self.assertTrue(report["all_tasks_valid"])
            self.assertTrue(os.path.isfile(report_json))

            lat = report["summary"]["latency_ms"]
            self.assertAlmostEqual(lat["avg_t_total_ms"], 15000.0, places=2)
            self.assertAlmostEqual(lat["avg_t_llm_ms"], 13500.0, places=2)
            self.assertAlmostEqual(lat["avg_t_db_ms"], 450.0, places=2)
            self.assertAlmostEqual(lat["llm_to_db_ratio"], 30.0, places=2)
            self.assertEqual(report["summary"]["steps"]["avg_steps"], 3.0)
            self.assertEqual(report["akoflow_provenance_api"]["status"], "SKIPPED")

    def test_detects_missing_artifact_and_hash_tampering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            t0_dir = _create_synthetic_task_output(tmpdir, "local_jabuti_000")
            # Tamper with result.csv after provenance hash was recorded
            with open(os.path.join(t0_dir, "result.csv"), "a", encoding="utf-8") as f:
                f.write("CORRUPTED,999\n")

            # Missing local_jabuti_001 completely
            args = verifier.parse_args(
                [
                    "--results_dir",
                    tmpdir,
                    "--expected_tasks",
                    "0,1",
                ]
            )
            exit_code, report = verifier.run_verification(args)
            self.assertEqual(exit_code, 1)
            self.assertFalse(report["all_tasks_valid"])
            self.assertEqual(report["summary"]["failed_verification_count"], 2)
            self.assertTrue(
                any("SHA256" in err for err in report["tasks"][0]["errors"])
            )
            self.assertTrue(
                any("not found" in err for err in report["tasks"][1]["errors"])
            )

    @patch("urllib.request.urlopen")
    def test_mocked_akoflow_provenance_rest_api(self, mock_urlopen):
        mock_payload = {
            "namespace": "escience-jabuti",
            "workflow": "jabuti-sql-benchmark-qwen2.5-coder-32b",
            "activities": [
                {"name": "preflight-check", "status": "SUCCEEDED"},
                {"name": "task-local_jabuti_000", "status": "SUCCEEDED"},
                {"name": "task-local_jabuti_001", "status": "SUCCEEDED"},
                {"name": "evaluation", "status": "SUCCEEDED"},
            ],
        }
        mock_resp = io.BytesIO(json.dumps(mock_payload).encode("utf-8"))
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        api_res = verifier.verify_akoflow_provenance_api(
            api_url="http://mock-akoflow.local:8080",
            expected_task_ids=["local_jabuti_000", "local_jabuti_001"],
            workflow_name="jabuti-sql-benchmark-qwen2.5-coder-32b",
        )
        self.assertEqual(api_res["status"], "VERIFIED")
        self.assertEqual(
            api_res["recorded_activities"],
            ["task-local_jabuti_000", "task-local_jabuti_001"],
        )
        self.assertEqual(api_res["missing_activities"], [])


if __name__ == "__main__":
    unittest.main()

