"""Schema-accurate синтетическая БД для офлайн-разработки и валидации."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np

from callprofiler.insight.repository import apply_insight_schema
from callprofiler.insight.synth.archetypes import DEFAULT_TEMPLATES
from callprofiler.insight.synth.noise import inject_asr_noise

# .../insight/synth/corpus.py -> parents[1]=insight, .parent=callprofiler
_BASE_SCHEMA = Path(__file__).resolve().parents[1].parent / "db" / "schema.sql"


class SyntheticCorpus:
    def __init__(self, seed: int = 0):
        self.seed = seed
        self.ground_truth = {}

    def build(self, path: str = ":memory:", n_per: int = 20,
              user_id: str = "me", templates=DEFAULT_TEMPLATES,
              end_date=datetime(2026, 6, 1), noise_rate: float = 0.0) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.executescript(_BASE_SCHEMA.read_text(encoding="utf-8"))
        apply_insight_schema(conn)
        conn.execute(
            "INSERT INTO users(user_id, display_name, incoming_dir, sync_dir, ref_audio) "
            "VALUES (?,?,?,?,?)",
            (user_id, "Synthetic", "in", "sync", "ref.wav"),
        )
        rng = np.random.default_rng(self.seed)
        self.ground_truth = {}
        for tmpl in templates:
            for _ in range(n_per):
                cur = conn.execute(
                    "INSERT INTO contacts(user_id, display_name) VALUES (?,?)",
                    (user_id, f"{tmpl.name}_{int(rng.integers(1_000_000))}"),
                )
                contact_id = cur.lastrowid
                self.ground_truth[contact_id] = tmpl.name
                for i, call in enumerate(tmpl.sample_calls(rng, end_date)):
                    cur = conn.execute(
                        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
                        "source_filename, source_md5, duration_sec, status) "
                        "VALUES (?,?,?,?,?,?,?, 'done')",
                        (user_id, contact_id, call["direction"], call["call_datetime"],
                         f"c{contact_id}_{i}.mp3", f"md5-{contact_id}-{i}",
                         call["duration_sec"]),
                    )
                    call_id = cur.lastrowid

                    # Генерируем сегменты транскрипта со специфичными регистрами
                    segments = tmpl.sample_segments(rng)
                    start_ms = 0
                    for seg in segments:
                        text = seg["text"]
                        # Применяем шум к речи OTHER
                        if noise_rate > 0.0 and seg["speaker"] == "OTHER":
                            text = inject_asr_noise(text, noise_rate, seed=self.seed + call_id)

                        end_ms = start_ms + 5000  # ~5 сек на сегмент
                        conn.execute(
                            "INSERT INTO transcripts(call_id, speaker, text, start_ms, end_ms) "
                            "VALUES (?,?,?,?,?)",
                            (call_id, seg["speaker"], text, start_ms, end_ms)
                        )
                        start_ms = end_ms

                    # Генерируем анализ (Phase 3)
                    analysis = tmpl.sample_analysis(rng)
                    conn.execute(
                        "INSERT INTO analyses(call_id, risk_score, profanity_density, "
                        "call_type, key_topics) "
                        "VALUES (?,?,?,?,?)",
                        (call_id, analysis["risk_score"], analysis["profanity_density"],
                         analysis["call_type"], json.dumps(analysis["key_topics"])),
                    )

        conn.commit()
        return conn
