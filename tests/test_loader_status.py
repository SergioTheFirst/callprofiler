# -*- coding: utf-8 -*-
"""
test_loader_status.py — тесты для Stage-1 terminal status после bulk_load.
"""

import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from callprofiler.bulk.loader import bulk_load
from callprofiler.db.repository import Repository


class TestBulkLoaderStatus:
    """Тесты статуса и стадии после загрузки транскриптов."""

    def test_bulk_load_sets_transcribed_status(self):
        """Загруженный звонок имеет status='transcribed' и pipeline_stage=2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_dir = Path(tmpdir) / "txt"
            txt_dir.mkdir()
            db_path = Path(tmpdir) / "test.db"

            # Инициализировать БД и добавить пользователя
            repo = Repository(str(db_path))
            repo.init_db()
            repo.add_user("me", "Test User", None, str(txt_dir), "", "")
            repo.close()

            # Создать тестовый .txt файл
            txt_file = txt_dir / "test_call.txt"
            txt_file.write_text("[me]: Привет\n[s2]: Привет!")

            # bulk_load
            stats = bulk_load(str(txt_dir), "me", str(db_path))
            assert stats['loaded'] == 1

            # Проверить что звонок имеет правильный статус и stage
            repo = Repository(str(db_path))
            conn = repo._get_conn()
            rows = conn.execute("SELECT * FROM calls WHERE user_id=?", ("me",)).fetchall()
            assert len(rows) >= 1
            call = dict(rows[0])
            assert call['status'] == 'transcribed', f"Expected status='transcribed', got {call['status']}"
            assert call['pipeline_stage'] == 2, f"Expected pipeline_stage=2, got {call['pipeline_stage']}"
            repo.close()

    def test_bulk_load_saves_transcripts_before_status(self):
        """Транскрипты сохраняются ДО установки терминального статуса."""
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_dir = Path(tmpdir) / "txt"
            txt_dir.mkdir()
            db_path = Path(tmpdir) / "test.db"

            repo = Repository(str(db_path))
            repo.init_db()
            repo.add_user("me", "Test User", None, str(txt_dir), "", "")
            repo.close()

            txt_file = txt_dir / "test_call.txt"
            txt_file.write_text("[me]: Привет\n[s2]: Привет!")

            stats = bulk_load(str(txt_dir), "me", str(db_path))
            assert stats['loaded'] == 1

            # Проверить что транскрипты сохранены
            repo = Repository(str(db_path))
            conn = repo._get_conn()
            rows = conn.execute("SELECT * FROM calls WHERE user_id=?", ("me",)).fetchall()
            assert len(rows) >= 1
            call_id = dict(rows[0])['call_id']

            transcripts = conn.execute("SELECT COUNT(*) FROM transcripts WHERE call_id=?", (call_id,)).fetchone()[0]
            assert transcripts > 0, "Transcripts not saved"
            repo.close()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
