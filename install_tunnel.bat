@echo off
setlocal
cd /d "%~dp0"
.venv\Scripts\python.exe scripts\install_tunnel.py
pause
