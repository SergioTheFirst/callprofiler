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
import re
from pathlib import Path
from typing import TYPE_CHECKING

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.prompt_builder import PromptBuilder
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.analyze.service import PROMPT_VERSION_ANALYZE
from callprofiler.audio.normalizer import get_duration_sec, normalize
from callprofiler.db.uow import uow_for
from callprofiler.deliver.card_generator import CardGenerator
from callprofiler.deliver.telegram_bot import TelegramNotifier
from callprofiler.diarize.role_assigner import assign_speakers, is_role_fragile
from callprofiler.identity import user_profile_dir
from callprofiler.models import Segment


def _make_asr_runner(config: "Config"):
    """Factory: return ASR runner based on config.models.asr_backend.

    ОБА runner'а импортируются ЛЕНИВО. Раньше `WhisperRunner` тянулся на
    верхнем уровне модуля, а он делает `import torch` — из-за этого весь
    orchestrator (и любой тест/CLI, его импортирующий) требовал ML-стек даже
    при `asr_backend: gigaam`, когда Whisper вообще не используется. Тот же
    класс дефекта, что P-OPS-03 в `__init__.py`: ленивость в одной ветке
    фабрики и eager-импорт в другой — защита, которая не работает.
    """
    backend = getattr(config.models, "asr_backend", "whisper")
    if backend == "gigaam":
        from callprofiler.transcribe.gigaam_runner import GigaAMRunner
        return GigaAMRunner(config)
    from callprofiler.transcribe.whisper_runner import WhisperRunner
    return WhisperRunner(config)

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)


_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_stem(name: str, *, max_len: int = 60) -> str:
    """Очистить имя источника до безопасного для ФС хвоста (без расширения)."""
    stem = Path(name).stem
    stem = _SAFE_STEM_RE.sub("_", stem).strip("._")
    return stem[:max_len] if stem else ""


