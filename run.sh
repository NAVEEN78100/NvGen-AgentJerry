#!/usr/bin/env bash
# AgentJerry — one-command start (macOS / Linux). Opens on http://localhost:8000
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then $PY -m venv .venv; fi
source .venv/bin/activate
pip install -q -r backend/requirements.txt
if [ ! -f backend/static/index.html ] && command -v npm >/dev/null; then
  (cd frontend && npm install && npm run build && rm -rf ../backend/static && cp -r dist ../backend/static)
fi
cd backend
echo ""
echo "  AgentJerry is starting on http://localhost:8000"
echo "  Sign in: priya@brightpath.example / demo1234"
echo ""
exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
