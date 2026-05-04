@echo off
set PYTHONPATH=C:\pro\callprofiler\src
echo Running p2_entities with resume support...
python -m callprofiler biography-run --user serhio --passes p2_entities --max-retries 3
echo.
echo Checking status after run...
python -m callprofiler biography-status --user serhio
pause
