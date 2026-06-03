@echo off
cd /d "C:\pro\callprofiler"
echo ============================================================
echo   CallProfiler - Install deps (Python 3.12 + CUDA)
echo ============================================================
echo NOTE: torch/torchaudio cu124 install separately (one time):
echo   pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
echo.
python -m pip install -r requirements-gigaam.txt
echo.
python -c "import torch,torchaudio,transformers,fastapi,uvicorn,jinja2; print('deps OK | CUDA', torch.cuda.is_available())"
echo ============================================================
pause
