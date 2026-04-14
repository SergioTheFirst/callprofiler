# Bugs and Ideas

## Active bugs
- llama-server CUDA backend not loading despite DLLs present
  Next step: dir C:\llama\ggml-cuda* and dir C:\llama\cu*.dll

## Ideas (not yet in roadmap)
- Add call duration to Telegram notification
- Weekly digest every Monday morning
- Contact risk trend chart

## Technical debt
- No tests for normalizer.py, whisper_runner.py, pyannote_runner.py (mock GPU needed)
- configs/base.yaml has placeholder hf_token — replace before production
