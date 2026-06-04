@echo off
REM ============================================================
REM  Liveness probe: does the dashboard see LIVE DB writes?
REM  Run this WHILE the pipeline is processing files.
REM  If MAX(updated_at) / counts change between the two samples,
REM  real-time works.
REM ============================================================
set PYTHONPATH=C:\pro\callprofiler\src
python C:\pro\callprofiler\dash_check.py
pause
