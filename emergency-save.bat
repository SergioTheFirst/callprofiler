@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   EMERGENCY SAVE (Claude hit limits)
echo ========================================
echo.
set /p MSG="What was done before limit hit: "
echo.

cd C:\pro\callprofiler
git add -A
git commit -m "emergency: %MSG%"
git push origin main
echo [OK] Code saved.

for /f %%a in ('powershell -command "Get-Date -Format yyyy-MM-dd_HH-mm"') do set DT=%%a
set NOTE=C:\pro\callprofiler-obsidian\sessions\EMERGENCY-%DT%.md
powershell -command "$t = '# EMERGENCY %DT%' + [char]10 + [char]10 + '## Was doing:' + [char]10 + '%MSG%' + [char]10 + [char]10 + '## Next session start with:' + [char]10 + 'new-session.bat then Ctrl+V into Claude' + [char]10; [System.IO.File]::WriteAllText('%NOTE%', $t, [System.Text.Encoding]::UTF8)"

cd C:\pro\callprofiler-obsidian
git add -A
git commit -m "emergency: %MSG%"
git push origin main
echo [OK] Notes saved.
echo.
echo ========================================
echo  NEXT SESSION: just run new-session.bat
echo  and press Ctrl+V in Claude as usual
echo ========================================
pause
