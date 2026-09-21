@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
echo Project Brain MCP - secure ChatGPT connection
echo Keep this window open. Ctrl+C stops the tunnel and local MCP child.
.venv\Scripts\python.exe scripts\tunnel.py start
pause
