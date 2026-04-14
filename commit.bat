@echo off 
set /p MSG="Commit: " 
cd C:\pro\callprofiler 
git add -A 
git commit -m "%%MSG%%" 
git push origin main 
