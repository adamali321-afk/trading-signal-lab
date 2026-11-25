# Trading Signal Lab — MVP 1.1

A local-first Mac-friendly market-analysis and forward paper-trading app. It exposes a FastAPI backend and a browser dashboard.

## Quick start on macOS

1. Install Python 3.11 or newer.
2. Clone this repository:
   ```bash
   git clone https://github.com/adamali321-afk/trading-signal-lab.git
   cd trading-signal-lab
   ```
3. Copy `.env.example` to `.env`, then add your Twelve Data API key.
4. Start the app:
   ```bash
   chmod +x start.command
   ./start.command
   ```

The dashboard opens at `http://127.0.0.1:8000`. API documentation is at `http://127.0.0.1:8000/docs`.

## Database options

- Local development uses SQLite at `DATABASE_PATH` by default.
- Hosted deployments should set `DATABASE_URL` to a PostgreSQL connection string. When set, PostgreSQL is used instead of SQLite.
- Never commit database credentials or put them in source code. Add `DATABASE_URL` as a secret environment variable in Render.
- The app creates its tables automatically at startup.

## Moving existing SQLite data to PostgreSQL

Before changing the live Render database setting, create a PostgreSQL database and take a copy of the SQLite database you want to preserve. Then set `DATABASE_URL` in your local environment and run:

```bash
python scripts/migrate_sqlite_to_postgres.py ./data/trading_signals.db
```

The migration refuses to run if the destination already contains signals or paper trades. It copies IDs and records, then resets PostgreSQL sequences. Keep the original SQLite file unchanged until you have verified the migrated record counts and dashboard history.

**Important:** Render's current `/tmp` SQLite file is ephemeral and cannot be recovered through this code change. If you need records currently held only in the deployed container, export them before the service restarts or redeploys. Local SQLite history is a separate database and must be migrated separately.

## Safety

This is a paper-trading research application only. It has no broker connection or live order execution.
