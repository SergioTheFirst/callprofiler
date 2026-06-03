@echo off
cd /d "C:\pro\callprofiler"
set PYTHONPATH=C:\pro\callprofiler\src
echo ============================================================
echo   CallProfiler - Stage-1 Pipeline Test
echo   Processes ALL settled audio in C:\calls\in (recursive)
echo ============================================================
echo.
echo [1/3] bootstrap  (folders + DB + user 'me')
python -m callprofiler bootstrap
echo.
echo [2/3] process incoming  (one pass: scan -^> transcribe -^> DB -^> .txt -^> cleanup)
python -m callprofiler -v watch --once
echo.
echo [3/3] queue status
python -m callprofiler status
echo ------------------------------------------------------------
echo Texts:   C:\calls\text\
echo Report:  C:\Users\SERGE\Desktop\rez.txt
echo Note: LLM step needs llama-server on :8080 (else skipped gracefully).
echo ============================================================
pause
