#!/usr/bin/env python3
"""
load_dump.py — Robust database loader for JABUTI-SQL PostgreSQL database
========================================================================

PURPOSE:
--------
Loads the JABUTI-SQL schema (ddl.sql) and dataset (dump.sql) into PostgreSQL.
Handles known issues with the current JABUTI-SQL dump:
  1. Creates required role 'datalake_user' prior to running DDL.
  2. Strips pg_dump 16.10 '\\restrict' header that breaks older psql clients.
  3. Safely handles truncated EOF on 'instituicao_estoca_produto'.
  4. Allows selective loading of tables (e.g. only the complete tables for smoke testing).
  5. Refreshes materialized views where applicable.

USAGE:
------
  # Fast mode (loads the 5 fully complete tables ~1.07M rows, takes ~10 seconds):
  python load_dump.py --host localhost --port 5432

  # Full mode (includes the 9.36M rows of instituicao_estoca_produto):
  python load_dump.py --host localhost --port 5432 --include-partial-stock
"""

import argparse
import os
import sys
import time

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("ERROR: psycopg2 is required. Install with: pip install psycopg2-binary")
    sys.exit(1)


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


def init_database(conn):
    """Ensure required roles exist and permissions are set."""
    with conn.cursor() as cur:
        # Create role datalake_user used by ddl.sql ownership statements
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


def run_ddl(conn, ddl_path: str):
    """Execute ddl.sql to create tables, views, and indexes."""
    print(f"[load_dump] Executing DDL from {ddl_path}...")
    with open(ddl_path, "r", encoding="utf-8") as f:
        # Strip psql client meta-commands (e.g. \restrict, \unrestrict)
        # which are not valid SQL for the backend engine.
        lines = [line for line in f if not line.strip().startswith("\\")]
        ddl_sql = "".join(lines)

    with conn.cursor() as cur:
        cur.execute(ddl_sql)
    conn.commit()
    print("[load_dump] DDL executed successfully.")


def load_copy_blocks(conn, dump_path: str, allowed_tables: set):
    """
    Parse and execute COPY blocks from dump.sql.
    Safely handles truncated COPY blocks by discarding corrupted trailing lines
    and ensuring the block is terminated with '\\.'.
    """
    print(f"[load_dump] Reading COPY data from {dump_path}...")
    current_table = None
    copy_header = None
    buffer = []
    total_loaded = {}

    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            if line.startswith("COPY "):
                parts = line.split()
                # line format: COPY public.<table_name> (...) FROM stdin;
                table_with_schema = parts[1]
                table_name = table_with_schema.replace("public.", "")
                if allowed_tables is None or table_name in allowed_tables:
                    current_table = table_name
                    copy_header = line
                    buffer = [line]
                    print(f"  --> Found COPY block for {table_name} at line {line_num}...")
                else:
                    current_table = None
                continue

            if current_table:
                if line.strip() == r"\.":
                    # Clean completion of COPY block
                    buffer.append(line)
                    _execute_copy_buffer(conn, current_table, buffer, total_loaded)
                    current_table = None
                    buffer = []
                elif line.startswith("--") or line.startswith("SET ") or line.startswith("ALTER "):
                    # Hit next SQL block without terminator (truncation)
                    print(f"  [!] Block for {current_table} had no terminator, appending \\.")
                    buffer.append("\\.\n")
                    _execute_copy_buffer(conn, current_table, buffer, total_loaded)
                    current_table = None
                    buffer = []
                else:
                    buffer.append(line)

        # Handle EOF if still inside a COPY block (e.g. truncated instituicao_estoca_produto)
        if current_table and buffer:
            print(f"  [!] Truncated EOF reached for {current_table}. Cleaning partial line and terminating.")
            # Discard broken partial last line if it doesn't end with a newline
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
    views = ["mv_estoque_mais_recente", "mv_leitos_mais_recente"]
    with conn.cursor() as cur:
        for mv in views:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW public.{mv};")
                conn.commit()
                print(f"  [OK] Refreshed materialized view public.{mv}")
            except Exception as e:
                conn.rollback()
                print(f"  [NOTE] Could not refresh public.{mv} (expected if source table empty): {e}")


def main():
    parser = argparse.ArgumentParser(description="Load JABUTI-SQL into PostgreSQL")
    parser.add_argument("--host", default="localhost", help="PostgreSQL host (default: localhost)")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    parser.add_argument("--user", default="postgres", help="PostgreSQL user (default: postgres)")
    parser.add_argument("--password", default="", help="PostgreSQL password")
    parser.add_argument("--dbname", default="jabuti_sql", help="Database name (default: jabuti_sql)")
    parser.add_argument("--ddl", default=None, help="Path to ddl.sql")
    parser.add_argument("--dump", default=None, help="Path to dump.sql")
    parser.add_argument("--include-partial-stock", action="store_true",
                        help="Include the truncated instituicao_estoca_produto table (9.36M rows)")
    parser.add_argument("--skip-ddl", action="store_true", help="Skip DDL execution (load data only)")

    args = parser.parse_args()

    ddl_path = args.ddl or find_file("ddl/ddl.sql")
    dump_path = args.dump or find_file("dump.sql")

    if not os.path.exists(ddl_path):
        print(f"ERROR: ddl.sql not found at {ddl_path}")
        sys.exit(1)
    if not os.path.exists(dump_path):
        print(f"ERROR: dump.sql not found at {dump_path}")
        sys.exit(1)

    print("=" * 60)
    print("JABUTI-SQL Database Loader")
    print(f"Target: {args.user}@{args.host}:{args.port}/{args.dbname}")
    print(f"DDL:    {ddl_path}")
    print(f"Dump:   {dump_path}")
    print("=" * 60)

    # Tables to load
    allowed = {"catmat", "endereco", "fabricante", "fornecedor", "instituicao"}
    if args.include_partial_stock:
        allowed.add("instituicao_estoca_produto")
        print("[load_dump] Mode: Complete tables + partial stock table (~10.4M rows total)")
    else:
        print("[load_dump] Mode: Complete tables only (~1.07M rows total across 5 tables)")

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

    if not args.skip_ddl:
        run_ddl(conn, ddl_path)

    loaded = load_copy_blocks(conn, dump_path, allowed)
    refresh_materialized_views(conn)
    conn.close()

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"Database loading finished in {elapsed:.1f} seconds!")
    print("Row counts in database:")
    for t, c in sorted(loaded.items()):
        print(f"  - {t:<30}: {c:>10,} rows")
    print("=" * 60)


if __name__ == "__main__":
    main()
