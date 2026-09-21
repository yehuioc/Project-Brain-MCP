@echo off
setlocal
cd /d "%~dp0"
if not exist .runtime\tmp mkdir .runtime\tmp
set TEMP=%CD%\.runtime\tmp
set TMP=%TEMP%
set PIP_CACHE_DIR=%CD%\.runtime\pip-cache
set PYTHONUTF8=1
echo [1/4] Checking Python...
python --version || goto :nopython
for /f "tokens=*" %%i in ('python -c "import sys; print(int(sys.version_info >= (3,10)))"') do set PYOK=%%i
if not "%PYOK%"=="1" (
  echo Python 3.10 or newer is required.
  pause
  exit /b 1
)
echo [2/4] Creating virtual environment...
if not exist .venv python -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
echo [3/4] Installing MCP SDK...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || exit /b 1
echo [4/4] Running self tests...
python scripts\self_test.py || exit /b 1
python scripts\mcp_protocol_test.py || exit /b 1
if not exist data\projects.json echo {"projects":[],"security":{}} > data\projects.json
echo.
echo Installation complete.
echo Next: run configure_project.bat, then start_http.bat or configure your MCP host for stdio.
pause
exit /b 0
:nopython
echo Python was not found. Install Python 3.10+ and enable "Add Python to PATH".
pause
exit /b 1
