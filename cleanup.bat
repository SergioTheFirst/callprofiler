@echo off
REM cleanup.bat - passthrough to cleanup.py (dry-run by default; add --apply to delete)
REM   cleanup.bat prune-missing --user me
REM   cleanup.bat prune-missing --user me --apply
REM   cleanup.bat purge-user --user serhio
REM   cleanup.bat purge-user --user serhio --apply
setlocal
set PYTHONPATH=%~dp0src
python "%~dp0cleanup.py" %*
endlocal
