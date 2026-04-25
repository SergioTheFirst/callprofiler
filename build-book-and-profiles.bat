@echo off
REM -*- coding: utf-8 -*-
REM build-book-and-profiles.bat — Full v2 pipeline with fault tolerance
REM Usage: build-book-and-profiles.bat [serhio]

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set PYTHONPATH=C:\pro\callprofiler\src
set USER_ID=%1
if "!USER_ID!"=="" set USER_ID=serhio

set LOG_FILE=%CD%\pipeline.log
set TIMESTAMP_FORMAT=%%date:~10,4%%-%%date:~4,2%%-%%date:~7,2%% %%time:~0,2%%:%%time:~5,2%%:%%time:~8,2%%

if exist "!LOG_FILE!" (
    echo. >> "!LOG_FILE!"
    echo [!TIMESTAMP_FORMAT!] ========== PIPELINE RESTART ========== >> "!LOG_FILE!"
) else (
    (echo [!TIMESTAMP_FORMAT!] ========== PIPELINE START ==========> "!LOG_FILE!")
)

echo.
echo 📚 CallProfiler — Build Book + Profiles (v2 Pipeline)
echo User: !USER_ID!
echo Log: !LOG_FILE!
echo.

REM ─────────────────────────────────────────────────────────────────────────
REM STAGE 1: Reenrich v2 analyses (one-time LLM regeneration)
REM ─────────────────────────────────────────────────────────────────────────

echo [Stage 1/5] Reenrich v2 analyses...
echo [!TIMESTAMP_FORMAT!] Stage 1: reenrich-v2 --user !USER_ID! >> "!LOG_FILE!"

python -m callprofiler reenrich-v2 --user !USER_ID! >> "!LOG_FILE!" 2>&1
if !errorlevel! neq 0 (
    echo ❌ FAILED: reenrich-v2
    echo [!TIMESTAMP_FORMAT!] ❌ reenrich-v2 failed with code !errorlevel! >> "!LOG_FILE!"
    exit /b 1
)
echo ✅ Stage 1 complete
echo [!TIMESTAMP_FORMAT!] ✅ reenrich-v2 complete >> "!LOG_FILE!"
timeout /t 2 /nobreak >nul

REM ─────────────────────────────────────────────────────────────────────────
REM STAGE 2: Graph backfill (build entities, relations, metrics)
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo [Stage 2/5] Graph backfill...
echo [!TIMESTAMP_FORMAT!] Stage 2: graph-backfill --user !USER_ID! >> "!LOG_FILE!"

python -m callprofiler graph-backfill --user !USER_ID! >> "!LOG_FILE!" 2>&1
if !errorlevel! neq 0 (
    echo ❌ FAILED: graph-backfill
    echo [!TIMESTAMP_FORMAT!] ❌ graph-backfill failed with code !errorlevel! >> "!LOG_FILE!"
    exit /b 2
)
echo ✅ Stage 2 complete
echo [!TIMESTAMP_FORMAT!] ✅ graph-backfill complete >> "!LOG_FILE!"
timeout /t 2 /nobreak >nul

REM ─────────────────────────────────────────────────────────────────────────
REM STAGE 3: Graph health check (verify graph stability)
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo [Stage 3/5] Graph health check...
echo [!TIMESTAMP_FORMAT!] Stage 3: graph-health --user !USER_ID! >> "!LOG_FILE!"

python -m callprofiler graph-health --user !USER_ID! >> "!LOG_FILE!" 2>&1
if !errorlevel! neq 0 (
    echo ⚠️  WARNING: graph-health failed — graph may be unstable
    echo [!TIMESTAMP_FORMAT!] ⚠️  graph-health issues detected >> "!LOG_FILE!"
    echo Fix: run "python -m callprofiler graph-audit --user !USER_ID!" manually
    echo Continuing anyway...
    timeout /t 3 /nobreak >nul
) else (
    echo ✅ Stage 3 complete — graph is healthy
    echo [!TIMESTAMP_FORMAT!] ✅ graph-health passed >> "!LOG_FILE!"
)

REM ─────────────────────────────────────────────────────────────────────────
REM STAGE 4: Profile all (generate psychology profiles for all entities)
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo [Stage 4/5] Generate psychology profiles...
echo [!TIMESTAMP_FORMAT!] Stage 4: profile-all --user !USER_ID! >> "!LOG_FILE!"

python -m callprofiler profile-all --user !USER_ID! >> "!LOG_FILE!" 2>&1
if !errorlevel! neq 0 (
    echo ❌ FAILED: profile-all
    echo [!TIMESTAMP_FORMAT!] ❌ profile-all failed with code !errorlevel! >> "!LOG_FILE!"
    exit /b 3
)
echo ✅ Stage 4 complete
echo [!TIMESTAMP_FORMAT!] ✅ profile-all complete >> "!LOG_FILE!"
timeout /t 2 /nobreak >nul

REM ─────────────────────────────────────────────────────────────────────────
REM STAGE 5: Biography run (generate book chapters and annual summaries)
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo [Stage 5/5] Generate biography book...
echo [!TIMESTAMP_FORMAT!] Stage 5: biography-run --user !USER_ID! >> "!LOG_FILE!"

python -m callprofiler biography-run --user !USER_ID! >> "!LOG_FILE!" 2>&1
if !errorlevel! neq 0 (
    echo ❌ FAILED: biography-run
    echo [!TIMESTAMP_FORMAT!] ❌ biography-run failed with code !errorlevel! >> "!LOG_FILE!"
    exit /b 4
)
echo ✅ Stage 5 complete
echo [!TIMESTAMP_FORMAT!] ✅ biography-run complete >> "!LOG_FILE!"

REM ─────────────────────────────────────────────────────────────────────────
REM SUCCESS
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo ✅ PIPELINE COMPLETE
echo [!TIMESTAMP_FORMAT!] ✅✅✅ PIPELINE COMPLETE ✅✅✅ >> "!LOG_FILE!"
echo.
echo 📖 Book generated: bio_chapters, bio_books tables
echo 👤 Profiles generated: entities, entity_metrics tables
echo 📋 Log: !LOG_FILE!
echo.

timeout /t 3 /nobreak >nul
exit /b 0
