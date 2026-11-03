#!/usr/bin/env python3
"""
load_dump.py — Robust database loader for JABUTI-SQL PostgreSQL database
========================================================================

PURPOSE:
--------
Loads the JABUTI-SQL schema and dataset into PostgreSQL.
Supports:
  1. PostgreSQL custom archive dump (jabuti_sql.dump, pg_dump -Fc) — FAST & COMPLETE.
  2. Plain text SQL dump (dump.sql) — legacy fallback.

FEATURES:
---------
- Automatically detects binary custom format (.dump) vs plain text (.sql).
- Uses `pg_restore` natively (on host or inside Docker container `jabuti-postgres`).
- Pre-creates the required `datalake_user` role with appropriate permissions.
- Fast mode (default): loads the 14 standard tables (~1.2M rows in ~15 seconds),
  which unlocks 63 out of 69 questions.
- Full mode (--full or --include-stock): loads all 15 tables including the 143M
  row `instituicao_estoca_produto` table (unlocks 100% of benchmark).
- Automatically refreshes materialized views (`mv_leitos_mais_recente`, etc.).
- Displays clean, verified row count table upon completion.

USAGE:
------
  # Fast mode (loads 14 tables ~1.2M rows, takes ~15 seconds):
  python load_dump.py --host localhost --port 5432

  # Full mode (includes the 143M rows of instituicao_estoca_produto):
  python load_dump.py --host localhost --port 5432 --full
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("ERROR: psycopg2 is required. Install with: pip install psycopg2-binary")
    sys.exit(1)


CORE_14_TABLES = [
    "catmat",
    "endereco",
    "fabricante",
    "fornecedor",
    "instituicao",
    "leitos",
    "macrorregiao_de_saude",
    "mantenedora",
    "mantenedora_compra_produto",
    "municipio",
    "produto",
    "regiao_de_saude",
    "regiao_do_brasil",
    "unidade_federativa",
]

ALL_15_TABLES = CORE_14_TABLES + ["instituicao_estoca_produto"]


def find_file(relative_subpath: str) -> str:
    """Find file in either Spider2/JABUTI-SQL or ../../../JABUTI-SQL."""
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "JABUTI-SQL", relative_subpath)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "JABUTI-SQL", relative_subpath)),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


def find_default_dump() -> str:
    """Check for jabuti_sql.dump first, then fallback to dump.sql."""
    dump_custom = find_file("jabuti_sql.dump")
    if os.path.exists(dump_custom):
        return dump_custom
    dump_sql = find_file("dump.sql")
    if os.path.exists(dump_sql):
        return dump_sql
    return dump_custom


def is_custom_format_dump(filepath: str) -> bool:
    """Check if the dump file is a PostgreSQL custom archive (starts with PGDMP)."""
    if not os.path.exists(filepath):
        return False
    with open(filepath, "rb") as f:
        magic = f.read(5)
        return magic == b"PGDMP"


def init_database(conn):
    """Ensure required roles exist and permissions are set."""
    with conn.cursor() as cur:
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'datalake_user') THEN
                    CREATE ROLE datalake_user WITH LOGIN SUPERUSER;
                END IF;
            END
            $$;
        """)
        cur.execute("GRANT ALL ON SCHEMA public TO postgres, datalake_user;")
    conn.commit()
    print("[load_dump] Initialized database roles (datalake_user, postgres).")


def reset_public_schema(conn):
    """Clean public schema for a fresh restore."""
    with conn.cursor() as cur:
        cur.execute("""
            DROP SCHEMA IF EXISTS public CASCADE;
            CREATE SCHEMA public;
            GRANT ALL ON SCHEMA public TO postgres, datalake_user;
        """)
    conn.commit()
    print("[load_dump] Reset public schema.")


