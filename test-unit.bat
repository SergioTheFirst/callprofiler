@echo off
cd /d "C:\pro\callprofiler"
set PYTHONPATH=C:\pro\callprofiler\src
echo ============================================================
echo   CallProfiler - Unit Tests (pytest)
echo ============================================================
python -m pytest tests/ -q
echo ------------------------------------------------------------
echo Exit code: %ERRORLEVEL%   (0 = all passed)
echo Stage-1 only:  python -m pytest tests/test_gigaam_runner.py tests/test_text_export.py tests/test_watcher_cleanup.py -q
echo ============================================================
pause
