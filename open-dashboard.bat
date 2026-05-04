@echo off
REM Quick launcher for CallProfiler Dashboard with auto-browser
REM Opens dashboard server and browser in parallel

echo Starting CallProfiler Dashboard...
echo.
echo User: serhio
echo Port: 8765
echo URL: http://127.0.0.1:8765
echo.

REM Set Python path
set PYTHONPATH=C:\pro\callprofiler\src

REM Start dashboard server in background
start "CallProfiler Dashboard" cmd /c "python -m callprofiler dashboard --user serhio --port 8765 --host 127.0.0.1"

REM Wait 3 seconds for server to start
timeout /t 3 /nobreak >nul

REM Open browser
start http://127.0.0.1:8765

echo.
echo Dashboard opened in browser
echo To stop the server, close the "CallProfiler Dashboard" window
echo.
pause
