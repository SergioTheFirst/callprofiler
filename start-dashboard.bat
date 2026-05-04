@echo off
REM Quick launcher for CallProfiler Dashboard
REM Opens dashboard in browser automatically

echo Starting CallProfiler Dashboard...
echo.
echo User: serhio
echo Port: 8765
echo URL: http://127.0.0.1:8765
echo.
echo Opening browser in 3 seconds...
echo Press Ctrl+C to stop the server
echo.

REM Set PYTHONPATH so imports work
set PYTHONPATH=%~dp0src

REM Open browser after 3 seconds (in background)
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8765"

REM Start dashboard server (blocking)
python "%~dp0src\callprofiler\cli\main.py" dashboard --user serhio --port 8765 --host 127.0.0.1

REM If server exits, pause to show error
pause
