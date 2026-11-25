"""Import a protected Render JSON export into an empty Neon PostgreSQL database.

Usage:
  DATABASE_URL='postgresql://...' python scripts/import_render_export.py render_export.json

The export is preserved as-is. Destination must be empty; inserts are atomic.
"""
import json
import os
import math
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.db import init_db

TABLES = {
    "signals": [
        "id", "created_at", "symbol", "timeframe", "direction",
        "entry_reference", "stop_loss", "take_profit", "candle_time",
        "provider", "analysis_json", "strategy_version"
    ],
    "paper_trades": [
        "id", "signal_id", "created_at", "symbol", "timeframe", "direction",
        "entry", "stop_loss", "take_profit", "entry_candle_time", "status",
        "exit", "exit_time", "exit_reason", "result_r"
    ],
}


def normalize(value):
    if isinstance(value, float):
        return round(value, 12) if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_render_export.py EXPORT_JSON")
    export_file = Path(sys.argv[1]).expanduser().resolve()
    if not export_file.is_file():
        raise SystemExit(f"Export file not found: {export_file}")
    url = os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://", 1)
    if not url:
        raise SystemExit("Set DATABASE_URL to your Neon connection string.")

    payload = json.loads(export_file.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise SystemExit("Unsupported export schema version.")
    rows = {table: payload.get(table) for table in TABLES}
    if any(not isinstance(rows[t], list) for t in TABLES):
        raise SystemExit("Export missing one or more table arrays.")
    reported = payload.get("counts", {})
    for table in TABLES:
        if reported.get(table) != len(rows[table]):
            raise SystemExit(f"Export count mismatch for {table}.")

    init_db()
    with psycopg.connect(url, row_factory=dict_row) as dst:
        counts = {table: dst.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in TABLES}
        if any(counts.values()):
            raise SystemExit(f"Neon destination is not empty: {counts}; stopped without importing.")
        for table, columns in TABLES.items():
            records = rows[table]
            if records:
                sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
                dst.executemany(sql, [tuple(record.get(col) for col in columns) for record in records])
        for table in TABLES:
            dst.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"EXISTS(SELECT 1 FROM {table}))"
            )
        # Validate exact IDs and row counts before commit; transaction rolls back on failure.
        for table in TABLES:
            source_ids = [row["id"] for row in rows[table]]
            dest_ids = [row["id"] for row in dst.execute(f"SELECT id FROM {table} ORDER BY id").fetchall()]
            if source_ids != dest_ids:
                raise RuntimeError(f"Verification failed for {table}: IDs differ.")
            if len(dest_ids) != reported[table]:
                raise RuntimeError(f"Verification failed for {table}: row count differs.")
            dest_rows = dst.execute(
                f"SELECT {', '.join(TABLES[table])} FROM {table} ORDER BY id"
            ).fetchall()
            for idx, (src_record, dest_record) in enumerate(zip(rows[table], dest_rows)):
                src_normalized = normalize({col: src_record.get(col) for col in TABLES[table]})
                dest_normalized = normalize(dict(dest_record))
                if src_normalized != dest_normalized:
                    raise RuntimeError(
                        f"Verification failed for {table} record index {idx}, id={src_record['id']}: field values differ."
                    )
    print(f"Imported export timestamp: {payload.get('exported_at')}")
    for table in TABLES:
        print(f"{table}: {reported[table]} rows imported and verified (counts, IDs, and field values match)")


if __name__ == "__main__":
    main()
