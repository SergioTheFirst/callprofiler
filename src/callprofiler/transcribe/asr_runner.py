# -*- coding: utf-8 -*-
"""
asr_runner.py — Protocol (interface) for ASR backends.

Any ASR implementation (WhisperRunner, GigaAMRunner, etc.) satisfies
this interface to be interchangeable in the pipeline orchestrator.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from callprofiler.models import Segment


@runtime_checkable
class ASRRunner(Protocol):
    """Interface for speech-to-text backends used by the pipeline.

    Implementations: WhisperRunner, GigaAMRunner.
    Selection via config.models.asr_backend ("whisper" | "gigaam").
    """

    def load(self) -> None:
        """Load model/connect to backend. Idempotent."""
        ...

    def unload(self) -> None:
        """Free GPU memory / close connection. Idempotent."""
        ...

    def transcribe(self, wav_path: str) -> list["Segment"]:
        """Transcribe WAV file. Returns Segments with speaker=UNKNOWN.

        Raises:
            RuntimeError — if transcription fails after all retries.
        """
        ...