def restore_custom_dump(dump_path: str, args, target_tables: list):
    """Restore from a PostgreSQL custom archive dump using pg_restore."""
    # Determine pg_restore invocation
    has_local_pg_restore = shutil.which("pg_restore") is not None
    use_docker = not has_local_pg_restore

    print(f"[load_dump] Mode: PostgreSQL custom archive dump ({os.path.getsize(dump_path) / (1024*1024):.1f} MB)")
    if use_docker:
        print("[load_dump] Using pg_restore inside Docker container 'jabuti-postgres'")
    else:
        print("[load_dump] Using host pg_restore")

    # Step 1: Restore schema only
    print("  --> Restoring database schema (tables, views, indexes, materialized views)...")
    if use_docker:
        schema_cmd = [
            "docker", "exec", "-i", "jabuti-postgres",
            "pg_restore", "-U", args.user, "-d", args.dbname, "--schema-only"
        ]
    else:
        schema_cmd = [
            "pg_restore", "-h", args.host, "-p", str(args.port), "-U", args.user,
            "-d", args.dbname, "--schema-only"
        ]

    with open(dump_path, "rb") as dump_file:
        res = subprocess.run(schema_cmd, stdin=dump_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"  [WARN] Schema restore returned non-zero code {res.returncode}: {res.stderr.decode()[:200]}")
    else:
        print("  [OK] Schema restored successfully.")

    # Step 2: Restore data for target tables
    print(f"  --> Restoring data for {len(target_tables)} table(s)...")
    table_flags = []
    for t in target_tables:
        table_flags.extend(["-t", t])

    if use_docker:
        data_cmd = [
            "docker", "exec", "-i", "jabuti-postgres",
            "pg_restore", "-U", args.user, "-d", args.dbname, "-a"
        ] + table_flags
    else:
        data_cmd = [
            "pg_restore", "-h", args.host, "-p", str(args.port), "-U", args.user,
            "-d", args.dbname, "-a"
        ] + table_flags

    with open(dump_path, "rb") as dump_file:
        res = subprocess.run(data_cmd, stdin=dump_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"  [WARN] Data restore returned non-zero code {res.returncode}: {res.stderr.decode()[:200]}")
    else:
        print(f"  [OK] Data restored for {len(target_tables)} table(s).")


def run_ddl(conn, ddl_path: str):
    """Execute ddl.sql to create tables, views, and indexes (legacy SQL loader)."""
    print(f"[load_dump] Executing DDL from {ddl_path}...")
    with open(ddl_path, "r", encoding="utf-8") as f:
        lines = [line for line in f if not line.strip().startswith("\\")]
        ddl_sql = "".join(lines)

    with conn.cursor() as cur:
        cur.execute(ddl_sql)
    conn.commit()
    print("[load_dump] DDL executed successfully.")


def load_copy_blocks(conn, dump_path: str, allowed_tables: set):
    """Parse and execute COPY blocks from dump.sql (legacy SQL loader)."""
    print(f"[load_dump] Reading COPY data from {dump_path}...")
    current_table = None
    buffer = []
    total_loaded = {}

    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            if line.startswith("COPY "):
                parts = line.split()
                table_with_schema = parts[1]
                table_name = table_with_schema.replace("public.", "")
                if allowed_tables is None or table_name in allowed_tables:
                    current_table = table_name
                    buffer = [line]
                else:
                    current_table = None
                continue

            if current_table:
                if line.strip() == r"\.":
                    buffer.append(line)
                    _execute_copy_buffer(conn, current_table, buffer, total_loaded)
                    current_table = None
                    buffer = []
                elif line.startswith("--") or line.startswith("SET ") or line.startswith("ALTER "):
                    buffer.append("\\.\n")
                    _execute_copy_buffer(conn, current_table, buffer, total_loaded)
                    current_table = None
                    buffer = []
                else:
                    buffer.append(line)

        if current_table and buffer:
            while buffer and not buffer[-1].endswith("\n"):
                buffer.pop()
            buffer.append("\\.\n")
            _execute_copy_buffer(conn, current_table, buffer, total_loaded)

    return total_loaded


def _execute_copy_buffer(conn, table_name, buffer, total_loaded):
    import io
    copy_stmt = buffer[0]
    data = "".join(buffer[1:])
    with conn.cursor() as cur:
        try:
            cur.copy_expert(copy_stmt, io.StringIO(data))
            conn.commit()
            cur.execute(f"SELECT COUNT(*) FROM public.{table_name};")
            count = cur.fetchone()[0]
            total_loaded[table_name] = count
            print(f"  [OK] Loaded public.{table_name}: {count:,} rows")
        except Exception as e:
            conn.rollback()
            print(f"  [ERROR] Failed to load public.{table_name}: {e}")


