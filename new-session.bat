@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   CALLPROFILER - STARTING SESSION...
echo ========================================
echo.

echo [1/4] Pulling code...
cd C:\pro\callprofiler
git pull origin main
echo.

echo [2/4] Pulling Obsidian notes...
cd C:\pro\callprofiler-obsidian
git pull origin main
echo.

echo [3/4] Creating today log in Obsidian...
for /f %%a in ('powershell -command "Get-Date -Format yyyy-MM-dd"') do set D=%%a
set FILE=C:\pro\callprofiler-obsidian\sessions\%D%.md
if not exist "%FILE%" (
    powershell -command "$t = '# Session %D%' + [char]10 + [char]10 + '## Goal' + [char]10 + [char]10 + '## Done' + [char]10 + [char]10 + '## Problems' + [char]10 + [char]10 + '## Next Step' + [char]10; [System.IO.File]::WriteAllText('%FILE%', $t, [System.Text.Encoding]::UTF8)"
    echo [OK] Created: %FILE%
) else (
    echo [OK] Log exists: %FILE%
)

echo [4/4] Copying start prompt to clipboard...
cd C:\pro\callprofiler
powershell -command "Get-Content 'start-prompt.txt' -Encoding UTF8 | Set-Clipboard"
echo [OK] Start prompt copied to clipboard!
echo.

echo ========================================
echo  LAST 5 COMMITS:
echo ========================================
git log --oneline -5
echo.
echo ========================================
echo  READY. Go to Claude and press Ctrl+V
echo ========================================
pause
