@echo off
REM Daily auto-ingest wrapper. Activates venv, runs Python orchestrator, captures output.
setlocal
set ROOT=C:\home-proj\tracker\finance-app
cd /d "%ROOT%"
call ".venv\Scripts\activate.bat"

REM Date stamp for log filename (locale-independent: use PowerShell)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set RUN_DATE=%%i
if not exist "logs" mkdir "logs"

python scripts\auto_ingest.py 1>>"logs\runner_%RUN_DATE%.log" 2>&1
set RC=%ERRORLEVEL%
endlocal & exit /b %RC%
