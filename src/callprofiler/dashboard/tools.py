# -*- coding: utf-8 -*-
"""
Dashboard tools — admin actions available from the web interface.
Uses Repository for write access, imports modules on demand.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_IMPORT_ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".amr", ".aac", ".flac"}
_IMPORT_MAX_BYTES = 512 * 1024 * 1024
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def save_incoming_audio(db_path: str, user_id: str, filename: str, data: bytes) -> dict[str, Any]:
    """Сохранить перетащенный аудиофайл в incoming_dir юзера (M5, security-sensitive).

    Watcher штатно подхватит файл дальше — ничего в пайплайне не меняется.
    Path traversal режется через Path(filename).name; расширение — whitelist;
    запись атомарна (.part -> os.replace), недописанный файл watcher не увидит.
    """
    import sqlite3

    if not data:
        return {"error": "empty file"}
    if len(data) > _IMPORT_MAX_BYTES:
        return {"error": "file too large"}

    name = Path(filename).name
    if not name:
        return {"error": "invalid filename"}
    if Path(name).stem.upper() in _WINDOWS_RESERVED_NAMES:
        return {"error": "reserved filename"}
    if Path(name).suffix.lower() not in _IMPORT_ALLOWED_EXT:
        return {"error": "unsupported type"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT incoming_dir FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["incoming_dir"]:
        return {"error": "unknown user or incoming_dir not configured"}

    incoming = Path(row["incoming_dir"])
    incoming.mkdir(parents=True, exist_ok=True)

    dst = incoming / name
    stem, suffix = dst.stem, dst.suffix
    i = 1
    while dst.exists():
        dst = incoming / f"{stem}-{i}{suffix}"
        i += 1

    tmp = dst.with_suffix(dst.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dst)

    return {"saved": dst.name, "bytes": len(data)}


class DashboardTools:
    """Thin wrapper for admin actions triggered from the web UI."""

    def __init__(self, config, user_id: str):
        self.config = config
        self.user_id = user_id
        self.db_path = Path(config.data_dir) / "db" / "callprofiler.db"
        self._history: list[dict[str, Any]] = []

    def get_status(self) -> dict[str, Any]:
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        status = {}
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM calls WHERE user_id = ? GROUP BY status",
                (self.user_id,),
            ).fetchall()
            status["by_status"] = {r["status"]: r["cnt"] for r in rows}
            # pending = все НЕ терминальные: new/normalizing/diarizing/transcribing/analyzing/delivering
            pending = conn.execute(
                "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ? AND status NOT IN ('done','error','transcribed')",
                (self.user_id,),
            ).fetchone()["cnt"]
            errors = conn.execute(
                "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ? AND status = 'error'",
                (self.user_id,),
            ).fetchone()["cnt"]
            processed = conn.execute(
                "SELECT COUNT(*) AS cnt FROM calls WHERE user_id = ? AND status = 'done'",
                (self.user_id,),
            ).fetchone()["cnt"]
            status["pending"] = pending
            status["error"] = errors
            status["processed"] = processed
            name_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM contacts WHERE user_id = ? AND (display_name IS NULL OR display_name = '') AND (name_confirmed = 0 OR name_confirmed IS NULL)",
                (self.user_id,),
            ).fetchone()["cnt"]
            status["contacts_without_name"] = name_count
        finally:
            conn.close()
        return status

    async def run_reprocess(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._reprocess_sync)

    def _reprocess_sync(self) -> dict[str, Any]:
        try:
            from callprofiler.db.repository import Repository
            from callprofiler.pipeline.orchestrator import Orchestrator

            cfg = self.config  # already a loaded Config object — do NOT re-load from a path
            repo = Repository(str(self.db_path))
            orchestrator = Orchestrator(cfg, repo)

            errors = repo.get_error_calls(cfg.pipeline.max_retries)
            if not errors:
                repo.close()
                return {"status": "ok", "message": "No errored calls to reprocess", "count": 0}

            count = len(errors)
            orchestrator.retry_errors()
            repo.close()
            self._log(f"reprocess: {count} calls retried")
            return {"status": "ok", "message": f"Retrying {count} calls", "count": count}
        except Exception as e:
            log.error("reprocess failed: %s", e)
            return {"status": "error", "message": str(e), "count": 0}

    async def run_rebuild_summaries(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._rebuild_sync)

    def _rebuild_sync(self) -> dict[str, Any]:
        try:
            from callprofiler.db.repository import Repository
            from callprofiler.aggregate.summary_builder import SummaryBuilder

            repo = Repository(str(self.db_path))
            builder = SummaryBuilder(repo)
            contacts = repo.get_all_contacts_for_user(self.user_id)
            for c in contacts:
                try:
                    builder.rebuild_contact(self.user_id, c["contact_id"])
                except Exception as e:
                    log.warning("Failed summary for contact %s: %s", c.get("contact_id"), e)
            repo.close()
            self._log(f"rebuild-summaries: {len(contacts)} contacts")
            return {"status": "ok", "message": f"Rebuilt {len(contacts)} contact summaries", "count": len(contacts)}
        except Exception as e:
            log.error("rebuild-summaries failed: %s", e)
            return {"status": "error", "message": str(e), "count": 0}

    async def run_extract_names(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_names_sync)

    def _extract_names_sync(self) -> dict[str, Any]:
        try:
            from callprofiler.bulk.name_extractor import NameExtractor
            from callprofiler.db.repository import Repository

            repo = Repository(str(self.db_path))
            extractor = NameExtractor(repo)
            found = extractor.extract_for_user(self.user_id)
            repo.close()
            self._log(f"extract-names: {found} names found")
            return {"status": "ok", "message": f"Found {found} names", "count": found}
        except Exception as e:
            log.error("extract-names failed: %s", e)
            return {"status": "error", "message": str(e), "count": 0}

    async def run_rebuild_cards(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._rebuild_cards_sync)

    def _rebuild_cards_sync(self) -> dict[str, Any]:
        try:
            from callprofiler.db.repository import Repository
            from callprofiler.aggregate.summary_builder import SummaryBuilder
            from callprofiler.deliver.card_generator import CardGenerator

            repo = Repository(str(self.db_path))
            builder = SummaryBuilder(repo)
            contacts = repo.get_all_contacts_for_user(self.user_id)
            for c in contacts:
                try:
                    builder.rebuild_contact(self.user_id, c["contact_id"])
                except Exception as e:
                    log.warning("Failed summary for contact %s: %s", c.get("contact_id"), e)

            generator = CardGenerator(repo, self.config)
            generator.write_all_cards(self.user_id)
            repo.close()
            self._log(f"rebuild-cards: {len(contacts)} contacts")
            return {"status": "ok", "message": f"Rebuilt cards for {len(contacts)} contacts", "count": len(contacts)}
        except Exception as e:
            log.error("rebuild-cards failed: %s", e)
            return {"status": "error", "message": str(e), "count": 0}

    async def run_age_recompute(self, contact_id: int) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._age_recompute_sync, contact_id)

    def _age_recompute_sync(self, contact_id: int) -> dict[str, Any]:
        try:
            from callprofiler.db.repository import Repository
            from callprofiler.insight.age_estimate import run_age_estimate
            from callprofiler.insight.age_style.estimate_style import run_style_estimate
            from callprofiler.dashboard.db_reader import DashboardDBReader

            # ponytail: full-population recompute, not just contact_id — z-scores are
            # relative to the user's whole contact population, so scoring one contact
            # requires the same population pass anyway (feature_store.standardize).
            repo = Repository(str(self.db_path))
            conn = repo._get_conn()

            # Ф6.1: маркер-пасс (этот контакт) + стиль (вся популяция)
            owner_birth_year = getattr(self.config, "owner_birth_year", 0) or 0
            mstats = run_age_estimate(conn, self.user_id, contact_id=contact_id,
                                      owner_birth_year=owner_birth_year)
            stats = run_style_estimate(conn, self.user_id)

            # C3: hint_diarization — проверить есть ли OTHER-реплики для контакта
            has_other_lines = conn.execute(
                "SELECT 1 FROM transcripts t JOIN calls c ON c.call_id = t.call_id "
                "WHERE c.user_id = ? AND c.contact_id = ? AND t.speaker = 'OTHER' LIMIT 1",
                (self.user_id, contact_id)
            ).fetchone()
            hint_diarization = None
            if not has_other_lines:
                # Если есть звонки но нет OTHER-реплик → диаризация не сработала
                has_calls = conn.execute(
                    "SELECT 1 FROM calls WHERE user_id = ? AND contact_id = ? LIMIT 1",
                    (self.user_id, contact_id)
                ).fetchone()
                if has_calls:
                    hint_diarization = ("реплики контакта не размечены (UNKNOWN) — "
                                       "стилометрия невозможна, только маркеры/LLM")

            repo.close()

            reader = DashboardDBReader(self.config.data_dir)
            dossier = reader.get_person_dossier(contact_id, self.user_id)
            self._log(f"age-recompute: markers={mstats.get('estimated', 0)}, "
                     f"styles={stats.get('estimated', 0)}")

            result = {"status": "ok", "stats": stats, "marker_stats": mstats}
            if dossier:
                result["age"] = dossier.get("age")
                result["age_style"] = dossier.get("age_style")
                result["age_fused"] = dossier.get("age_fused")

            # Ф6.4: диагностика owner_birth_year
            if owner_birth_year == 0:
                result["hint"] = "owner_birth_year не задан в base.yaml — реляционные якоря выключены"

            # C3: добавить hint_diarization если есть
            if hint_diarization:
                result["hint_diarization"] = hint_diarization

            return result
        except Exception as e:
            log.error("age-recompute failed: %s", e)
            return {"status": "error", "message": str(e)}

    async def run_import_audio(self, filename: str, data: bytes) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._import_audio_sync, filename, data)

    def _import_audio_sync(self, filename: str, data: bytes) -> dict[str, Any]:
        try:
            result = save_incoming_audio(str(self.db_path), self.user_id, filename, data)
            if "error" not in result:
                self._log(f"import-audio: {result['saved']} ({result['bytes']} bytes)")
            return result
        except Exception as e:
            log.error("import-audio failed: %s", e)
            return {"error": str(e)}

    def _log(self, msg: str):
        self._history.insert(0, {
            "ts": time.strftime("%H:%M:%S"),
            "message": msg,
        })
        if len(self._history) > 50:
            self._history = self._history[:50]

    def get_history(self) -> list[dict[str, Any]]:
        return self._history[:20]
