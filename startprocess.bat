@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python -m callprofiler -v watch
