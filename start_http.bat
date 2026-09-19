@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run install.bat first.
  pause
  exit /b 1
)
echo Project Brain MCP: http://127.0.0.1:8765/mcp
echo Keep this window open. Ctrl+C to stop.
set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m project_brain.server --transport streamable-http --host 127.0.0.1 --port 8765
