@echo off
set /p MSG="Что сделано: "
cd C:\pro\callprofiler
git add -A
git commit -m "%%MSG%%"
git push origin main
echo [OK] Код запушен
cd C:\pro\callprofiler-obsidian
git add -A
git commit -m "session: %%MSG%%"
git push origin main
echo [OK] Obsidian запушен
echo === ВСЁ СОХРАНЕНО ===
pause
