@echo off
cd /d "C:\pro\callprofiler"
set PYTHONPATH=C:\pro\callprofiler\src
echo #################### 1/3  ENVIRONMENT ####################
python --version
python -c "import torch; print('torch', torch.__version__, '| CUDA', torch.cuda.is_available())"
python -c "import transformers; print('transformers', transformers.__version__, '(must be < 5)')"
echo.
echo #################### 2/3  UNIT TESTS ####################
python -m pytest tests/ -q
if errorlevel 1 (echo. & echo UNIT TESTS FAILED - stopping. & pause & exit /b 1)
echo.
echo #################### 3/3  PIPELINE  (C:\calls\in) ####################
python -m callprofiler bootstrap
python -m callprofiler -v watch --once
python -m callprofiler status
echo.
echo DONE.  Texts: C:\calls\text\   Report: C:\Users\SERGE\Desktop\rez.txt
echo ============================================================
pause
