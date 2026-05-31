# -*- coding: utf-8 -*-
"""
gigaam_runner.py — GigaAM v3 RNN-T ASR backend.

HTTP client for the GigaAM transcription server.
URL configured via configs/base.yaml → models.gigaam_url.

Activation:
  In configs/base.yaml set:
    models:
      asr_backend: gigaam
      gigaam_url: http://<host>:<port>

Interface matches ASRRunner protocol (same as WhisperRunner).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.models import Segment

logger = logging.getLogger(__name__)


class GigaAMRunner:
    """GigaAM v3 RNN-T client.

    Satisfies the ASRRunner protocol (load / unload / transcribe).
    GPU memory management is server-side — load/unload are no-ops here.
    """

    def __init__(self, config: "Config") -> None:
        self.config = config
        self._url: str | None = None

    def load(self) -> None:
        """Validate configuration and record endpoint URL."""
        url = getattr(self.config.models, "gigaam_url", "")
        if not url:
            raise RuntimeError(
                "GigaAM URL not configured. "
                "Set models.gigaam_url in configs/base.yaml."
            )
        self._url = url.rstrip("/")
        logger.info("GigaAMRunner ready: %s", self._url)

    def unload(self) -> None:
        """Release endpoint reference (server manages GPU)."""
        self._url = None
        logger.info("GigaAMRunner unloaded")

    def transcribe(self, wav_path: str) -> list["Segment"]:
        """Transcribe WAV via GigaAM HTTP endpoint.

        Protocol (to be implemented when API spec is available):
          POST {gigaam_url}/transcribe
          Content-Type: audio/wav  (raw bytes)
          Response: JSON list of {start_ms, end_ms, text}

        Raises:
            RuntimeError — if URL not set or request fails.
        """
        if not self._url:
            raise RuntimeError("GigaAMRunner not loaded. Call load() first.")

        import requests
        from callprofiler.models import Segment

        wav = Path(wav_path)
        if not wav.exists():
            raise RuntimeError(f"Audio file not found: {wav_path}")

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with open(wav_path, "rb") as f:
                    resp = requests.post(
                        f"{self._url}/transcribe",
                        data=f.read(),
                        headers={"Content-Type": "audio/wav"},
                        timeout=300,
                    )
                resp.raise_for_status()
                raw = resp.json()

                segments: list[Segment] = []
                for item in raw:
                    text = str(item.get("text", "")).strip()
                    if not text:
                        continue
                    segments.append(
                        Segment(
                            start_ms=int(item.get("start_ms", 0)),
                            end_ms=int(item.get("end_ms", 0)),
                            text=text,
                            speaker="UNKNOWN",
                        )
                    )
                logger.info(
                    "GigaAM transcribe: %d segments from %s", len(segments), wav_path
                )
                return segments

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if attempt < 2:
                    delay = 2 ** (attempt + 1)
                    logger.warning(
                        "GigaAM недоступен (попытка %d/3), повтор через %ds: %s",
                        attempt + 1, delay, exc,
                    )
                    time.sleep(delay)
            except Exception as exc:
                raise RuntimeError(
                    f"GigaAM transcribe failed for {wav_path}: {exc}"
                ) from exc

        raise RuntimeError(
            f"GigaAM недоступен после 3 попыток для {wav_path}: {last_exc}"
        ) from last_exc
