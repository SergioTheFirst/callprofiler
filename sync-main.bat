@echo off
REM ============================================================
REM  sync-main.bat - FORCE overwrite this folder from GitHub
REM  (origin/main). Local edits to TRACKED files are discarded.
REM  C:\calls (DB, audio) is NOT touched by git.
REM ============================================================
setlocal
cd /d "%~dp0"
echo [1/4] remote...
git remote remove origin 2>nul
git remote add origin https://github.com/SergioTheFirst/callprofiler.git
echo [2/4] fetch...
git fetch origin
if errorlevel 1 goto err
echo [3/4] hard reset to origin/main...
git reset --hard origin/main
if errorlevel 1 goto err
echo [4/4] current commit:
git log -1 --oneline
echo.
echo [OK] Folder synced with GitHub origin/main.
goto end
:err
echo.
echo [ERROR] git failed.
echo   - "dubious ownership": run this once, then re-run sync-main.bat:
echo        git config --global --add safe.directory C:/pro/callprofiler
echo   - asks for login/password: repo is private - tell Claude.
:end
echo.
pause
