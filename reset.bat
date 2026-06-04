@echo off
REM ============================================================
REM  reset.bat - CLEAN START (dry-run by default).
REM    reset.bat            -> dry-run: show what would be wiped
REM    reset.bat --apply    -> backup DB, wipe DB + derived data,
REM                            then bootstrap a fresh empty DB + user 'me'
REM    reset.bat --apply --keep-files  -> wipe only the DB
REM  NEVER touches sources: C:\calls\in and C:\calls\source.
REM  The old DB is backed up to ...\callprofiler.db.bak-<timestamp>.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python "%~dp0reset.py" %*
endlocal
pause
