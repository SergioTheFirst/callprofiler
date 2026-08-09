# -*- coding: utf-8 -*-
"""test_bulk_enrich_readiness.py — T-13: bulk_enrich по-прежнему деградирует
корректно (zero stats == CLI exit-code-2 эквивалент) когда LLM не готов,
теперь через явный LLMClient.ensure_ready() вместо сети в конструкторе."""
from __future__ import annotations

from unittest.mock import patch


def test_bulk_enrich_returns_zero_stats_when_llm_not_ready(tmp_path):
    from callprofiler.bulk.enricher import bulk_enrich
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository

    db_path = str(tmp_path / "t.db")
    repo = Repository(db_path)
    repo.init_db()
    repo.add_user(
        user_id="me", display_name="T", telegram_chat_id="0",
        incoming_dir=str(tmp_path / "in"), sync_dir=str(tmp_path / "sync"),
        ref_audio=str(tmp_path / "r.wav"),
    )
    repo.close()

    # Dev-машина без ffmpeg (dev/run split, CLAUDE.md) — минимальный Config
    # вместо реальной load_config("configs/base.yaml") с ffmpeg-валидацией.
    with patch("callprofiler.bulk.enricher.load_config", return_value=Config()), \
         patch("callprofiler.bulk.enricher.LLMClient") as MockLLMClient:
        MockLLMClient.return_value.ensure_ready.side_effect = ConnectionError("down")
        stats = bulk_enrich("me", db_path, config_path="configs/base.yaml")

    assert stats == {"processed": 0, "failed": 0, "skipped": 0, "total": 0}
