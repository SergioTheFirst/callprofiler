@echo off
chcp 65001 > nul
REM ============================================================
REM  Generate personality characteristics (dashboard: "click name - know all")
REM  Run on the box AFTER calls processing (watch is done).
REM  user = me. Russian localization is presentation-only, DB untouched:
REM  no restart needed for that. This bat rebuilds the underlying DATA.
REM ============================================================
REM  Notes:
REM   - chcp 65001 + UTF-8 source -> cmd.exe parses cyrillic text safely.
REM   - All comments and echo lines kept in English to avoid OEM codepage issues.
REM   - graph-replay returns exit code 2 on ASSERT FAILED (orphan events etc.)
REM     which is diagnostic, NOT fatal. We log it and keep going.
REM   - pause at the end keeps the window open so errors are visible.
REM ============================================================
setlocal
set PYTHONPATH=C:\pro\callprofiler\src
set USER=me
cd /d C:\pro\callprofiler

echo === [1/4] Graph: rebuild + health check (det, no GPU) ===
python -m callprofiler graph-replay --user %USER%
if %errorlevel% neq 0 echo [!] graph-replay returned exit code %errorlevel% (continuing anyway)
python -m callprofiler graph-health --user %USER%
if %errorlevel% neq 0 echo [!] graph-health returned exit code %errorlevel% (psycho-profile may be incomplete)

echo === [2/4] Archetypes + features + entity-contact link (numpy, no GPU) ===
python -m callprofiler features-build --user %USER%
if %errorlevel% neq 0 echo [!] features-build returned exit code %errorlevel% (continuing anyway)
python -m callprofiler archetypes-fit --user %USER%
if %errorlevel% neq 0 echo [!] archetypes-fit returned exit code %errorlevel% (continuing anyway)
python -m callprofiler person-link --user %USER%
if %errorlevel% neq 0 echo [!] person-link returned exit code %errorlevel% (continuing anyway)

echo === [3/4] Age estimation: deterministic part (no LLM) ===
python -m callprofiler age-estimate --user %USER%
if %errorlevel% neq 0 echo [!] age-estimate returned exit code %errorlevel% (continuing anyway)

echo.
echo === [4/4] LLM part: ONLY when llama-server is ALIVE and ASR is OFF ===
echo     (GPU is sequential - ASR and LLM at the same time = OOM)
echo     Uncomment lines below once llama-server is up:
echo.
REM python -m callprofiler profile-all --user %USER%
REM python -m callprofiler age-estimate --user %USER% --llm

echo === Done. Open the dashboard and check the dossier. ===
pause
endlocal
