@echo off
cd /d "%~dp0"

set PYTHONDONTWRITEBYTECODE=1
set PYTHONUNBUFFERED=1

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -O start_app.py
) else (
    python -O start_app.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] Startup failed. Check errors above.
    pause
)
