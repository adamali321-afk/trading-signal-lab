# Trading Signal Lab — MVP 1.0

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

## Manual start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Safety

This is a paper-trading research application only. It has no broker connection or live order execution.
