"""One-time, non-destructive migration from a local SQLite DB to PostgreSQL.

Usage:
    DATABASE_URL='postgresql://...' python scripts/migrate_sqlite_to_postgres.py ./data/trading_signals.db

The destination must be empty. The source SQLite file is never modified.
"""
import os
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

TABLES = {
    "signals": (
        "id, created_at, symbol, timeframe, direction, entry_reference, stop_loss, "
        "take_profit, candle_time, provider, analysis_json, strategy_version"
    ),
    "paper_trades": (
        "id, signal_id, created_at, symbol, timeframe, direction, entry, stop_loss, "
        "take_profit, entry_candle_time, status, exit, exit_time, exit_reason, result_r"
    ),
}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/migrate_sqlite_to_postgres.py PATH_TO_SQLITE_DB")
    source_path = Path(sys.argv[1]).expanduser()
    if not source_path.is_file():
        raise SystemExit(f"SQLite database not found: {source_path}")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Set DATABASE_URL to your PostgreSQL connection string.")
    database_url = database_url.replace("postgres://", "postgresql://", 1)

    src = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    with psycopg.connect(database_url, row_factory=dict_row) as dst:
        counts = {
            table: dst.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in TABLES
        }
        if any(counts.values()):
            raise SystemExit(f"Destination is not empty: {counts}. Migration stopped; no rows copied.")

        source_rows = {
            table: src.execute(f"SELECT {columns} FROM {table} ORDER BY id").fetchall()
            for table, columns in TABLES.items()
        }
        for table, columns in TABLES.items():
            rows = source_rows[table]
            if not rows:
                continue
            names = [name.strip() for name in columns.split(",")]
            placeholders = ", ".join(["%s"] * len(names))
            sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            dst.executemany(sql, [tuple(row[name] for name in names) for row in rows])

        for table in TABLES:
            dst.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"EXISTS(SELECT 1 FROM {table}))",
                (table,),
            )
        dst.commit()

    src.close()
    print("Migration completed.")
    for table, rows in source_rows.items():
        print(f"{table}: {len(rows)} rows copied")


if __name__ == "__main__":
    main()
