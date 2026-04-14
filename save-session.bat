@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   CALLPROFILER - SAVING SESSION...
echo ========================================
echo.
set /p MSG="One line - what was done: "
echo.

echo [1/2] Pushing code...
cd C:\pro\callprofiler
git add -A
git commit -m "%MSG%"
git push origin main
echo [OK] Code saved.
echo.

echo [2/2] Pushing Obsidian...
cd C:\pro\callprofiler-obsidian
git add -A
git commit -m "session: %MSG%"
git push origin main
echo [OK] Notes saved.
echo.

echo ========================================
echo  ALL SAVED. Session complete.
echo ========================================
pause
