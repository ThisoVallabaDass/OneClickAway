@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run.py
) else (
  python scripts\run.py
)
if errorlevel 1 pause
