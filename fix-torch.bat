@echo off
cd /d "C:\pro\callprofiler"
echo ============================================================
echo   Restore CUDA torch (was replaced by a CPU build)
echo ============================================================
echo Reinstalling torch 2.6.0 + torchaudio 2.6.0 (CUDA 12.4)...
python -m pip install --force-reinstall torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
echo.
python -c "import torch,torchaudio; print('torch',torch.__version__,'| torchaudio',torchaudio.__version__,'| CUDA',torch.cuda.is_available())"
echo.
echo EXPECT: torch 2.6.0+cu124 ... CUDA True
echo (If you later run install-roles.bat, run THIS again afterwards.)
pause
