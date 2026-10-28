#!/usr/bin/env bash
set -e
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
python -m app.seed
echo "Starting on http://127.0.0.1:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000
