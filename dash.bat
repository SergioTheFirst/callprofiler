@echo off
REM ============================================================
REM  CallProfiler dashboard (real-time).
REM  WAL-reader fixed: now sees LIVE pipeline writes.
REM  Run this, then open:  http://127.0.0.1:8765
REM ============================================================
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler dashboard --user me --port 8765
