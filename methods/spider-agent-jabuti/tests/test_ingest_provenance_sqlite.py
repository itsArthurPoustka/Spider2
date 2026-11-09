#!/usr/bin/env python3
"""
test_ingest_provenance_sqlite.py — Unit Tests for SQLite Provenance Ingestion
"""

import os
import sqlite3
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
for p in (PARENT_DIR, os.path.join(PARENT_DIR, "akoflow"), os.path.join(PARENT_DIR, "provenance")):
    if p not in sys.path:
        sys.path.insert(0, p)

from ingest_provenance_sqlite import (
    extract_sql_from_action,
    init_database,
    ingest_run,
)


class TestIngestProvenanceSQLite(unittest.TestCase):
    def test_extract_sql_from_action(self):
        cmd = 'Bash(code="psql -U postgres jabuti_sql -c \\"SELECT 1 FROM table\\")'
        self.assertEqual(extract_sql_from_action(cmd), "SELECT 1 FROM table")

        cmd2 = "Bash(code='psql -U postgres jabuti_sql -c \\'SELECT count(*) FROM test\\'\')"
        self.assertEqual(extract_sql_from_action(cmd2), "SELECT count(*) FROM test")

        self.assertIsNone(extract_sql_from_action('Bash(code="ls -la")'))
        self.assertIsNone(extract_sql_from_action(""))

    def test_init_database(self):
        conn = sqlite3.connect(":memory:")
        init_database(conn)
        cur = conn.cursor()

        # Check tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cur.fetchall()}
        self.assertIn("runs", tables)
        self.assertIn("task_provenance", tables)
        self.assertIn("task_steps", tables)

        # Check views exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='view';")
        views = {row[0] for row in cur.fetchall()}
        self.assertIn("v_persona_summary", views)
        self.assertIn("v_difficulty_summary", views)
        self.assertIn("v_sql_actions", views)
        conn.close()


if __name__ == "__main__":
    unittest.main()