def refresh_materialized_views(conn):
    """Attempt refreshing materialized views if tables exist."""
    views = ["mv_leitos_mais_recente", "mv_estoque_mais_recente"]
    with conn.cursor() as cur:
        for mv in views:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW public.{mv};")
                conn.commit()
                print(f"  [OK] Refreshed materialized view public.{mv}")
            except Exception as e:
                conn.rollback()
                print(f"  [NOTE] Could not refresh public.{mv} (expected if source table empty): {e}")


def print_database_summary(conn):
    """Query and display live row counts for all tables and materialized views."""
    with conn.cursor() as cur:
        cur.execute("ANALYZE;")
        cur.execute("""
            SELECT 
                schemaname, 
                relname AS table_name, 
                n_live_tup AS live_rows 
            FROM pg_stat_user_tables 
            ORDER BY table_name;
        """)
        rows = cur.fetchall()

    print("\n" + "=" * 60)
    print("Current Row Counts in Database (pg_stat_user_tables):")
    print("=" * 60)
    total = 0
    for schema, table, count in rows:
        print(f"  - {table:<32}: {count:>12,} rows")
        total += count
    print("-" * 60)
    print(f"  {'TOTAL ROWS':<32}: {total:>12,} rows")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Load JABUTI-SQL into PostgreSQL")
    parser.add_argument("--host", default="localhost", help="PostgreSQL host (default: localhost)")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    parser.add_argument("--user", default="postgres", help="PostgreSQL user (default: postgres)")
    parser.add_argument("--password", default="", help="PostgreSQL password")
    parser.add_argument("--dbname", default="jabuti_sql", help="Database name (default: jabuti_sql)")
    parser.add_argument("--ddl", default=None, help="Path to ddl.sql (for legacy SQL dumps)")
    parser.add_argument("--dump", default=None, help="Path to jabuti_sql.dump or dump.sql")
    parser.add_argument("--full", "--include-stock", dest="full_load", action="store_true",
                        help="Include the 143M row instituicao_estoca_produto table (takes longer)")
    parser.add_argument("--clean", action="store_true", default=True,
                        help="Drop and recreate public schema before loading (default: True)")
    parser.add_argument("--no-clean", dest="clean", action="store_false",
                        help="Do not drop public schema before loading")

    args = parser.parse_args()

    dump_path = args.dump or find_default_dump()
    ddl_path = args.ddl or find_file("ddl/ddl.sql")

    if not os.path.exists(dump_path):
        print(f"ERROR: Dump file not found at {dump_path}")
        sys.exit(1)

    custom_format = is_custom_format_dump(dump_path)

    print("=" * 60)
    print("JABUTI-SQL Database Loader")
    print(f"Target:   {args.user}@{args.host}:{args.port}/{args.dbname}")
    print(f"Dump:     {dump_path} (Format: {'PostgreSQL Custom Dump' if custom_format else 'Plain SQL'})")
    if custom_format:
        target_tables = ALL_15_TABLES if args.full_load else CORE_14_TABLES
        print(f"Scope:    {'All 15 tables (including 143M stock rows)' if args.full_load else '14 core tables (~1.2M rows, fast mode)'}")
    print("=" * 60)

    conn_params = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "dbname": args.dbname,
    }
    if args.password:
        conn_params["password"] = args.password

    try:
        conn = psycopg2.connect(**conn_params)
    except Exception as e:
        print(f"ERROR: Could not connect to PostgreSQL: {e}")
        print("Ensure PostgreSQL is running (e.g. `docker compose up -d` in jabuti_db/)")
        sys.exit(1)

    t0 = time.time()
    init_database(conn)

    if custom_format:
        if args.clean:
            reset_public_schema(conn)
        restore_custom_dump(dump_path, args, target_tables)
    else:
        # Legacy plain text SQL path
        if not os.path.exists(ddl_path):
            print(f"ERROR: ddl.sql not found at {ddl_path}")
            sys.exit(1)
        run_ddl(conn, ddl_path)
        allowed = set(ALL_15_TABLES if args.full_load else CORE_14_TABLES)
        load_copy_blocks(conn, dump_path, allowed)

    refresh_materialized_views(conn)
    print_database_summary(conn)
    conn.close()

    elapsed = time.time() - t0
    print(f"\n[load_dump] Database loading finished in {elapsed:.1f} seconds!")


if __name__ == "__main__":
    main()
