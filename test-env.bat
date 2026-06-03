@echo off
cd /d "C:\pro\callprofiler"
set PYTHONPATH=C:\pro\callprofiler\src
echo ============================================================
echo   CallProfiler - Environment Check
echo ============================================================
python --version
python -c "import torch; print('torch', torch.__version__, '| CUDA available:', torch.cuda.is_available())"
python -c "import torchaudio, transformers; print('torchaudio', torchaudio.__version__, '| transformers', transformers.__version__)"
where ffmpeg >nul 2>&1 && (echo ffmpeg: OK) || (echo ffmpeg: NOT FOUND in PATH)
if exist "C:\models\GigaAM-v3-rnnt\config.json" (echo model:  C:\models\GigaAM-v3-rnnt OK) else (echo model:  NOT FOUND at C:\models\GigaAM-v3-rnnt)
echo ------------------------------------------------------------
echo CUDA must be True and transformers must be ^< 5 for GigaAM.
echo ============================================================
pause
