@echo off
chcp 65001 > nul
set /p MSG="What was done (commit message): "
cd C:\pro\callprofiler
git add -A
git commit -m "%MSG%"
git push origin main
echo [OK] Code pushed
cd C:\pro\callprofiler-obsidian
git add -A
git commit -m "session: %MSG%"
git push origin main
echo [OK] Obsidian pushed
echo === ALL SAVED ===
pause
