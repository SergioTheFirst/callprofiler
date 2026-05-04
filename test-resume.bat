@echo off
setlocal enabledelayedexpansion

set "PYTHONPATH=C:\pro\callprofiler\src"
set "USER_ID=serhio"
set "LOG_FILE=%CD%\test-resume.log"

echo.
echo ============================================================
echo   Test Biography Resume - p2_entities only
echo ============================================================
echo   User:     !USER_ID!
echo   Log:      !LOG_FILE!
echo ============================================================
echo.

echo Checking LLM server...
curl -s -o nul --connect-timeout 3 http://localhost:8080/health 2>nul
if !errorlevel! neq 0 (
    echo   [WARN] LLM server not responding
    pause
    exit /b 1
) else (
    echo   [OK]  LLM server reachable
    echo.
)

echo Running biography-run with p2_entities pass only...
echo.

python src\callprofiler\cli\main.py --log-file "!LOG_FILE!" biography-run --user "!USER_ID!" --passes p2_entities 2>&1

if !errorlevel! neq 0 (
    echo.
    echo *** FAILED: biography-run p2_entities (code !errorlevel!)
    echo *** Log: !LOG_FILE!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   TEST COMPLETE
echo ============================================================
echo.

pause
exit /b 0
