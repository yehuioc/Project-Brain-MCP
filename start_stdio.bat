@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe exit /b 1
set PYTHONPATH=%CD%
.venv\Scripts\python.exe -m project_brain.server --transport stdio
