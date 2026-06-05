@echo off
REM ============================================================
REM  reset.bat - CLEAN SLATE (dry-run by default).
REM    reset.bat              -> dry-run: show what would be wiped
REM    reset.bat --apply      -> backup DB, wipe ALL derived data,
REM                              then bootstrap fresh empty DB + user 'me'
REM    reset.bat --apply --no-backup  -> skip DB backup
REM  WIPES everything EXCEPT protected: ALL of C:\calls\data (DB, every
REM    profile users\*, logs, biography) + C:\calls\text + C:\calls\sync.
REM  NEVER touches: C:\calls\in (processing input) and C:\calls\source (master).
REM  DB backed up OUTSIDE data -> C:\calls\callprofiler.db.bak-<timestamp>.
REM  After apply: run startprocess.bat -> reprocesses C:\calls\in from scratch.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python "%~dp0reset.py" %*
endlocal
pause
