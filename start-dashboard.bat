@echo off
set PYTHONPATH=C:\pro\callprofiler\src

echo.
echo ============================================================
echo   CallProfiler Dashboard - Real-time Pipeline Monitor
echo ============================================================
echo   User: serhio
echo   Port: 8765
echo   URL:  http://127.0.0.1:8765
echo ============================================================
echo.
echo Starting dashboard server...
echo Press Ctrl+C to stop
echo.

REM Open browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8765"

REM Start dashboard
python -m callprofiler dashboard --user serhio --port 8765 --host 127.0.0.1

pause