def norm_wav_path(norm_dir: Path, call_id: int, source_filename: str | None) -> Path:
    """Детерминированный путь normalized .wav: ``{call_id}__{имя_источника}.wav``.

    Имя источника в названии (а не просто ``{call_id}.wav``) — чтобы при крахе
    массового прогона уже нормализованный файл узнавался и НЕ пере-нормализовался
    (orchestrator проверяет существование этого пути). ``call_id`` остаётся
    префиксом для уникальности (разные звонки с одинаковым basename источника не
    коллизируют и не подменяют друг другу аудио) и для парсинга в
    ``watcher.cleanup_normalized`` (``stem.split("__")[0]``). Совместимо со старым
    чистым ``{call_id}.wav``.
    """
    stem = _safe_stem(source_filename or "")
    name = f"{call_id}__{stem}.wav" if stem else f"{call_id}.wav"
    return norm_dir / name


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
        repo.backoff_base_sec = config.pipeline.retry_interval_sec  # T-07: база exp-backoff

        # Компоненты ASR/diarize (лениво загружаются)
        # ASR-runner создаётся ЛЕНИВО, при первом обращении (см. property ниже) —
        # симметрично pyannote. Создание в __init__ означало бы, что сам факт
        # конструирования Orchestrator требует ML-стек: любой тест/CLI/облачный
        # прогон без torch падал бы, не дойдя до реальной работы.
        self._asr_runner = None
        # pyannote создаётся лениво при первой диаризации — Stage-1 его не требует
        self.pyannote_runner = None
        # Диагностика: каждую отдельную причину сбоя диаризации логируем ОДИН раз
        # (batch может быть тысячи звонков — иначе один и тот же warning спамит лог).
        self._diag_warned: set[str] = set()

        # Компоненты анализа (prompts резолвятся от корня проекта, не от data_dir)
        self.prompt_builder = PromptBuilder(config.prompts_dir)
        self.card_generator = CardGenerator(repo)
        self.telegram = telegram

        logger.info("Orchestrator инициализирован")

    @property
    def asr_runner(self):
        """ASR-runner по требованию. Сеттер сохранён — тесты подменяют фейком."""
        if self._asr_runner is None:
            self._asr_runner = _make_asr_runner(self.config)
        return self._asr_runner

    @asr_runner.setter
    def asr_runner(self, runner) -> None:
        self._asr_runner = runner

    def _fail(self, user_id: str, call_id: int, exc: Exception, stage: str) -> None:
        """Централизованная обработка ошибок с классификацией FATAL vs retryable.

        FATAL: ValueError, TypeError, KeyError, AssertionError, FileNotFoundError
          → сообщение f"FATAL[{stage}]: {exc}", не ретрится автоматически.
        Retryable (всё остальное): ConnectionError, TimeoutError, OSError, RuntimeError, Exception
          → сообщение f"{stage}: {exc}", ретрится по exp-backoff.

        Всегда логирует и вызывает update_call_status(user_id, call_id, "error", message).
        """
        FATAL_TYPES = (ValueError, TypeError, KeyError, AssertionError, FileNotFoundError)
        if isinstance(exc, FATAL_TYPES):
            message = f"FATAL[{stage}]: {exc}"
        else:
            message = f"{stage}: {exc}"
        logger.error(message + f" (call_id={call_id})", exc_info=True)
        self.repo.update_call_status(user_id, call_id, "error", message)

    def process_call(self, call_id: int) -> bool:
        """Обработать один звонок от начала до конца.

        Параметры:
            call_id  — идентификатор звонка в БД

        Возвращает:
            True если обработка успешна, False при ошибке
        """
        user_id: str | None = None
        try:
            call = (
                self.repo._get_conn()
                .execute(
                    "SELECT * FROM calls WHERE call_id=?",
                    (call_id,),
                )
                .fetchone()
            )
            if not call:
                logger.error("Звонок %d не найден", call_id)
                return False

            call = dict(call)
            user_id = call["user_id"]
            contact_id = call.get("contact_id")
            audio_path = call.get("audio_path", "")

            # ── Шаг 1: Normalize ─────────────────────────────
            self.repo.update_call_status(user_id, call_id, "normalizing")
            norm_dir = user_profile_dir(
                self.config.data_dir, user_id, "audio", "normalized"
            )
            norm_dir.mkdir(parents=True, exist_ok=True)
            norm_path = str(
                norm_wav_path(norm_dir, call_id, call.get("source_filename"))
            )

            if Path(norm_path).exists():
                # Уже нормализован (резюм после прерывания): wav пишется атомарно,
                # существование ⟺ готов → пропускаем ffmpeg, переиспользуем.
                logger.info("Resume: call_id=%d пропуск normalize (wav есть)", call_id)
            else:
                normalize(audio_path, norm_path)
            duration_sec = get_duration_sec(norm_path)
            self.repo.update_call_paths(user_id, call_id, norm_path, duration_sec)
            self.repo.update_pipeline_stage(user_id, call_id, 1)
            logger.info(
                "Нормализация завершена: call_id=%d, duration=%ds",
                call_id,
                duration_sec,
            )

            # ── Шаг 2: Transcribe ────────────────────────────
            # Сначала диаризация (роли), потом ASR по turn'ам (текст по ролям).
            # F4 voice-note: один голос владельца — диаризация не нужна, turns=[].
            is_note = call.get("call_type") == "note"
            user = self.repo.get_user(user_id)
            ref_audio = user.get("ref_audio", "") if user else ""
            if is_note:
                turns = []
            else:
                self.repo.update_call_status(user_id, call_id, "diarizing")
                turns = self._diarize_turns(call_id, norm_path, ref_audio)

            self.repo.update_call_status(user_id, call_id, "transcribing")
            self.asr_runner.load()
            try:
                segments = self._asr_transcribe(norm_path, turns)
            finally:
                self.asr_runner.unload()
            logger.info(
                "Транскрибирование: call_id=%d, %d сегментов", call_id, len(segments)
            )
            if is_note:
                for seg in segments:
                    seg.speaker = "OWNER"

            # Сохранить транскрипт (БД = источник истины) + читабельный .txt
            self.repo.save_transcripts(user_id, call_id, segments)
            self._export_text(call, segments)
            self.repo.set_role_fragile(user_id, call_id, is_role_fragile(segments))

            # T-11: гейт ASR-покрытия перед stage 2 — частичное распознавание = error (видимый карантин), не COMPLETE
            asr_coverage = float(getattr(self.asr_runner, "last_coverage", 1.0))
            asr_windows_total = int(getattr(self.asr_runner, "last_windows_total", 0))
            asr_windows_failed = int(getattr(self.asr_runner, "last_windows_failed", 0))
            self.repo.set_asr_coverage(user_id, call_id, asr_coverage)
            if asr_coverage < self.config.models.asr_min_coverage:
                raise RuntimeError(
                    f"ASR partial coverage {asr_coverage:.2f} < {self.config.models.asr_min_coverage}: "
                    f"{asr_windows_failed}/{asr_windows_total} окон упали"
                )

            self.repo.update_pipeline_stage(user_id, call_id, 2)

            # F4: заметка — без анализа (промпт заточен под диалог), сразу done.
            if is_note:
                self._maybe_delete_normalized(norm_path)
                self._finalize_note(call, segments)
                return True

            # ── Шаг 4: Analyze ───────────────────────────────
            if not self.config.features.enable_llm_analysis:
                self.repo.update_call_status(user_id, call_id, "transcribed")
                self._maybe_delete_normalized(norm_path)
                return True

            self.repo.update_call_status(user_id, call_id, "analyzing")
            self._analyze_call(call_id, call, segments)
            self.repo.update_pipeline_stage(user_id, call_id, 3)

            # ── Шаг 5: Deliver ───────────────────────────────
            self.repo.update_call_status(user_id, call_id, "delivering")
            self._deliver_call(call_id, user_id, contact_id)
            self.repo.update_pipeline_stage(user_id, call_id, 4)

            # ── Готово ────────────────────────────────────────
            self.repo.update_call_status(user_id, call_id, "done")
            self._maybe_delete_normalized(norm_path)
            logger.info("✓ Звонок %d обработан полностью", call_id)
            return True

        except Exception as exc:
            if user_id is not None:
                # Определить стадию по pipeline_stage для логирования
                stage = "process_call"
                self._fail(user_id, call_id, exc, stage)
            return False

    def process_batch(self, call_ids: list[int]) -> None:
        """Batch-обработка с crash-resume по pipeline_stage (0→1→2→3→4).

        pipeline_stage персистируется в БД после каждой фазы.
        При рестарте после краша пропускает уже выполненные фазы.
        """
        if not call_ids:
            return

        logger.info("Batch-обработка: %d звонков", len(call_ids))

        calls_data = []
        for call_id in call_ids:
            call = (
                self.repo._get_conn()
                .execute("SELECT * FROM calls WHERE call_id=?", (call_id,))
                .fetchone()
            )
            if call:
                calls_data.append(dict(call))

        if not calls_data:
            return

        # Кэш пользователей для ref_audio
        users_cache: dict = {}
        for call in calls_data:
            uid = call["user_id"]
            if uid not in users_cache:
                users_cache[uid] = self.repo.get_user(uid)

        # ── Фаза 1: Normalize (параллельный ffmpeg, I/O-bound) ──────────
        from concurrent.futures import ThreadPoolExecutor, as_completed

        norm_tasks: list[dict] = []  # calls needing normalize
        for call in calls_data:
            call_id = call["call_id"]
            stage = call.get("pipeline_stage", 0)
            if stage >= 1:
                call["_norm_path"] = call.get("norm_path", "")
                continue
            user_id = call["user_id"]
            self.repo.update_call_status(user_id, call_id, "normalizing")
            norm_dir = user_profile_dir(
                self.config.data_dir, user_id, "audio", "normalized"
            )
            norm_dir.mkdir(parents=True, exist_ok=True)
            norm_path = str(
                norm_wav_path(norm_dir, call_id, call.get("source_filename"))
            )
            if Path(norm_path).exists():
                call["_norm_path"] = norm_path
                call["pipeline_stage"] = 1
                continue
            call["_norm_path"] = norm_path
            norm_tasks.append(call)

        if norm_tasks:
            max_workers = min(8, len(norm_tasks))
            logger.info("Параллельная нормализация: %d файлов, %d воркеров",
                        len(norm_tasks), max_workers)

            def _do_normalize(c: dict) -> tuple[int, bool, str]:
                cid = c["call_id"]
                try:
                    normalize(c["audio_path"], c["_norm_path"])
                    return (cid, True, "")
                except Exception as exc:
                    return (cid, False, str(exc))

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_do_normalize, c): c for c in norm_tasks}
                for future in as_completed(futures):
                    cid, ok, err = future.result()
                    call = futures[future]
                    if ok:
                        duration_sec = get_duration_sec(call["_norm_path"])
                        self.repo.update_call_paths(
                            call["user_id"], cid, call["_norm_path"], duration_sec
                        )
                        self.repo.update_pipeline_stage(call["user_id"], cid, 1)
                        call["pipeline_stage"] = 1
                        logger.info("Нормализация: call_id=%d, duration=%ds", cid, duration_sec)
                    else:
                        # Ошибка нормализации — классифицируем как синтетический RuntimeError
                        exc = RuntimeError(err)
                        self._fail(call["user_id"], cid, exc, "normalize")
                        call["_skip"] = True

        calls_data = [c for c in calls_data if not c.get("_skip")]
        gpu_clear = True  # T-12: результат VRAM-барьера после Фазы 2

        # ── Фаза 2: Transcribe + Diarize ─────────────────────────────
        # stage >= 2 → сегменты уже в БД
        segments_map: dict[int, list[Segment]] = {}

        for call in calls_data:
            call_id = call["call_id"]
            if call.get("pipeline_stage", 0) >= 2:
                rows = self.repo.get_transcript(call["user_id"], call_id)
                if rows:
                    segments_map[call_id] = [
                        Segment(
                            start_ms=int(r["start_ms"]),
                            end_ms=int(r["end_ms"]),
                            text=r["text"],
                            speaker=r["speaker"],
                        )
                        for r in rows
                    ]
                logger.info(
                    "Resume: call_id=%d пропуск transcribe (stage=%d, %d сег.)",
                    call_id, call.get("pipeline_stage", 0), len(segments_map.get(call_id, [])),
                )

        needs_transcribe = [c for c in calls_data if c.get("pipeline_stage", 0) < 2]
        if needs_transcribe:
            # Pass A: диаризация → turn'ы. pyannote грузится ОДИН раз на батч
            # (_diarize_batch), а НЕ на каждый звонок — иначе на больших партиях
            # перезагрузка моделей съедает часы. Сбой → [] (роли UNKNOWN).
            # F4: заметки (один голос) исключены из диаризации — turns_map.get(id, [])
            # ниже естественно даёт [] для них, спикер выставляется явно OWNER.
            diarize_targets = [c for c in needs_transcribe if c.get("call_type") != "note"]
            turns_map = self._diarize_batch(diarize_targets, users_cache) if diarize_targets else {}

            # Pass B+C: ASR грузится ОДИН раз на батч, но текст каждого звонка
            # сразу сохраняется и его normalized .wav УДАЛЯЕТСЯ немедленно (а не
            # после транскрибации всего батча) — wav после ASR больше не нужен
            # (save работает с сегментами в памяти), на больших прогонах это не
            # даёт wav копиться. Diarize (Pass A) уже отработал по wav выше.
            self.asr_runner.load()
            try:
                for call in needs_transcribe:
                    call_id = call["call_id"]
                    uid = call["user_id"]
                    try:
                        self.repo.update_call_status(uid, call_id, "transcribing")
                        segs = self._asr_transcribe(
                            call["_norm_path"], turns_map.get(call_id, [])
                        )
                        if call.get("call_type") == "note":
                            for seg in segs:
                                seg.speaker = "OWNER"
                        segments_map[call_id] = segs
                        logger.info("Transcribe: call_id=%d, %d сегментов", call_id, len(segs))
                        self.repo.save_transcripts(uid, call_id, segs)
                        self._export_text(call, segs)
                        self.repo.set_role_fragile(uid, call_id, is_role_fragile(segs))

                        # T-11: гейт ASR-покрытия перед stage 2
                        asr_coverage = float(getattr(self.asr_runner, "last_coverage", 1.0))
                        asr_windows_total = int(getattr(self.asr_runner, "last_windows_total", 0))
                        asr_windows_failed = int(getattr(self.asr_runner, "last_windows_failed", 0))
                        self.repo.set_asr_coverage(uid, call_id, asr_coverage)
                        if asr_coverage < self.config.models.asr_min_coverage:
                            raise RuntimeError(
                                f"ASR partial coverage {asr_coverage:.2f} < {self.config.models.asr_min_coverage}: "
                                f"{asr_windows_failed}/{asr_windows_total} окон упали"
                            )

                        self.repo.update_pipeline_stage(uid, call_id, 2)
                        call["pipeline_stage"] = 2
                    except Exception as exc:
                        self._fail(uid, call_id, exc, "transcribe")
            finally:
                # GPU-sequential (CLAUDE.md Hard Constraint): ASR+pyannote (~5GB)
                # ОБЯЗАНЫ уйти из VRAM ДО Фазы 3 — иначе они + llama-server
                # Qwen 9B Q8_0 (~10GB) > 12GB на RTX 3060 → OOM. Ко-резидентность
                # GigaAM+pyannote сохраняется ВНУТРИ Фазы 2 (грузятся раз на
                # батч, а не на каждый звонок) — выигрыш без риска для VRAM.
                gpu_clear = self._unload_models()

        # ── Фаза 2.5: Завершить голосовые заметки (F4, без анализа/доставки) ──
        # Ставим pipeline_stage=4 сразу — Фазы 3/4 ниже гейтятся по stage и
        # естественно пропускают уже-финализированные заметки, ничего доп. не нужно.
        for call in calls_data:
            if call.get("call_type") == "note" and call.get("pipeline_stage", 0) == 2:
                self._finalize_note(call, segments_map.get(call["call_id"], []))
                call["pipeline_stage"] = 4

        # ── Фаза 3: Analyze (LLM) ────────────────────────────────────
        if not gpu_clear:
            logger.error(
                "[gpu] VRAM-барьер после выгрузки ASR/pyannote НЕ пройден — Фаза 3 (LLM) пропущена "
                "(OOM-guard, T-12); звонки stage 2 подхватит process_pending после повторной выгрузки"
            )
        elif not self.config.features.enable_llm_analysis:
            logger.info("LLM analysis disabled by feature flag; skipping batch analyze phase")
            # Stage-1 terminal: транскрибированные звонки (stage 2) завершаем как
            # 'transcribed'. Иначе они залипают в status='transcribing' (Phase 4
            # deliver гейтит stage<3) и get_stalled_calls реклаймит их каждый
            # прогон = бесконечный stall-loop. Покрывает и свежие, и
            # resume-залипшие звонки. Звонки на stage>=3 (анализ был раньше)
            # идут в Phase 4 на доставку как обычно.
            for call in calls_data:
                if call.get("pipeline_stage", 0) == 2:
                    self.repo.update_call_status(
                        call["user_id"], call["call_id"], "transcribed"
                    )
                    logger.info("✓ Звонок %d → transcribed (Stage-1 done)", call["call_id"])
        else:
            for call in calls_data:
                call_id = call["call_id"]
                uid = call["user_id"]
                stage = call.get("pipeline_stage", 0)
                if stage >= 3:
                    logger.info("Resume: call_id=%d пропуск analyze (stage=%d)", call_id, stage)
                    continue
                if call_id not in segments_map:
                    continue
                try:
                    self.repo.update_call_status(uid, call_id, "analyzing")
                    self._analyze_call(call_id, call, segments_map[call_id])
                    self.repo.update_pipeline_stage(uid, call_id, 3)
                    call["pipeline_stage"] = 3
                except Exception as exc:
                    self._fail(uid, call_id, exc, "analyze")

        # ── Фаза 4: Deliver ──────────────────────────────────────────
        for call in calls_data:
            call_id = call["call_id"]
            uid = call["user_id"]
            stage = call.get("pipeline_stage", 0)
            if stage >= 4:
                continue
            if stage < 3:
                continue  # analyze не завершён
            try:
                self.repo.update_call_status(uid, call_id, "delivering")
                self._deliver_call(call_id, uid, call.get("contact_id"))
                self.repo.update_pipeline_stage(uid, call_id, 4)
                self.repo.update_call_status(uid, call_id, "done")
                logger.info("✓ Звонок %d обработан (batch)", call_id)
            except Exception as exc:
                self._fail(uid, call_id, exc, "deliver")

        logger.info("Batch завершён: %d звонков", len(call_ids))

    def process_pending(self) -> None:
        """Обработать новые звонки и зависшие после краша (crash-resume)."""
        pending = self.repo.get_pending_calls()
        stalled = self.repo.get_stalled_calls()
        pending_ids = {c["call_id"] for c in pending}
        all_calls = pending + [c for c in stalled if c["call_id"] not in pending_ids]
        if not all_calls:
            logger.debug("Нет pending/stalled звонков")
            return
        call_ids = [c["call_id"] for c in all_calls]
        if stalled:
            logger.info(
                "Найдено %d pending + %d stalled звонков", len(pending), len(stalled)
            )
        else:
            logger.info("Найдено %d pending звонков", len(pending))
        # Чанкуем: иначе turns_map/segments_map всех звонков висят в RAM (на 17k —
        # риск OOM). Прогресс пишется в БД инкрементально, resume по pipeline_stage.
        chunk = getattr(self.config.pipeline, "batch_chunk_size", 0) or 100
        if len(call_ids) <= chunk:
            self.process_batch(call_ids)
        else:
            logger.info("Обработка %d звонков чанками по %d", len(call_ids), chunk)
            for i in range(0, len(call_ids), chunk):
                self.process_batch(call_ids[i : i + chunk])

    def retry_errors(self, user_id: str | None = None) -> None:
        """Повторить звонки со статусом 'error' и retry_count < max_retries.

        If user_id is provided, only retries that user's calls (T-18 user-scope gate).
        If user_id is None, retries all users' calls (multi-user watcher).
        """
        max_retries = self.config.pipeline.max_retries
        errors = self.repo.get_error_calls(max_retries, user_id=user_id)
        if not errors:
            logger.debug("Нет звонков для повтора")
            return

        call_ids = [c["call_id"] for c in errors]
        logger.info("Повтор %d звонков с ошибками", len(call_ids))
        self.process_batch(call_ids)

    # ── Внутренние методы ─────────────────────────────────────────────

    def _export_text(self, call: dict, segments: list[Segment]) -> None:
        """Записать читабельный .txt транскрипт (по ролям).

        Путь (T-08): ``pipeline.text_export_dir/users/{user_id}/{call_id}__
        <имя_исходника>.txt`` — уникален между профилями и между звонками с
        одинаковым именем исходника. Роли: OWNER→[me], OTHER→[s2],
        UNKNOWN→[?]. На Stage-1 (без диаризации) все строки идут с ``[?]``.

        Не фатально: сбой логируется, pipeline продолжается.
        """
        text_dir = getattr(self.config.pipeline, "text_export_dir", "")
        if not text_dir:
            return
        try:
            from callprofiler.transcribe.text_export import write_transcript

            src_name = call.get("source_filename") or f"call_{call.get('call_id')}"
            out_path = write_transcript(
                text_dir, call["user_id"], call["call_id"], src_name, segments
            )
            logger.info("Текст сохранён: %s (%d строк)", out_path, len(segments))
        except Exception as exc:  # noqa: BLE001 — экспорт не валит pipeline
            logger.warning(
                "Не удалось записать текст для call_id=%s: %s",
                call.get("call_id"), exc,
            )

    def _maybe_delete_normalized(self, norm_path: str) -> None:
        """Удалить normalized .wav после транскрибации (stage 2), если включён
        ``pipeline.delete_normalized_after_transcribe``.

        На 17k звонках WAV (16кГц моно) занимают сотни ГБ; транскрипт уже в БД,
        wav для stage 3/4 (LLM/deliver) и для resume не нужен. Не фатально:
        сбой удаления логируется, pipeline продолжается.
        """
        if not getattr(self.config.pipeline, "delete_normalized_after_transcribe", False):
            return
        if not norm_path:
            return
        try:
            p = Path(norm_path)
            if p.exists():
                p.unlink()
                logger.debug("Удалён normalized wav (экономия диска): %s", norm_path)
        except Exception as exc:  # noqa: BLE001 — удаление не валит pipeline
            logger.warning("Не удалось удалить normalized %s: %s", norm_path, exc)

    def _finalize_note(self, call: dict, segments: list[Segment]) -> None:
        """Финализировать голосовую заметку владельца (F4): без LLM-анализа и
        без обычной доставки (send_summary читает analyses, которых нет у
        заметок) — свой notify с первыми символами транскрипта + опциональной
        caption-привязкой к существующему контакту.
        """
        call_id = call["call_id"]
        user_id = call["user_id"]
        self.repo.update_pipeline_stage(user_id, call_id, 4)
        self.repo.update_call_status(user_id, call_id, "done")
        transcript_text = " ".join(s.text for s in segments if s.text).strip()
        bind_status = self._maybe_bind_note_to_contact(user_id, call, transcript_text)
        if self.telegram is not None:
            try:
                asyncio.get_event_loop().run_until_complete(
                    self.telegram.send_note_ready(user_id, transcript_text, bind_status)
                )
            except Exception as exc:  # noqa: BLE001 — уведомление не валит pipeline
                logger.error(
                    "Не удалось уведомить о готовности заметки call_id=%d: %s",
                    call_id, exc,
                )
        logger.info("✓ Заметка %d готова (call_type=note)", call_id)

    def _maybe_bind_note_to_contact(
        self, user_id: str, call: dict, transcript_text: str
    ) -> str | None:
        """Привязать заметку к контакту по caption `@Имя` (F4, шаг 4).

        Caption уносится в имени файла (note_target_name, filename_parser.py) —
        единственное место, где он ещё известен на момент финализации.
        Возвращает строку статуса для уведомления владельцу, или None если
        caption не было вовсе (обычная заметка без адресата).
        """
        try:
            from callprofiler.ingest.filename_parser import parse_filename

            meta = parse_filename(call.get("source_filename") or "")
        except Exception:
            return None

        target = meta.note_target_name
        if not target:
            return None

        if not transcript_text:
            return f"⚠ Заметка не привязана к «{target}» — пустой транскрипт"

        contact, ambiguous = self.repo.find_contact_by_name(user_id, target)
        if ambiguous:
            return f"⚠ «{target}» — несколько подходящих контактов, не привязано"
        if contact is None:
            return f"⚠ Контакт «{target}» не найден, заметка не привязана"

        try:
            from callprofiler.insight.repository import append_contact_note

            conn = self.repo._get_conn()
            dt_label = call.get("call_datetime") or ""
            line = f"[{dt_label}] {transcript_text[:500]}"
            append_contact_note(conn, user_id, contact["contact_id"], line)
            label = contact.get("display_name") or contact.get("phone_e164") or target
            return f"📎 Привязано к контакту «{label}»"
        except Exception as exc:  # noqa: BLE001 — привязка не валит финализацию заметки
            logger.warning("Не удалось привязать заметку к контакту %s: %s", target, exc)
            return f"⚠ Ошибка привязки к «{target}»"

    def _unload_models(self) -> bool:
        """Выгрузить pyannote + GigaAM из VRAM. Идемпотентно. True ⇔ обе выгрузки
        прошли И VRAM-барьер пройден (T-12). False → вызывающий НЕ начинает LLM-фазу.

        Модели держатся загруженными между фазами батча (ко-резидентность),
        экономя 3-6 секунд на каждой перезагрузке.
        """
        ok = True
        for name, runner in (("pyannote", self.pyannote_runner), ("asr", self.asr_runner)):
            if runner is None:
                continue
            try:
                runner.unload()
            except Exception:
                logger.exception("[gpu] unload %s failed", name)
                ok = False
        ok = self._vram_barrier() and ok
        self.gpu_state = "EMPTY" if ok else "FAILED"
        return ok

    def _vram_barrier(self) -> bool:
        """Измеренный барьер: после gc+empty_cache занято ≤ models.gpu_unload_barrier_mb.
        Без torch/CUDA (dev-ноутбук, CPU) — барьер считается пройденным."""
        try:
            import torch
        except ImportError:
            return True
        if not torch.cuda.is_available():
            return True
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        used_mb = torch.cuda.memory_allocated() / 2**20
        limit = getattr(self.config.models, "gpu_unload_barrier_mb", 512)
        if used_mb > limit:
            logger.error("[gpu] после выгрузки занято %.0f MB > барьер %d MB", used_mb, limit)
            return False
        return True

    def _warn_once(self, key: str, msg: str, *args) -> None:
        """Залогировать WARNING ровно один раз на причину (key).

        Диаризация деградирует gracefully (роли → UNKNOWN), но раньше КАЖДАЯ
        причина сбоя сваливалась в один невнятный warning, и пользователь не мог
        понять, ЧТО чинить. Теперь каждая причина логируется один раз с конкретным
        указанием, что именно отсутствует/неверно.
        """
        if key in self._diag_warned:
            return
        self._diag_warned.add(key)
        logger.warning(msg, *args)

    def _diarize_turns(self, call_id, norm_path: str, ref_audio: str) -> list[dict]:
        """Диаризация → turn'ы (OWNER/OTHER) для назначения ролей.

        Возвращает список dict ``{start_ms, end_ms, speaker}`` или ``[]``, если
        диаризация выключена / нет ref_audio / нет токена / сбой (graceful —
        транскрипт не теряется, роли просто остаются UNKNOWN, см.
        ``.claude/rules/pipeline.md``). pyannote ВСЕГДА выгружается (VRAM перед
        ASR/LLM-фазой). Каждая причина сбоя логируется один раз с указанием фикса.
        """
        if not self.config.features.enable_diarization:
            return []

        if not (ref_audio and Path(ref_audio).exists()):
            self._warn_once(
                "no_ref",
                "Диаризация включена, но ref_audio отсутствует (%r) — роли остаются "
                "UNKNOWN. Задайте эталон голоса владельца: bootstrap/add-user "
                "--ref-audio <owner.wav> (файл должен существовать).",
                ref_audio,
            )
            return []

        if not self.config.hf_token:
            # Не блокируем: модели могли быть скачаны заранее в локальный HF-кэш.
            self._warn_once(
                "no_token",
                "Диаризация включена, но HF_TOKEN пуст — gated-модели pyannote "
                "(speaker-diarization-3.1, embedding) обычно отвечают 401 и роли "
                "будут UNKNOWN. Задайте HF_TOKEN и примите условия моделей на "
                "huggingface.co.",
            )

        try:
            if self.pyannote_runner is None:
                try:
                    from callprofiler.diarize.pyannote_runner import PyannoteRunner
                except ImportError as exc:
                    self._warn_once(
                        "no_pyannote",
                        "Диаризация включена, но стек ролей не установлен (%s) — роли "
                        "UNKNOWN. Установите: pip install pyannote.audio==3.3.2 librosa "
                        "soundfile (секция ROLES в requirements-gigaam.txt).",
                        exc,
                    )
                    return []
                self.pyannote_runner = PyannoteRunner(self.config)
            self.pyannote_runner.load(ref_audio)
            turns = self.pyannote_runner.diarize(norm_path)
            logger.info("Диаризация: call_id=%s, %d turn'ов", call_id, len(turns))
            return turns or []
        except Exception as exc:  # noqa: BLE001 — роли необязательны
            self._warn_once(
                "diarize_fail_%s" % type(exc).__name__,
                "Диаризация упала (%s: %s) — роли UNKNOWN, pipeline продолжается. "
                "Частые причины: gated-модель не принята на HF / неверный HF_TOKEN / "
                "не установлены librosa|soundfile.",
                type(exc).__name__, exc,
            )
            logger.debug("Диаризация call_id=%s — полный трейс:", call_id, exc_info=True)
            return []
        finally:
            if self.pyannote_runner is not None:
                self.pyannote_runner.unload()

    def _diarize_batch(
        self, calls: list[dict], users_cache: dict
    ) -> dict[int, list[dict]]:
        """Диаризовать ПАЧКУ звонков, загрузив pyannote ОДИН раз на каждый
        уникальный ``ref_audio`` (не на каждый звонок).

        Узкое место масштаба: ``_diarize_turns`` грузит модели + строит
        ref-эмбеддинг и выгружает на КАЖДЫЙ звонок (~2-3 c/звонок) — на 17k это
        часы впустую. Здесь pyannote живёт на всю группу одного ref (обычно один
        юзер = один ref → одна загрузка на батч).

        Возвращает ``{call_id: turns}``; диаризация выключена / нет ref / сбой
        звонка → ``[]`` (роли UNKNOWN, pipeline продолжается). pyannote ВСЕГДА
        выгружается (VRAM перед ASR/LLM). Причины сбоя логируются один раз.
        """
        turns_map: dict[int, list[dict]] = {c["call_id"]: [] for c in calls}
        if not self.config.features.enable_diarization or not calls:
            return turns_map

        if not self.config.hf_token:
            self._warn_once(
                "no_token",
                "Диаризация включена, но HF_TOKEN пуст — gated-модели pyannote "
                "обычно отвечают 401 и роли будут UNKNOWN. Задайте HF_TOKEN.",
            )

        from collections import defaultdict

        by_ref: dict[str, list[dict]] = defaultdict(list)
        for call in calls:
            user = users_cache.get(call["user_id"])
            ref = user.get("ref_audio", "") if user else ""
            by_ref[ref].append(call)

        for ref_audio, group in by_ref.items():
            if not (ref_audio and Path(ref_audio).exists()):
                self._warn_once(
                    "no_ref",
                    "Диаризация включена, но ref_audio отсутствует (%r) — роли "
                    "UNKNOWN. Задайте эталон голоса владельца.",
                    ref_audio,
                )
                continue

            if self.pyannote_runner is None:
                try:
                    from callprofiler.diarize.pyannote_runner import PyannoteRunner
                except ImportError as exc:
                    self._warn_once(
                        "no_pyannote",
                        "Диаризация включена, но стек ролей не установлен (%s) — "
                        "роли UNKNOWN. pip install pyannote.audio librosa soundfile.",
                        exc,
                    )
                    return turns_map
                self.pyannote_runner = PyannoteRunner(self.config)

            try:
                self.pyannote_runner.load(ref_audio)  # ОДИН раз на ref

                # Постусловие: эмбеддинг загруженного runner'а обязан
                # соответствовать ЭТОЙ ref-группе (bugs.md — utечка эмбеддинга
                # между профилями при смене ref без выгрузки модели).
                from callprofiler.artifacts import file_fingerprint
                expected_fp = file_fingerprint(ref_audio)
                # Fail-closed: отсутствие атрибута — тоже несоответствие. Дефолт
                # expected_fp сделал бы сторожа бесшумно бесполезным для любого
                # другого runner'а (тест-дубль, будущий ECAPA — план Б C-03).
                actual_fp = getattr(self.pyannote_runner, "ref_fingerprint", None)
                if actual_fp != expected_fp:
                    logger.error(
                        "Pyannote ref_fingerprint не совпадает с группой (ref=%r) — "
                        "пропуск группы, роли UNKNOWN (защита от чужого эталона)",
                        ref_audio,
                    )
                    continue

                for call in group:
                    call_id = call["call_id"]
                    self.repo.update_call_status(call["user_id"], call_id, "diarizing")
                    try:
                        turns = self.pyannote_runner.diarize(call["_norm_path"]) or []
                        turns_map[call_id] = turns
                        logger.info(
                            "Диаризация: call_id=%s, %d turn'ов", call_id, len(turns)
                        )
                    except Exception as exc:  # noqa: BLE001 — звонок не валит батч
                        self._warn_once(
                            "diarize_fail_%s" % type(exc).__name__,
                            "Диаризация упала (%s: %s) — роли UNKNOWN, продолжаем.",
                            type(exc).__name__, exc,
                        )
                        logger.debug(
                            "Диаризация call_id=%s — трейс:", call_id, exc_info=True
                        )
            except Exception as exc:  # noqa: BLE001 — load() упал → группа UNKNOWN
                self._warn_once(
                    "diarize_load_%s" % type(exc).__name__,
                    "Загрузка pyannote упала (%s: %s) — роли UNKNOWN для группы. "
                    "Частые причины: gated-модель не принята / неверный HF_TOKEN.",
                    type(exc).__name__, exc,
                )
                logger.debug("pyannote load — трейс:", exc_info=True)
            # pyannote НЕ выгружаем — остаётся в VRAM для ко-резидентности
            # с GigaAM. Выгрузится в _unload_models() после всего батча.

        return turns_map

    def _asr_transcribe(self, norm_path: str, turns: list[dict]) -> list[Segment]:
        """Транскрибировать (ASR уже load()'нут). ``turns`` → роли.

        GigaAM + turns → ``transcribe_turns`` (текст по ролям, по сегментам
        спикеров). Иначе flat ``transcribe`` + ``assign_speakers`` поверх (Whisper).
        """
        if turns and hasattr(self.asr_runner, "transcribe_turns"):
            return self.asr_runner.transcribe_turns(norm_path, turns)
        segments = self.asr_runner.transcribe(norm_path)
        if turns:
            try:
                segments = assign_speakers(segments, turns)
            except Exception as exc:  # noqa: BLE001
                logger.warning("assign_speakers упал (роли UNKNOWN): %s", exc)
        return segments

    def _diarize_segments(
        self,
        call_id: int,
        norm_path: str,
        segments: list[Segment],
        ref_audio: str,
    ) -> list[Segment]:
        """Назначить роли спикеров через pyannote, с graceful degradation.

        Правила (`.claude/rules/pipeline.md` + CONSTITUTION Ст.9.3):
          - диаризация выключена или нет ref_audio → сегменты остаются UNKNOWN;
          - любой сбой pyannote (load/diarize) → логируем warning, сегменты
            остаются UNKNOWN, pipeline ПРОДОЛЖАЕТСЯ (транскрипт не теряется);
          - pyannote ВСЕГДА выгружается (finally) — иначе VRAM не освободится
            перед LLM-фазой и она упадёт по OOM.
        """
        if not self.config.features.enable_diarization:
            logger.info(
                "Diarization disabled by feature flag (call_id=%d); speakers=UNKNOWN",
                call_id,
            )
            return segments

        if not (ref_audio and Path(ref_audio).exists()):
            logger.warning(
                "Нет ref_audio для call_id=%d, пропуск диаризации (speakers=UNKNOWN)",
                call_id,
            )
            return segments

        try:
            if self.pyannote_runner is None:
                from callprofiler.diarize.pyannote_runner import PyannoteRunner
                self.pyannote_runner = PyannoteRunner(self.config)
            self.pyannote_runner.load(ref_audio)
            diarization = self.pyannote_runner.diarize(norm_path)
            result = assign_speakers(segments, diarization)
            logger.info(
                "Диаризация: call_id=%d, %d интервалов", call_id, len(diarization)
            )
            return result
        except Exception as exc:
            logger.warning(
                "Диаризация упала для call_id=%d, сегменты остаются UNKNOWN "
                "(pipeline продолжается): %s",
                call_id, exc,
            )
            return segments
        finally:
            if self.pyannote_runner is not None:
                self.pyannote_runner.unload()

    def _analyze_call(
        self,
        call_id: int,
        call: dict,
        segments: list[Segment],
    ) -> None:
        """Запустить LLM-анализ для звонка через AnalysisService.

        Gate B: анализ → orchestrator → сохранение
          1. Short-call stub: parse_status='stub_short' (легитимное снижение качества, не ошибка)
          2. LLM ConnectionError/RuntimeError: log.error, update_call_status("error"), return (нет invented analysis)
          3. После реального ответа LLM: если parse_status in (parse_failed, parsed_partial, output_truncated)
             → update_call_status("error"), return (не сохраняем quarantine-анализ)
        """
        user_id = call["user_id"]
        contact_id = call.get("contact_id")

        # Короткие звонки — skip LLM entirely (Sprint 4)
        transcript_text = " ".join(s.text for s in segments).strip()
        is_short_call = (
            len(transcript_text) < 50
            and not any(kw in transcript_text.lower() for kw in ("долг", "обещ", "срок", "завтра", "оплат"))
        )

        if is_short_call:
            logger.info(
                "Короткий звонок call_id=%d (%d символов), skip LLM",
                call_id, len(transcript_text),
            )
            analysis = parse_llm_response(
                "",
                model=self.config.models.llm_model,
                prompt_version=PROMPT_VERSION_ANALYZE,
            )
            analysis.call_type = "short"
            # Gate B.1: Отметить как stub, не как failure
            analysis.parse_status = "stub_short"
        else:
            # Использовать AnalysisService (единая точка анализа, F11.1)
            try:
                from callprofiler.analyze.service import AnalysisService

                svc = AnalysisService(self.config, self.repo, user_id=call.get("user_id", ""))
                analysis = svc.analyze_one_call(call, segments)
            except (ConnectionError, RuntimeError) as exc:
                # Gate B.2: LLM недоступен — логируем, помечаем статус, НЕ сохраняем анализ
                logger.error("LLM недоступен для call_id=%d: %s", call_id, exc)
                self._fail(user_id, call_id, exc, "analyze")
                return
            except Exception as exc:
                logger.error("Ошибка анализа call_id=%d: %s", call_id, exc)
                self._fail(user_id, call_id, exc, "analyze")
                return

        # Gate B.3: После реального ответа от LLM — проверяем parse_status
        # Если это критичный отказ парсера (не stub), не сохраняем
        parse_status = getattr(analysis, "parse_status", "unknown")
        if not is_short_call and parse_status in ("parse_failed", "parsed_partial", "output_truncated"):
            error_msg = f"LLM {parse_status}: {getattr(analysis, 'raw_response', '')[:300]}"
            logger.error(
                "Анализ call_id=%d quarantined (parse_status=%s), не сохраняем",
                call_id, parse_status,
            )
            exc = RuntimeError(error_msg)
            self._fail(user_id, call_id, exc, "analyze")
            return

        # T-04: анализ + обещания + summary + граф — одна граница транзакции.
        # Раньше каждый save_* коммитил отдельно; крах между ними оставлял
        # частично записанное состояние (analyses без promises, граф без
        # свежих analyses — P-DB-02/P-DB-05).
        conn = self.repo._get_conn()
        with uow_for(conn):
            # Сохранить анализ в БД
            self.repo.save_analysis(user_id, call_id, analysis)

            # Сохранить обещания
            if analysis.promises and contact_id:
                self.repo.save_promises(user_id, contact_id, call_id, analysis.promises)

            # Rebuild contact summary after analysis (Sprint 4)
            if contact_id:
                try:
                    from callprofiler.aggregate.summary_builder import SummaryBuilder

                    SummaryBuilder(self.repo).rebuild_contact(user_id, contact_id)
                    logger.debug(
                        "Summary rebuilt: user=%s, contact_id=%d", user_id, contact_id
                    )
                except Exception as _sbe:
                    logger.warning(
                        "Summary rebuild failed (non-fatal): %s", _sbe
                    )

            # Обновить Knowledge Graph (non-fatal)
            try:
                from callprofiler.graph.builder import GraphBuilder
                from callprofiler.graph.repository import apply_graph_schema

                apply_graph_schema(conn)
                GraphBuilder(conn).update_from_call(call_id)
            except Exception as _graph_exc:
                logger.warning(
                    "graph update failed for call_id=%d: %s", call_id, _graph_exc
                )

        logger.info(
            "Анализ: call_id=%d, priority=%d, risk=%d, parse_status=%s",
            call_id,
            analysis.priority,
            analysis.risk_score,
            getattr(analysis, "parse_status", "?"),
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
        if self.telegram and self.config.features.enable_telegram_notification:
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
