@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

echo === Killing old dashboard on :8765 ===
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo === Starting dashboard on http://127.0.0.1:8765 ===
start "CallProfiler Dashboard" C:\Python312\python.exe -m callprofiler dashboard --user me --port 8765

echo === Starting pipeline watcher ===
C:\Python312\python.exe -m callprofiler -v watch
