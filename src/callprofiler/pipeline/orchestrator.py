# -*- coding: utf-8 -*-
"""
orchestrator.py — главный оркестратор pipeline обработки звонков.

Собирает все модули вместе и управляет сквозным процессом:
  Ingest → Normalize → Transcribe → Diarize → Analyze → Deliver

GPU-дисциплина (CONSTITUTION.md Статья 9.2-9.3):
  - Whisper (~3GB) + pyannote (~1.5GB) помещаются вместе → загружаем оба
  - Перед LLM (~10GB) обязательно выгрузить Whisper+pyannote
  - Batch-режим: загрузить один раз → обработать все pending → выгрузить
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from callprofiler.analyze.llm_client import OllamaClient
from callprofiler.analyze.prompt_builder import PromptBuilder
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.audio.normalizer import normalize, get_duration_sec
from callprofiler.deliver.card_generator import CardGenerator
from callprofiler.deliver.telegram_bot import TelegramNotifier
from callprofiler.diarize.pyannote_runner import PyannoteRunner
from callprofiler.diarize.role_assigner import assign_speakers
from callprofiler.models import Segment
from callprofiler.transcribe.whisper_runner import WhisperRunner

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)


def _format_transcript(segments: list[Segment]) -> str:
    """Форматировать сегменты в текст стенограммы для LLM.

    Формат: [MM:SS] SPEAKER: текст
    """
    lines = []
    for seg in segments:
        total_sec = seg.start_ms // 1000
        minutes = total_sec // 60
        seconds = total_sec % 60
        lines.append(f"[{minutes:02d}:{seconds:02d}] {seg.speaker}: {seg.text}")
    return "\n".join(lines)


class Orchestrator:
    """Главный оркестратор pipeline обработки звонков.

    Использование:
        orch = Orchestrator(config, repo)
        orch.process_call(call_id)        # один звонок
        orch.process_pending()             # все новые
        orch.process_batch([1, 2, 3])      # batch с GPU-оптимизацией
    """

    def __init__(
        self,
        config: Config,
        repo: Repository,
        telegram: TelegramNotifier | None = None,
    ) -> None:
        """Инициализировать оркестратор.

        Параметры:
            config    — конфигурация проекта
            repo      — Repository для доступа к данным
            telegram  — TelegramNotifier (опционально, для отправки саммари)
        """
        self.config = config
        self.repo = repo

        # Компоненты ASR/diarize (лениво загружаются)
        self.whisper_runner = WhisperRunner(config)
        self.pyannote_runner = PyannoteRunner(config)

        # Компоненты анализа
        self.prompt_builder = PromptBuilder(
            str(Path(config.data_dir).parent / "configs" / "prompts")
            if config.data_dir
            else "configs/prompts"
        )
        self.card_generator = CardGenerator(repo)
        self.telegram = telegram

        logger.info("Orchestrator инициализирован")

    def process_call(self, call_id: int) -> bool:
        """Обработать один звонок от начала до конца.

        Параметры:
            call_id  — идентификатор звонка в БД

        Возвращает:
            True если обработка успешна, False при ошибке
        """
        try:
            call = self.repo._get_conn().execute(
                "SELECT * FROM calls WHERE call_id=?", (call_id,),
            ).fetchone()
            if not call:
                logger.error("Звонок %d не найден", call_id)
                return False

            call = dict(call)
            user_id = call["user_id"]
            contact_id = call.get("contact_id")
            audio_path = call.get("audio_path", "")

            # ── Шаг 1: Normalize ─────────────────────────────
            self.repo.update_call_status(call_id, "normalizing")
            norm_dir = Path(self.config.data_dir) / "users" / user_id / "audio" / "normalized"
            norm_dir.mkdir(parents=True, exist_ok=True)
            norm_path = str(norm_dir / f"{call_id}.wav")

            normalize(audio_path, norm_path)
            duration_sec = get_duration_sec(norm_path)
            self.repo.update_call_paths(call_id, norm_path, duration_sec)
            logger.info("Нормализация завершена: call_id=%d, duration=%ds", call_id, duration_sec)

            # ── Шаг 2: Transcribe ────────────────────────────
            self.repo.update_call_status(call_id, "transcribing")
            self.whisper_runner.load()
            segments = self.whisper_runner.transcribe(norm_path)
            self.whisper_runner.unload()
            logger.info("Транскрибирование: call_id=%d, %d сегментов", call_id, len(segments))

            # ── Шаг 3: Diarize ───────────────────────────────
            self.repo.update_call_status(call_id, "diarizing")
            user = self.repo.get_user(user_id)
            ref_audio = user.get("ref_audio", "") if user else ""

            if ref_audio and Path(ref_audio).exists():
                self.pyannote_runner.load(ref_audio)
                diarization = self.pyannote_runner.diarize(norm_path)
                segments = assign_speakers(segments, diarization)
                self.pyannote_runner.unload()
                logger.info("Диаризация: call_id=%d, %d интервалов", call_id, len(diarization))
            else:
                logger.warning("Нет ref_audio для user_id=%s, пропуск диаризации", user_id)

            # Сохранить транскрипт
            self.repo.save_transcripts(call_id, segments)

            # ── Шаг 4: Analyze ───────────────────────────────
            self.repo.update_call_status(call_id, "analyzing")
            self._analyze_call(call_id, call, segments)

            # ── Шаг 5: Deliver ───────────────────────────────
            self.repo.update_call_status(call_id, "delivering")
            self._deliver_call(call_id, user_id, contact_id)

            # ── Готово ────────────────────────────────────────
            self.repo.update_call_status(call_id, "done")
            logger.info("✓ Звонок %d обработан полностью", call_id)
            return True

        except Exception as exc:
            logger.error("Ошибка при обработке call_id=%d: %s", call_id, exc)
            self.repo.update_call_status(call_id, "error", str(exc))
            return False

    def process_batch(self, call_ids: list[int]) -> None:
        """Batch-обработка: GPU-оптимизированный режим.

        Загружает Whisper+pyannote один раз для всех файлов,
        затем выгружает и запускает LLM анализ.

        Параметры:
            call_ids  — список call_id для обработки
        """
        if not call_ids:
            return

        logger.info("Batch-обработка: %d звонков", len(call_ids))

        # Собрать данные о звонках
        calls_data = []
        for call_id in call_ids:
            call = self.repo._get_conn().execute(
                "SELECT * FROM calls WHERE call_id=?", (call_id,),
            ).fetchone()
            if call:
                calls_data.append(dict(call))

        if not calls_data:
            return

        # ── Фаза 1: Normalize все ────────────────────────
        for call in calls_data:
            try:
                self.repo.update_call_status(call["call_id"], "normalizing")
                user_id = call["user_id"]
                norm_dir = Path(self.config.data_dir) / "users" / user_id / "audio" / "normalized"
                norm_dir.mkdir(parents=True, exist_ok=True)
                norm_path = str(norm_dir / f"{call['call_id']}.wav")

                normalize(call["audio_path"], norm_path)
                duration_sec = get_duration_sec(norm_path)
                self.repo.update_call_paths(call["call_id"], norm_path, duration_sec)
                call["_norm_path"] = norm_path
            except Exception as exc:
                logger.error("Ошибка нормализации call_id=%d: %s", call["call_id"], exc)
                self.repo.update_call_status(call["call_id"], "error", str(exc))
                call["_skip"] = True

        # Отфильтровать сбойные
        calls_data = [c for c in calls_data if not c.get("_skip")]

        # ── Фаза 2: Transcribe + Diarize (Whisper + pyannote в GPU) ──
        self.whisper_runner.load()

        # Группировка по user_id для ref_audio
        users_cache = {}
        for call in calls_data:
            user_id = call["user_id"]
            if user_id not in users_cache:
                users_cache[user_id] = self.repo.get_user(user_id)

        segments_map = {}
        for call in calls_data:
            call_id = call["call_id"]
            try:
                self.repo.update_call_status(call_id, "transcribing")
                segments = self.whisper_runner.transcribe(call["_norm_path"])
                segments_map[call_id] = segments
                logger.info("Transcribe: call_id=%d, %d сегментов", call_id, len(segments))
            except Exception as exc:
                logger.error("Ошибка транскрибирования call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))

        self.whisper_runner.unload()

        # Diarize
        for call in calls_data:
            call_id = call["call_id"]
            if call_id not in segments_map:
                continue

            try:
                self.repo.update_call_status(call_id, "diarizing")
                user_id = call["user_id"]
                user = users_cache.get(user_id)
                ref_audio = user.get("ref_audio", "") if user else ""

                if ref_audio and Path(ref_audio).exists():
                    self.pyannote_runner.load(ref_audio)
                    diarization = self.pyannote_runner.diarize(call["_norm_path"])
                    segments_map[call_id] = assign_speakers(
                        segments_map[call_id], diarization
                    )
                    self.pyannote_runner.unload()

                self.repo.save_transcripts(call_id, segments_map[call_id])
            except Exception as exc:
                logger.error("Ошибка диаризации call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))

        # ── Фаза 3: Analyze (LLM, после выгрузки GPU моделей) ────
        for call in calls_data:
            call_id = call["call_id"]
            if call_id not in segments_map:
                continue

            try:
                self.repo.update_call_status(call_id, "analyzing")
                self._analyze_call(call_id, call, segments_map[call_id])
            except Exception as exc:
                logger.error("Ошибка анализа call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))

        # ── Фаза 4: Deliver ──────────────────────────────
        for call in calls_data:
            call_id = call["call_id"]
            if call_id not in segments_map:
                continue

            try:
                self.repo.update_call_status(call_id, "delivering")
                self._deliver_call(call_id, call["user_id"], call.get("contact_id"))
                self.repo.update_call_status(call_id, "done")
                logger.info("✓ Звонок %d обработан (batch)", call_id)
            except Exception as exc:
                logger.error("Ошибка доставки call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))

        logger.info("Batch завершён: %d звонков", len(call_ids))

    def process_pending(self) -> None:
        """Обработать все звонки со статусом 'new'."""
        pending = self.repo.get_pending_calls()
        if not pending:
            logger.debug("Нет pending звонков")
            return

        call_ids = [c["call_id"] for c in pending]
        logger.info("Найдено %d pending звонков", len(call_ids))
        self.process_batch(call_ids)

    def retry_errors(self) -> None:
        """Повторить звонки со статусом 'error' и retry_count < max_retries."""
        max_retries = self.config.pipeline.max_retries
        errors = self.repo.get_error_calls(max_retries)
        if not errors:
            logger.debug("Нет звонков для повтора")
            return

        call_ids = [c["call_id"] for c in errors]
        logger.info("Повтор %d звонков с ошибками", len(call_ids))
        self.process_batch(call_ids)

    # ── Внутренние методы ─────────────────────────────────────────────

    def _analyze_call(
        self,
        call_id: int,
        call: dict,
        segments: list[Segment],
    ) -> None:
        """Запустить LLM-анализ для звонка.

        Параметры:
            call_id   — идентификатор звонка
            call      — данные звонка из БД
            segments  — сегменты транскрипции
        """
        user_id = call["user_id"]
        contact_id = call.get("contact_id")

        # Форматировать транскрипт
        transcript_text = _format_transcript(segments)

        # Получить контекст (предыдущие анализы)
        previous_summaries = []
        if contact_id:
            prev_analyses = self.repo.get_recent_analyses(user_id, contact_id, limit=5)
            previous_summaries = [a.get("summary", "") for a in prev_analyses if a.get("summary")]

        # Получить метаданные для промпта
        contact = self.repo.get_contact(contact_id) if contact_id else None
        metadata = {
            "contact_name": contact.get("display_name") if contact else None,
            "phone": contact.get("phone_e164") if contact else None,
            "call_datetime": call.get("call_datetime"),
            "direction": call.get("direction", "UNKNOWN"),
        }

        # Построить промпт и отправить в LLM
        prompt = self.prompt_builder.build(
            transcript_text, metadata, previous_summaries
        )

        try:
            ollama = OllamaClient(
                base_url=self.config.models.ollama_url,
                model=self.config.models.llm_model,
            )
            raw_response = ollama.generate(prompt)
        except (ConnectionError, RuntimeError) as exc:
            logger.error("LLM недоступен для call_id=%d: %s", call_id, exc)
            raw_response = ""

        # Распарсить ответ
        analysis = parse_llm_response(
            raw_response,
            model=self.config.models.llm_model,
            prompt_version="v001",
        )

        # Сохранить в БД
        self.repo.save_analysis(call_id, analysis)

        # Сохранить обещания
        if analysis.promises and contact_id:
            self.repo.save_promises(user_id, contact_id, call_id, analysis.promises)

        # Обновить Knowledge Graph (только v2 analyses, non-fatal)
        try:
            from callprofiler.graph.builder import GraphBuilder
            from callprofiler.graph.repository import apply_graph_schema
            conn = self.repo._get_conn()
            apply_graph_schema(conn)
            GraphBuilder(conn).update_from_call(call_id)
        except Exception as _graph_exc:
            logger.warning("graph update failed for call_id=%d: %s", call_id, _graph_exc)

        logger.info(
            "Анализ: call_id=%d, priority=%d, risk=%d",
            call_id, analysis.priority, analysis.risk_score,
        )

    def _deliver_call(
        self,
        call_id: int,
        user_id: str,
        contact_id: int | None,
    ) -> None:
        """Доставить результаты: карточка + Telegram.

        Параметры:
            call_id     — идентификатор звонка
            user_id     — идентификатор пользователя
            contact_id  — идентификатор контакта (может быть None)
        """
        user = self.repo.get_user(user_id)
        if not user:
            return

        # Обновить caller card
        if contact_id:
            sync_dir = user.get("sync_dir", "")
            if sync_dir:
                try:
                    self.card_generator.write_card(user_id, contact_id, sync_dir)
                except Exception as exc:
                    logger.error("Ошибка записи карточки: %s", exc)

        # Отправить саммари в Telegram
        if self.telegram:
            try:
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.send_summary(user_id, call_id)
                )
            except RuntimeError:
                # Нет event loop — создать новый
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        self.telegram.send_summary(user_id, call_id)
                    )
                finally:
                    loop.close()
            except Exception as exc:
                logger.error("Ошибка отправки Telegram: %s", exc)
