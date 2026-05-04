echo on
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler reenrich-v2 --user serhio
python -m callprofiler graph-backfill --user serhio
python -m callprofiler graph-health --user serhio
python -m callprofiler profile-all --user serhio --limit 10
pause