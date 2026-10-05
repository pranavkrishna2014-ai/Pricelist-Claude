#!/usr/bin/env python3
"""
Migrate the Mattress Price App from SQLite (mattress.db) to Supabase Postgres.

    pip install psycopg2-binary
    python3 migrate.py --db mattress.db --url "postgresql://...:5432/postgres"

Safe to run more than once: with --replace it clears the destination tables
first, so a re-run always ends with exactly what is in the SQLite file.
Every row keeps its original id, so bills stay attached to their line items.

Nothing is written to the SQLite file — it is opened read-only.
"""

import argparse
import sqlite3
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Missing dependency. Run:  pip install psycopg2-binary")


# Destination column list per table, in insert order.
TABLES = [
    ("settings",   ["key", "value"]),
    ("users",      ["id", "username", "password_hash", "role", "created_at"]),
    ("clients",    ["id", "name", "phone", "address", "discount_value", "created_at"]),
    ("price_list", ["id", "brand", "product", "size_code", "size_metric",
                    "thickness", "price", "updated_at"]),
    ("bills",      ["id", "bill_no", "packing_slip_no", "client_id", "client_name",
                    "despatch_date", "grand_total", "created_at", "created_by"]),
    ("bill_items", ["id", "bill_id", "sno", "brand", "product", "size_code",
                    "size_metric", "thickness", "quantity", "unit_price",
                    "discount_type", "discount_value", "total_value"]),
]

# Columns that must never be NULL in Postgres, with the value to use instead.
NOT_NULL_DEFAULTS = {
    ("users", "role"): "user",
    ("clients", "phone"): "",
    ("clients", "address"): "",
    ("clients", "discount_value"): 0,
    ("price_list", "size_metric"): "",
    ("price_list", "price"): 0,
    ("bills", "client_name"): "",
    ("bills", "packing_slip_no"): "",
    ("bills", "despatch_date"): "",
    ("bills", "grand_total"): 0,
    ("bills", "created_by"): "",
    ("bill_items", "quantity"): 1,
    ("bill_items", "unit_price"): 0,
    ("bill_items", "discount_type"): "amount",
    ("bill_items", "discount_value"): 0,
    ("bill_items", "total_value"): 0,
}


def sqlite_columns(sconn, table):
    return {r[1] for r in sconn.execute(f"PRAGMA table_info({table})")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="mattress.db", help="path to the SQLite file")
    ap.add_argument("--url", required=True, help="Supabase connection string")
    ap.add_argument("--replace", action="store_true",
                    help="clear destination tables first (use for a re-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="read and report only, write nothing")
    args = ap.parse_args()

    sconn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sconn.row_factory = sqlite3.Row

    existing = {r[0] for r in sconn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    print(f"Reading {args.db}")
    payload = {}
    for table, cols in TABLES:
        if table not in existing:
            print(f"  {table:<12} table not present, skipping")
            payload[table] = []
            continue

        have = sqlite_columns(sconn, table)
        rows = []
        for r in sconn.execute(f"SELECT * FROM {table}"):
            d = dict(r)
            # Google Drive OAuth tokens are meaningless after the move
            if table == "settings" and str(d.get("key", "")).startswith("gdrive"):
                continue
            row = []
            for c in cols:
                v = d.get(c) if c in have else None
                if v is None and (table, c) in NOT_NULL_DEFAULTS:
                    v = NOT_NULL_DEFAULTS[(table, c)]
                row.append(v)
            rows.append(row)
        payload[table] = rows
        missing = [c for c in cols if c not in have]
        note = f"  (columns not in source, defaulted: {', '.join(missing)})" if missing else ""
        print(f"  {table:<12} {len(rows):>6} rows{note}")

    sconn.close()

    if args.dry_run:
        print("\nDry run — nothing written.")
        return

    print(f"\nConnecting to Postgres")
    pconn = psycopg2.connect(args.url)
    pconn.autocommit = False
    cur = pconn.cursor()

    try:
        if args.replace:
            # Children first; bill_items also goes via the cascade, but be explicit.
            cur.execute("TRUNCATE bill_items, bills, price_list, clients, users, settings "
                        "RESTART IDENTITY CASCADE")
            print("  cleared destination tables")

        for table, cols in TABLES:
            rows = payload[table]
            if not rows:
                continue
            collist = ", ".join(cols)
            template = "(" + ", ".join(["%s"] * len(cols)) + ")"
            conflict = "(key)" if table == "settings" else "(id)"
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO {table} ({collist}) VALUES %s "
                f"ON CONFLICT {conflict} DO NOTHING",
                rows, template=template, page_size=500,
            )
            print(f"  {table:<12} inserted")

        # Sequences must continue past the ids we forced in, or the next
        # insert from the app would collide with an existing row.
        for table in ("users", "clients", "price_list", "bills", "bill_items"):
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT MAX(id) IS NOT NULL FROM {table}))"
            )
        print("  id sequences realigned")

        pconn.commit()
    except Exception:
        pconn.rollback()
        print("\nMigration failed and was rolled back. Nothing changed.")
        raise

    # ── Verify ──────────────────────────────────────────────────────────
    print("\nVerification")
    ok = True
    for table, _ in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        dest = cur.fetchone()[0]
        src = len(payload[table])
        mark = "OK " if dest == src else "!! "
        if dest != src:
            ok = False
        print(f"  {mark}{table:<12} source {src:>6}   destination {dest:>6}")

    cur.execute("SELECT value FROM settings WHERE key = 'bill_counter'")
    row = cur.fetchone()
    print(f"\n  next bill number counter: {row[0] if row else 'not set'}")

    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    print(f"  admin accounts carried over: {cur.fetchone()[0]}")

    cur.close()
    pconn.close()

    print("\nDone." if ok else
          "\nCounts do not match — investigate before switching the office over.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
