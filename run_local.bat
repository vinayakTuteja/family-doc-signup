@echo off
REM Start the site on your computer for testing (Windows). Double-click this file.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo First run: setting things up, about a minute...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

set DEV_MODE=true
set EMAIL_BACKEND=console
set ADMIN_PASSWORD=dev
set RUN_RETENTION_IN_APP=false
set DATABASE_PATH=data/local.db
set OUTBOX_DIR=data/outbox
set BASE_URL=http://localhost:8000

echo.
echo Site:        http://localhost:8000
echo Test inbox:  http://localhost:8000/dev/outbox
echo Admin:       http://localhost:8000/admin   (user: admin, password: dev)
echo Close this window to stop.
echo.
uvicorn app.main:app --port 8000
pause
