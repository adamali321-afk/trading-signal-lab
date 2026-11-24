#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then cp .env.example .env; fi

# Use reliable pure-Python asyncio/http implementations on macOS.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop asyncio --http h11 &
SERVER_PID=$!

cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for i in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    open "http://127.0.0.1:8000"
    break
  fi
  sleep 0.25
done

wait "$SERVER_PID"
