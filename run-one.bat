@echo off
REM ============================================================
REM  run-one.bat "C:\path\to\call.mp3"
REM  Process ONE call file (--force), full output -> run-one.log
REM  Tip: you can drag-and-drop an mp3 onto this .bat.
REM  Use this for a quick role check (does NOT touch other calls).
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "LOG=%~dp0run-one.log"
if "%~1"=="" (
  echo Usage: run-one.bat "C:\calls\in\call.mp3"
  echo   or drag-and-drop an mp3 file onto this .bat
  pause
  exit /b 1
)
echo Processing "%~1"
echo Log file: %LOG%
python -m callprofiler -v process "%~1" --user me --force > "%LOG%" 2>&1
echo.
echo === last 40 log lines ===
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 40 -Encoding utf8"
echo.
echo [OK] Full log: %LOG%   - send this file to Claude.
pause
