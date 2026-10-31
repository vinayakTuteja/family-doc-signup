#!/usr/bin/env bash
# Start the site on your computer for testing (Mac or Linux). Usage: ./run_local.sh
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"; exit 1; }

if [ ! -d .venv ]; then
  echo "First run: setting things up (about a minute)..."
  $PY -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

export DEV_MODE=true EMAIL_BACKEND=console ADMIN_PASSWORD=dev RUN_RETENTION_IN_APP=false
export DATABASE_PATH=data/local.db OUTBOX_DIR=data/outbox BASE_URL=http://localhost:8000

echo ""
echo "Site:        http://localhost:8000"
echo "Test inbox:  http://localhost:8000/dev/outbox"
echo "Admin:       http://localhost:8000/admin   (user: admin, password: dev)"
echo "Press Ctrl+C to stop."
echo ""
uvicorn app.main:app --port 8000
