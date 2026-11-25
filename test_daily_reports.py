from datetime import datetime, timezone\nfrom zoneinfo import ZoneInfo

from app import db


def test_daily_reports_count_only_resolved_trades_by_resolution_day(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", "")
    monkeypatch.setattr(db, "DATABASE_PATH", str(tmp_path / "reports.sqlite3"))
    db.init_db()

    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        for direction, result, status in (
            ("LONG", 2.0, "CLOSED"),
            ("SHORT", -1.0, "CLOSED"),
            ("LONG", None, "OPEN"),
        ):
            cur = conn.execute(
                """INSERT INTO signals
                (created_at,symbol,timeframe,direction,analysis_json,strategy_version)
                VALUES(?,?,?,?,?,?)""",
                (now, "NVDA", "15min", direction, "{}", "test"),
            )
            conn.execute(
                """INSERT INTO paper_trades
                (signal_id,created_at,symbol,timeframe,direction,entry,stop_loss,
                 take_profit,entry_candle_time,status,exit,exit_time,exit_reason,result_r)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cur.lastrowid, now, "NVDA", "15min", direction, 100.0, 95.0,
                    110.0, now, status,
                    110.0 if result and result > 0 else 95.0 if result else None,
                    now if status == "CLOSED" else None,
                    "TAKE_PROFIT" if result and result > 0 else "STOP_LOSS" if result else None,
                    result,
                ),
            )

    report = db.daily_reports(days=3)
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
    item = next(day for day in report["days"] if day["date"] == today)
    assert item["signals"] == 3
    assert item["paper_trades_opened"] == 3
    assert item["resolved"] == 2
    assert item["wins"] == 1
    assert item["losses"] == 1
    assert item["win_rate_pct"] == 50.0
    assert item["net_r"] == 1.0
