#!/usr/bin/env python3
"""
test_provenance_queries.py — Unit Tests for Provenance Query Catalog
"""

import os
import sqlite3
import tempfile
import unittest

from ingest_provenance_sqlite import init_database
from provenance_queries import CATALOG, generate_sql_file, run_query


class TestProvenanceQueries(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize mock database schema and sample row
        conn = sqlite3.connect(self.db_path)
        init_database(conn)
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO runs (run_id, model, provider, total_tasks, correct_tasks, accuracy)
        VALUES ('test_run', 'mock_model', 'ollama', 1, 1, 1.0);
        """)
        cur.execute("""
        INSERT INTO task_provenance (
            run_id, task_id, persona, difficulty, parent_group, is_correct,
            t_total_ms, t_llm_ms, t_db_ms, t_other_ms, tokens_prompt,
            tokens_completion, tokens_total, step_count, export_syntax,
            prompt_hash, schema_sha256, model_digest, csv_sha256, raw_prov_json
        ) VALUES (
            'test_run', 'local_jabuti_000', 'Cidadã Leiga', 'simple', '0', 1,
            10000.0, 8000.0, 500.0, 1500.0, 100, 20, 120, 3, 'COPY_TO_STDOUT',
            'hash1', 'hash2', 'digest1', 'csvhash1', '{"test": true}'
        );
        """)
        cur.execute("""
        INSERT INTO task_steps (run_id, task_id, step_number, thought, action, action_type, sql_query)
        VALUES ('test_run', 'local_jabuti_000', 1, 'think', 'Bash(code="psql")', 'Bash', 'SELECT 1');
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_catalog_structure(self):
        self.assertGreaterEqual(len(CATALOG), 15)
        for qid, qdata in CATALOG.items():
            self.assertIn("title", qdata)
            self.assertIn("category", qdata)
            self.assertIn("description", qdata)
            self.assertIn("sql", qdata)
            self.assertTrue(qdata["sql"].strip().startswith("SELECT") or qdata["sql"].strip().startswith("WITH"))

    def test_all_catalog_queries_syntax(self):
        # Execute every single query in the catalog against the test database
        for qid in CATALOG:
            cols, rows = run_query(self.db_path, qid)
            self.assertIsInstance(cols, list)
            self.assertIsInstance(rows, list)

    def test_export_sql(self):
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tf:
            sql_path = tf.name
        try:
            generate_sql_file(sql_path)
            self.assertTrue(os.path.isfile(sql_path))
            self.assertGreater(os.path.getsize(sql_path), 500)
            with open(sql_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("JABUTI-SQL PROVENANCE & TELEMETRY QUERY CATALOG", content)
            self.assertIn("persona_performance", content)
        finally:
            if os.path.exists(sql_path):
                os.remove(sql_path)


if __name__ == "__main__":
    unittest.main()

