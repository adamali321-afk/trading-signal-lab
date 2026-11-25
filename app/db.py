import json
import sqlite3
from datetime import datetime, timezone

from .config import DATABASE_PATH, DATABASE_URL, STRATEGY_VERSION


def _is_postgres():
    return bool(DATABASE_URL)


def _sql(statement):
    return statement.replace("?", "%s") if _is_postgres() else statement


def connect():
    if _is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        return psycopg.connect(url, row_factory=dict_row)

    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with connect() as c:
        if _is_postgres():
            c.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_reference DOUBLE PRECISION,
                    stop_loss DOUBLE PRECISION,
                    take_profit DOUBLE PRECISION,
                    candle_time TEXT,
                    provider TEXT,
                    analysis_json TEXT NOT NULL,
                    strategy_version TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id BIGSERIAL PRIMARY KEY,
                    signal_id BIGINT NOT NULL UNIQUE REFERENCES signals(id),
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry DOUBLE PRECISION NOT NULL,
                    stop_loss DOUBLE PRECISION NOT NULL,
                    take_profit DOUBLE PRECISION NOT NULL,
                    entry_candle_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    exit DOUBLE PRECISION,
                    exit_time TEXT,
                    exit_reason TEXT,
                    result_r DOUBLE PRECISION
                )
            """)
        else:
            c.execute("CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, direction TEXT NOT NULL, entry_reference REAL, stop_loss REAL, take_profit REAL, candle_time TEXT, provider TEXT, analysis_json TEXT NOT NULL, strategy_version TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS paper_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id INTEGER NOT NULL UNIQUE REFERENCES signals(id), created_at TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, direction TEXT NOT NULL, entry REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL, entry_candle_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', exit REAL, exit_time TEXT, exit_reason TEXT, result_r REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_paper_open ON paper_trades(status,symbol,timeframe)")


def save_signal(symbol, timeframe, analysis, provider):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as c:
        cur = c.execute(_sql("INSERT INTO signals(created_at,symbol,timeframe,direction,entry_reference,stop_loss,take_profit,candle_time,provider,analysis_json,strategy_version) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id"), (now, symbol, timeframe, analysis['direction'], analysis.get('entry_reference'), analysis.get('stop_loss'), analysis.get('take_profit'), analysis['last_candle_time'], provider, json.dumps(analysis), STRATEGY_VERSION))
        signal_id = cur.fetchone()['id']
        trade_opened = False
        if analysis['direction'] in ('LONG', 'SHORT'):
            existing = c.execute(_sql("SELECT id FROM paper_trades WHERE symbol=? AND timeframe=? AND direction=? AND entry_candle_time=?"), (symbol, timeframe, analysis['direction'], analysis['last_candle_time'])).fetchone()
            if not existing:
                c.execute(_sql("INSERT INTO paper_trades(signal_id,created_at,symbol,timeframe,direction,entry,stop_loss,take_profit,entry_candle_time) VALUES(?,?,?,?,?,?,?,?,?)"), (signal_id, now, symbol, timeframe, analysis['direction'], analysis['entry_reference'], analysis['stop_loss'], analysis['take_profit'], analysis['last_candle_time']))
                trade_opened = True
        return int(signal_id), trade_opened


def list_signals(limit=100):
    with connect() as c:
        rows = c.execute(_sql("SELECT * FROM signals ORDER BY id DESC LIMIT ?"), (limit,)).fetchall()
    return [dict(r) | {'analysis': json.loads(r['analysis_json'])} for r in rows]


def list_trades(status=None, limit=200):
    with connect() as c:
        if status:
            rows = c.execute(_sql("SELECT * FROM paper_trades WHERE status=? ORDER BY id DESC LIMIT ?"), (status, limit)).fetchall()
        else:
            rows = c.execute(_sql("SELECT * FROM paper_trades ORDER BY id DESC LIMIT ?"), (limit,)).fetchall()
    return [dict(r) for r in rows]


def update_trade(trade_id, exit_price, exit_time, reason, result_r):
    with connect() as c:
        c.execute(_sql("UPDATE paper_trades SET status='CLOSED',exit=?,exit_time=?,exit_reason=?,result_r=? WHERE id=? AND status='OPEN'"), (exit_price, exit_time, reason, result_r, trade_id))


def update_open_trades(symbol, timeframe, candles):
    closed = []
    with connect() as c:
        rows = c.execute(_sql("SELECT * FROM paper_trades WHERE status='OPEN' AND symbol=? AND timeframe=?"), (symbol, timeframe)).fetchall()
    for trade in rows:
        for candle in candles:
            if candle.datetime <= trade['entry_candle_time']:
                continue
            stop_hit = candle.low <= trade['stop_loss'] if trade['direction'] == 'LONG' else candle.high >= trade['stop_loss']
            target_hit = candle.high >= trade['take_profit'] if trade['direction'] == 'LONG' else candle.low <= trade['take_profit']
            if not stop_hit and not target_hit:
                continue
            if stop_hit:
                price = trade['stop_loss']
                reason = 'STOP_LOSS'
                r = -1.0
            else:
                price = trade['take_profit']
                reason = 'TAKE_PROFIT'
                r = 2.0
            update_trade(trade['id'], price, candle.datetime, reason, r)
            closed.append(trade['id'])
            break
    return closed


def performance():
    with connect() as c:
        rows = c.execute("SELECT * FROM paper_trades WHERE status='CLOSED' ORDER BY id ASC LIMIT 10000").fetchall()
    trades = [dict(r) for r in rows]
    rs = [float(t['result_r']) for t in trades if t['result_r'] is not None]
    wins = sum(1 for x in rs if x > 0)
    losses = sum(1 for x in rs if x < 0)
    gross_win = sum(x for x in rs if x > 0)
    gross_loss = abs(sum(x for x in rs if x < 0))
    equity = peak = max_dd = 0.0
    for x in rs:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {'closed_trades': len(rs), 'open_trades': len(list_trades('OPEN', 10000)), 'wins': wins, 'losses': losses, 'win_rate_pct': round(wins / len(rs) * 100, 2) if rs else None, 'net_r': round(sum(rs), 2), 'expectancy_r': round(sum(rs) / len(rs), 3) if rs else None, 'profit_factor': round(gross_win / gross_loss, 2) if gross_loss else (None if not gross_win else 'infinite'), 'max_drawdown_r': round(max_dd, 2), 'note': 'Paper simulation only. Intrabar order is unknown; stop is assumed first when stop and target are both touched.'}


def _local_day(value):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
    except (TypeError, ValueError):
        return None


def daily_reports(days=30):
    """Aggregate signals by creation day and paper-trade outcomes by resolution day."""
    from datetime import date, timedelta

    days = max(1, min(int(days), 365))
    today = datetime.now(timezone.utc).astimezone().date()
    start = today - timedelta(days=days - 1)
    with connect() as c:
        signals = c.execute("SELECT created_at, direction FROM signals ORDER BY id DESC LIMIT 50000").fetchall()
        trades = c.execute("SELECT created_at, exit_time, result_r, status FROM paper_trades ORDER BY id DESC LIMIT 50000").fetchall()

    buckets = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        buckets[day] = {"date": day, "signals": 0, "paper_trades_opened": 0, "resolved": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "net_r": 0.0}

    for row in signals:
        day = _local_day(row["created_at"])
        if day in buckets:
            buckets[day]["signals"] += 1

    for row in trades:
        opened_day = _local_day(row["created_at"])
        if opened_day in buckets:
            buckets[opened_day]["paper_trades_opened"] += 1
        resolved_day = _local_day(row["exit_time"])
        if resolved_day in buckets and row["status"] == "CLOSED":
            item = buckets[resolved_day]
            item["resolved"] += 1
            result = float(row["result_r"] or 0)
            item["net_r"] += result
            if result > 0:
                item["wins"] += 1
            elif result < 0:
                item["losses"] += 1

    output = []
    for item in buckets.values():
        resolved = item["wins"] + item["losses"]
        item["win_rate_pct"] = round(item["wins"] / resolved * 100, 2) if resolved else None
        item["net_r"] = round(item["net_r"], 2)
        output.append(item)
    return {"timezone": "Europe/Berlin", "days": output, "note": "Win rate includes resolved paper trades only. Open positions are not counted as wins or losses; outcomes are grouped by the day the stop or target was reached."}
