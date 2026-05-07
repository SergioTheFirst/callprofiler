@echo off
setlocal enabledelayedexpansion

set "PYTHONPATH=C:\pro\callprofiler\src"
set "USER_ID=%1"
if "!USER_ID!"=="" set "USER_ID=serhio"
set "LOG_FILE=%CD%\pipeline.log"

echo.
echo ============================================================
echo   CallProfiler - Build Book + Profiles (v2 Pipeline)
echo ============================================================
echo   User:     !USER_ID!
echo   Log:      !LOG_FILE!
echo   Console:  per-file progress visible here
echo   LLM:      http://localhost:8080
echo ============================================================
echo.

echo Checking LLM server...
curl -s -o nul --connect-timeout 3 http://localhost:8080/health 2>nul
if errorlevel 1 (
    echo   [WARN] LLM server not responding
    echo          Run C:\llama\start.bat first
    echo.
) else (
    echo   [OK]  LLM server reachable
    echo.
)

REM ---- Stage 1 -----------------------------------------------------------
echo ------------------------------------------------------------
echo [Stage 1/6] Enrich unprocessed calls
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" bulk-enrich --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** FAILED: bulk-enrich
    echo *** Log: !LOG_FILE!
    pause
    exit /b 1
)
echo [OK] Stage 1 done
timeout /t 2 /nobreak >nul

REM ---- Stage 2 -----------------------------------------------------------
echo.
echo ------------------------------------------------------------
echo [Stage 2/6] Reenrich v2 analyses
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" reenrich-v2 --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** Note: reenrich-v2 returned non-zero
    echo *** This is OK if all analyses are already v2
    echo *** Continuing...
    timeout /t 2 /nobreak >nul
) else (
    echo [OK] Stage 2 done
    timeout /t 2 /nobreak >nul
)

REM ---- Stage 3 -----------------------------------------------------------
echo.
echo ------------------------------------------------------------
echo [Stage 3/6] Graph backfill
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" graph-backfill --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** FAILED: graph-backfill
    echo *** Log: !LOG_FILE!
    pause
    exit /b 3
)
echo [OK] Stage 3 done
timeout /t 2 /nobreak >nul

REM ---- Stage 4 -----------------------------------------------------------
echo.
echo ------------------------------------------------------------
echo [Stage 4/6] Graph health check
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" graph-health --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** WARNING: graph-health issues detected
    echo *** Fix: python -m callprofiler graph-audit --user "!USER_ID!"
    echo *** Continuing...
    timeout /t 3 /nobreak >nul
) else (
    echo [OK] Stage 4 - graph healthy
)

REM ---- Stage 5 -----------------------------------------------------------
echo.
echo ------------------------------------------------------------
echo [Stage 5/6] Generate psychology profiles
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" profile-all --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** FAILED: profile-all
    echo *** Log: !LOG_FILE!
    pause
    exit /b 5
)
echo [OK] Stage 5 done
timeout /t 2 /nobreak >nul

REM ---- Stage 6 -----------------------------------------------------------
echo.
echo ------------------------------------------------------------
echo [Stage 6/6] Generate biography book
echo ------------------------------------------------------------
echo.

python -m callprofiler --log-file "!LOG_FILE!" biography-run --user "!USER_ID!"
if errorlevel 1 (
    echo.
    echo *** FAILED: biography-run
    echo *** Log: !LOG_FILE!
    pause
    exit /b 6
)
echo [OK] Stage 6 done

echo.
echo ============================================================
echo   PIPELINE COMPLETE - !DATE! !TIME!
echo ============================================================
echo   Log: !LOG_FILE!
echo ============================================================
echo.

pause
exit /b 0