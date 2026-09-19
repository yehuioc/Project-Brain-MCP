@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install.bat first.
  pause
  exit /b 1
)
set PYTHONPATH=%CD%
.venv\Scripts\python.exe scripts\mcp_protocol_test.py
pause
