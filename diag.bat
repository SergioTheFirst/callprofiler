@echo off
cd /d "C:\pro\callprofiler"
set PYTHONPATH=C:\pro\callprofiler\src
set OUT=C:\Users\SERGE\Desktop\diag.txt
echo ============================================================
echo   CallProfiler diagnostics -^> %OUT%
echo   (GigaAM load test in the end may take ~20-60s)
echo ============================================================
python -u diag.py > "%OUT%" 2>&1
echo.
echo ==== DONE. Full report saved to: %OUT% ====
echo ---- contents below (copy ALL of it to the developer) ----
echo.
type "%OUT%"
echo.
echo ==== END (file: %OUT%) ====
pause
