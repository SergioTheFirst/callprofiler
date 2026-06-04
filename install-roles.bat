@echo off
cd /d "C:\pro\callprofiler"
echo ============================================================
echo   Install ROLES deps ([me]/[s2] diarization) - Python 3.12
echo ============================================================
echo Needs: pyannote.audio + soundfile + librosa + HF_TOKEN + ref_audio.
echo.
python -m pip install pyannote.audio soundfile librosa
echo.
echo pip above usually REPLACES CUDA torch with a CPU build -> re-pinning:
python -m pip install --force-reinstall torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
echo.
python -c "import torch; print('CUDA', torch.cuda.is_available()); import pyannote.audio, soundfile, librosa; print('roles deps OK')"
echo.
echo ============================================================
echo   STILL REQUIRED for roles:
echo   1) Get an HF token: https://huggingface.co/settings/tokens
echo   2) Accept access (logged in) for ALL three gated models:
echo        https://hf.co/pyannote/segmentation-3.0
echo        https://hf.co/pyannote/speaker-diarization-3.1
echo        https://hf.co/pyannote/embedding
echo   3) Persist token, then OPEN A NEW terminal:
echo        setx HF_TOKEN "hf_xxxxxxxxxxxxxxxxx"
echo   4) ref_audio (owner voice) is already set: C:\pro\mbot\ref\manager.wav
echo ============================================================
pause
