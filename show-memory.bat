@echo off
chcp 65001 > nul
cd C:\pro\callprofiler
echo === CONTINUITY.md - last 50 lines ===
powershell -command "Get-Content CONTINUITY.md -Encoding UTF8 | Select-Object -Last 50"
echo.
echo === Last 10 commits ===
git log --oneline -10
echo.
pause
