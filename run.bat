@echo off
REM AgentJerry - one-command start (Windows). Opens on http://localhost:8000
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install -q -r backend\requirements.txt
cd backend
echo.
echo   AgentJerry is starting on http://localhost:8000
echo   Sign in: priya@brightpath.example / demo1234
echo.
start "" http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
