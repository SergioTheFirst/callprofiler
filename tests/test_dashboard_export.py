# -*- coding: utf-8 -*-
"""Real-DB tests for DashboardDBReader.export_book_markdown (Phase 4, Feature 2).

Mirrors the way export_calls is exercised, but against a real on-disk SQLite so
the markdown-assembly logic (prose_full vs chapter concatenation, ordering,
user_id isolation, empty placeholder) is actually verified — not mocked away.
"""
from __future__ import annotations

import sqlite3

import pytest

from callprofiler.biography.schema import apply_biography_schema
from callprofiler.dashboard.db_reader import DashboardDBReader


def _make_db(tmp_path):
    db_file = tmp_path / "bio.db"
    conn = sqlite3.connect(str(db_file))
    apply_biography_schema(conn)
    return db_file, conn


def test_export_prefers_prose_full(tmp_path):
    """A fully-assembled volume (bio_books.prose_full) is the canonical export;
    individual chapters are ignored when prose_full exists."""
    db_file, conn = _make_db(tmp_path)
    conn.execute(
        """INSERT INTO bio_books (user_id, title, prose_full, book_type)
           VALUES (?, ?, ?, 'main')""",
        ("u1", "Моя книга", "# Моя книга\n\nПолный текст тома."),
    )
    conn.execute(
        """INSERT INTO bio_chapters (user_id, chapter_num, title, prose)
           VALUES (?, 1, ?, ?)""",
        ("u1", "Глава первая", "Текст главы который не должен попасть."),
    )
    conn.commit()
    conn.close()

    md = DashboardDBReader(str(db_file)).export_book_markdown("u1")
    assert "Полный текст тома." in md
    assert "не должен попасть" not in md  # chapters skipped when prose_full present


def test_export_assembles_chapters_in_order(tmp_path):
    """With no prose_full, chapters are concatenated by chapter_num ascending,
    wrapped by the book frame (title / prologue / epilogue)."""
    db_file, conn = _make_db(tmp_path)
    conn.execute(
        """INSERT INTO bio_books (user_id, title, prologue, epilogue, book_type)
           VALUES (?, ?, ?, ?, 'main')""",
        ("u1", "Жизнь", "Это пролог.", "Это эпилог."),
    )
    # Inserted out of order on purpose — output must be num 1 then num 2.
    conn.execute(
        """INSERT INTO bio_chapters (user_id, chapter_num, title, prose)
           VALUES (?, 2, ?, ?)""",
        ("u1", "Второй месяц", "Проза второй главы."),
    )
    conn.execute(
        """INSERT INTO bio_chapters (user_id, chapter_num, title, prose)
           VALUES (?, 1, ?, ?)""",
        ("u1", "Первый месяц", "Проза первой главы."),
    )
    conn.commit()
    conn.close()

    md = DashboardDBReader(str(db_file)).export_book_markdown("u1")
    assert "# Жизнь" in md
    assert "Это пролог." in md
    assert "Это эпилог." in md
    assert "## Первый месяц" in md
    assert "## Второй месяц" in md
    # Ordering: chapter 1 prose appears before chapter 2 prose, epilogue last.
    assert md.index("Проза первой главы.") < md.index("Проза второй главы.")
    assert md.index("Проза второй главы.") < md.index("Это эпилог.")


def test_export_placeholder_when_empty(tmp_path):
    """No book and no chapters → a valid, clearly-empty markdown placeholder."""
    db_file, conn = _make_db(tmp_path)
    conn.commit()
    conn.close()

    md = DashboardDBReader(str(db_file)).export_book_markdown("u1")
    assert md.strip()  # never empty string
    assert "не сгенерирована" in md.lower()


def test_export_is_user_scoped(tmp_path):
    """Export for u1 must not leak u2's chapters."""
    db_file, conn = _make_db(tmp_path)
    conn.execute(
        """INSERT INTO bio_chapters (user_id, chapter_num, title, prose)
           VALUES (?, 1, ?, ?)""",
        ("u1", "Гл1", "ПРИНАДЛЕЖИТ_U1"),
    )
    conn.execute(
        """INSERT INTO bio_chapters (user_id, chapter_num, title, prose)
           VALUES (?, 1, ?, ?)""",
        ("u2", "Гл1", "ПРИНАДЛЕЖИТ_U2"),
    )
    conn.commit()
    conn.close()

    md = DashboardDBReader(str(db_file)).export_book_markdown("u1")
    assert "ПРИНАДЛЕЖИТ_U1" in md
    assert "ПРИНАДЛЕЖИТ_U2" not in md


def test_calls_by_stage_maps_all_pipeline_statuses(tmp_path):
    """Регресс степпера: статус 'new' раньше мапился на несуществующий 'pending'
    (всегда 0), а стадии 'diarizing'/'delivering' отсутствовали → дашборд врал.
    Теперь каждый реальный статус конвейера считается отдельной стадией."""
    from callprofiler.db.repository import Repository

    db = tmp_path / "db" / "callprofiler.db"
    db.parent.mkdir(parents=True)
    repo = Repository(str(db))
    repo.init_db()
    repo.add_user(user_id="me", display_name="t", telegram_chat_id="1",
                  incoming_dir="/i", sync_dir="/s", ref_audio="/r")
    stages = ["new", "normalizing", "diarizing", "transcribing",
              "analyzing", "delivering", "done", "error"]
    for st in stages:
        cid = repo.create_call(user_id="me", contact_id=None, direction="IN",
                               call_datetime="2026-01-01 00:00:00",
                               source_filename=st + ".mp3", source_md5=st,
                               audio_path="/a.mp3")
        repo.update_call_status(cid, st)

    by_stage = DashboardDBReader(str(db)).get_calls_by_stage("me")
    for st in stages:
        assert by_stage.get(st) == 1, f"{st} -> {by_stage.get(st)}"
    assert "other" not in by_stage  # все статусы распознаны
