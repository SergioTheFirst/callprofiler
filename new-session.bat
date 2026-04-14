@echo off
chcp 65001 > nul
cd C:\pro\callprofiler-obsidian
git pull origin main
for /f "tokens=1,2,3 delims=." %%a in ('powershell -command "Get-Date -Format dd.MM.yyyy"') do set D=%%c-%%b-%%a
set FILE=C:\pro\callprofiler-obsidian\sessions\%D%.md
if not exist "%FILE%" (
    powershell -command "$content = '# Session %D%`n`n## Goal`n`n## Done`n`n## Problems`n`n## Next Step`n'; [System.IO.File]::WriteAllText('%FILE%', $content, [System.Text.Encoding]::UTF8)"
    echo [Created: %FILE%]
) else (
    echo [Log exists: %FILE%]
)
cd C:\pro\callprofiler
git pull origin main
echo.
echo === CONTINUITY.md - last 30 lines ===
powershell -command "Get-Content CONTINUITY.md -Encoding UTF8 | Select-Object -Last 30"
echo.
pause
