@echo off
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed
echo Starting on http://127.0.0.1:8000
uvicorn app.main:app --host 0.0.0.0 --port 8000
