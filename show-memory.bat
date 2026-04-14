@echo off
cd C:\pro\callprofiler
echo === CONTINUITY.md ===
powershell -command "Get-Content CONTINUITY.md ^| Select-Object -Last 50"
echo.
echo === Последние коммиты ===
git log --oneline -10
pause
