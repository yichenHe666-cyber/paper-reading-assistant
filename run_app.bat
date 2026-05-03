@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe start_app.py
) else (
    python start_app.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] Startup failed. Check errors above.
    pause
)
