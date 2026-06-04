@echo off
REM ============================================================
REM  run-watch.bat - one watch pass: ingest C:\calls\in +
REM  resume stalled calls. Full output -> run-watch.log
REM  NOTE: this picks up ALL stalled calls (there are many) and
REM  can run for a long time. For a quick role check use run-one.bat.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "LOG=%~dp0run-watch.log"
echo Running: watch --once (verbose)   log: %LOG%
python -m callprofiler -v watch --once > "%LOG%" 2>&1
echo.
echo === last 50 log lines ===
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 50 -Encoding utf8"
echo.
echo [OK] Full log: %LOG%   - send this file to Claude.
pause
