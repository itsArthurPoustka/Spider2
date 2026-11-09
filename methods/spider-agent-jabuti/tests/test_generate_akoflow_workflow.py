import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
for p in (PARENT_DIR, os.path.join(PARENT_DIR, "akoflow"), os.path.join(PARENT_DIR, "provenance")):
    if p not in sys.path:
        sys.path.insert(0, p)

import generate_akoflow_workflow as gen


def _parse_yaml_with_ruby_or_fallback(yaml_path: str) -> dict:
    """
    Parses a YAML file into a Python dict using PyYAML if installed,
    or system Ruby's psych (libyaml) parser on macOS/Linux.
    """
    try:
        import yaml as _yaml  # type: ignore

        if hasattr(_yaml, "safe_load"):
            with open(yaml_path, "r", encoding="utf-8") as f:
                return _yaml.safe_load(f)
    except ImportError:
        pass

    proc = subprocess.run(
        [
            "ruby",
            "-ryaml",
            "-rjson",
            "-e",
            "puts JSON.generate(YAML.safe_load(File.read(ARGV[0])))",
            yaml_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


class TestGenerateAkoflowWorkflow(unittest.TestCase):
    def test_full_69_instance_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_yaml = os.path.join(tmpdir, "workflow_jabuti.yaml")
            exit_code = gen.main(
                [
                    "--model",
                    "qwen2.5-coder:32b",
                    "--instances",
                    "all",
                    "--output_yaml",
                    out_yaml,
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.isfile(out_yaml))

            doc = _parse_yaml_with_ruby_or_fallback(out_yaml)
            self.assertEqual(doc["name"], "jabuti-sql-benchmark-qwen2.5-coder-32b")
            self.assertEqual(doc["spec"]["namespace"], "escience-jabuti")
            self.assertEqual(doc["spec"]["image"], "spider-agent-runner:latest")

            activities = doc["spec"]["activities"]
            # 1 preflight + 69 tasks + 1 evaluation = 71 activities
            self.assertEqual(len(activities), 71)

            # Activity 0: preflight-check
            preflight = activities[0]
            self.assertEqual(preflight["name"], "preflight-check")
            self.assertNotIn("dependsOn", preflight)
            self.assertIn("postgres", preflight["run"])

            # Activities 1..69: task-local_jabuti_000 .. task-local_jabuti_068
            expected_task_names = []
            for idx in range(69):
                task_id = f"local_jabuti_{idx:03d}"
                act_name = f"task-{task_id}"
                expected_task_names.append(act_name)
                act = activities[idx + 1]
                self.assertEqual(act["name"], act_name)
                self.assertEqual(act["dependsOn"], ["preflight-check"])
                self.assertEqual(act["cpuLimit"], "1")
                self.assertIsInstance(act["cpuLimit"], str)
                self.assertEqual(act["memoryLimit"], "2Gi")
                self.assertIsInstance(act["memoryLimit"], str)
                self.assertEqual(
                    act["run"],
                    f"python run_single_task.py --task_id {task_id} "
                    f"--model qwen2.5-coder:32b "
                    f"--output_dir /shared/output/qwen2.5-coder:32b/{task_id}",
                )

            # Final Activity: evaluation
            evaluation = activities[-1]
            self.assertEqual(evaluation["name"], "evaluation")
            self.assertEqual(evaluation["dependsOn"], expected_task_names)
            self.assertEqual(
                evaluation["run"],
                "python evaluate_jabuti.py "
                "--result_dir /shared/output/qwen2.5-coder:32b "
                "--gold_dir evaluation/gold "
                "--jabuti_jsonl examples/jabuti.jsonl",
            )

    def test_smoke_subset_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_yaml = os.path.join(tmpdir, "workflow_smoke.yaml")
            exit_code = gen.main(
                [
                    "--model",
                    "qwen2.5-coder:32b",
                    "--instances",
                    "0,1,2",
                    "--output_yaml",
                    out_yaml,
                ]
            )
            self.assertEqual(exit_code, 0)
            doc = _parse_yaml_with_ruby_or_fallback(out_yaml)

            activities = doc["spec"]["activities"]
            self.assertEqual(len(activities), 5)
            self.assertEqual(
                [a["name"] for a in activities],
                [
                    "preflight-check",
                    "task-local_jabuti_000",
                    "task-local_jabuti_001",
                    "task-local_jabuti_002",
                    "evaluation",
                ],
            )
            for act in activities[1:4]:
                self.assertEqual(act["dependsOn"], ["preflight-check"])
            self.assertEqual(
                activities[-1]["dependsOn"],
                [
                    "task-local_jabuti_000",
                    "task-local_jabuti_001",
                    "task-local_jabuti_002",
                ],
            )

    def test_invalid_instance_raises_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_yaml = os.path.join(tmpdir, "invalid.yaml")
            exit_code = gen.main(
                [
                    "--model",
                    "qwen2.5-coder:32b",
                    "--instances",
                    "999",
                    "--output_yaml",
                    out_yaml,
                ]
            )
            self.assertEqual(exit_code, 1)

            empty_exit = gen.main(
                [
                    "--model",
                    "qwen2.5-coder:32b",
                    "--instances",
                    "   ",
                    "--output_yaml",
                    out_yaml,
                ]
            )
            self.assertEqual(empty_exit, 1)


if __name__ == "__main__":
    unittest.main()

