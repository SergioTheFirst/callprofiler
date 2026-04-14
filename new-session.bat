@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   CALLPROFILER - START SESSION
echo ========================================
echo.

echo [1/4] Git status...
cd C:\pro\callprofiler
git pull origin main
echo.

echo [2/4] Obsidian pull...
cd C:\pro\callprofiler-obsidian
git pull origin main
echo.

echo [3/4] Creating today log...
cd C:\pro\callprofiler-obsidian
for /f %%a in ('powershell -command "Get-Date -Format yyyy-MM-dd"') do set D=%%a
set FILE=C:\pro\callprofiler-obsidian\sessions\%D%.md
if not exist "%FILE%" (
    powershell -command "$t = '# Session %D%' + [char]10 + [char]10 + '## Goal' + [char]10 + [char]10 + '## Done' + [char]10 + [char]10 + '## Problems' + [char]10 + [char]10 + '## Next Step' + [char]10; [System.IO.File]::WriteAllText('%FILE%', $t, [System.Text.Encoding]::UTF8)"
    echo [OK] Created: %FILE%
) else (
    echo [OK] Log exists: %FILE%
)
echo.

echo [4/4] Copying start prompt to clipboard...
cd C:\pro\callprofiler
powershell -command "Get-Content 'start-prompt.txt' -Encoding UTF8 | Set-Clipboard"
echo [OK] Prompt copied - go to Claude and press Ctrl+V
echo.

echo ========================================
echo   LAST 5 COMMITS:
echo ========================================
git log --oneline -5
echo.
echo ========================================
echo   READY. Press Ctrl+V in Claude.
echo ========================================
pause


