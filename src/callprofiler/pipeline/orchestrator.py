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

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.prompt_builder import PromptBuilder
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.audio.normalizer import get_duration_sec, normalize
from callprofiler.deliver.card_generator import CardGenerator
from callprofiler.deliver.telegram_bot import TelegramNotifier
from callprofiler.diarize.role_assigner import assign_speakers
from callprofiler.models import Segment
from callprofiler.transcribe.whisper_runner import WhisperRunner


def _make_asr_runner(config: "Config"):
    """Factory: return ASR runner based on config.models.asr_backend."""
    backend = getattr(config.models, "asr_backend", "whisper")
    if backend == "gigaam":
        from callprofiler.transcribe.gigaam_runner import GigaAMRunner
        return GigaAMRunner(config)
    return WhisperRunner(config)

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
        self.asr_runner = _make_asr_runner(config)
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

    def process_call(self, call_id: int) -> bool:
        """Обработать один звонок от начала до конца.

        Параметры:
            call_id  — идентификатор звонка в БД

        Возвращает:
            True если обработка успешна, False при ошибке
        """
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
            self.repo.update_call_status(call_id, "normalizing")
            norm_dir = (
                Path(self.config.data_dir) / "users" / user_id / "audio" / "normalized"
            )
            norm_dir.mkdir(parents=True, exist_ok=True)
            norm_path = str(norm_dir / f"{call_id}.wav")

            normalize(audio_path, norm_path)
            duration_sec = get_duration_sec(norm_path)
            self.repo.update_call_paths(call_id, norm_path, duration_sec)
            self.repo.update_pipeline_stage(call_id, 1)
            logger.info(
                "Нормализация завершена: call_id=%d, duration=%ds",
                call_id,
                duration_sec,
            )

            # ── Шаг 2: Transcribe ────────────────────────────
            # Сначала диаризация (роли), потом ASR по turn'ам (текст по ролям)
            user = self.repo.get_user(user_id)
            ref_audio = user.get("ref_audio", "") if user else ""
            self.repo.update_call_status(call_id, "diarizing")
            turns = self._diarize_turns(call_id, norm_path, ref_audio)

            self.repo.update_call_status(call_id, "transcribing")
            self.asr_runner.load()
            try:
                segments = self._asr_transcribe(norm_path, turns)
            finally:
                self.asr_runner.unload()
            logger.info(
                "Транскрибирование: call_id=%d, %d сегментов", call_id, len(segments)
            )

            # Сохранить транскрипт (БД = источник истины) + читабельный .txt
            self.repo.save_transcripts(call_id, segments)
            self._export_text(call, segments)
            self.repo.update_pipeline_stage(call_id, 2)

            # ── Шаг 4: Analyze ───────────────────────────────
            if self.config.features.enable_llm_analysis:
                self.repo.update_call_status(call_id, "analyzing")
                self._analyze_call(call_id, call, segments)
                self.repo.update_pipeline_stage(call_id, 3)
            else:
                logger.info(
                    "LLM analysis disabled by feature flag; skipping call_id=%d",
                    call_id,
                )

            # ── Шаг 5: Deliver ───────────────────────────────
            self.repo.update_call_status(call_id, "delivering")
            self._deliver_call(call_id, user_id, contact_id)
            self.repo.update_pipeline_stage(call_id, 4)

            # ── Готово ────────────────────────────────────────
            self.repo.update_call_status(call_id, "done")
            logger.info("✓ Звонок %d обработан полностью", call_id)
            return True

        except Exception as exc:
            logger.error("Ошибка при обработке call_id=%d: %s", call_id, exc)
            self.repo.update_call_status(call_id, "error", str(exc))
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

        # ── Фаза 1: Normalize ────────────────────────────────────────
        for call in calls_data:
            call_id = call["call_id"]
            stage = call.get("pipeline_stage", 0)
            if stage >= 1:
                call["_norm_path"] = call.get("norm_path", "")
                logger.info("Resume: call_id=%d пропуск normalize (stage=%d)", call_id, stage)
                continue
            try:
                self.repo.update_call_status(call_id, "normalizing")
                user_id = call["user_id"]
                norm_dir = (
                    Path(self.config.data_dir) / "users" / user_id / "audio" / "normalized"
                )
                norm_dir.mkdir(parents=True, exist_ok=True)
                norm_path = str(norm_dir / f"{call_id}.wav")
                normalize(call["audio_path"], norm_path)
                duration_sec = get_duration_sec(norm_path)
                self.repo.update_call_paths(call_id, norm_path, duration_sec)
                self.repo.update_pipeline_stage(call_id, 1)
                call["_norm_path"] = norm_path
                call["pipeline_stage"] = 1
                logger.info("Нормализация: call_id=%d, duration=%ds", call_id, duration_sec)
            except Exception as exc:
                logger.error("Ошибка нормализации call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))
                call["_skip"] = True

        calls_data = [c for c in calls_data if not c.get("_skip")]

        # ── Фаза 2: Transcribe + Diarize ─────────────────────────────
        # stage >= 2 → сегменты уже в БД
        segments_map: dict[int, list[Segment]] = {}

        for call in calls_data:
            call_id = call["call_id"]
            if call.get("pipeline_stage", 0) >= 2:
                rows = self.repo.get_transcript(call_id)
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
            # Pass A: диаризация → turn'ы (pyannote per-call, graceful). Делаем ДО
            # ASR — GigaAM транскрибирует по turn'ам. Сбой → [] (роли UNKNOWN).
            turns_map: dict[int, list[dict]] = {}
            for call in needs_transcribe:
                call_id = call["call_id"]
                self.repo.update_call_status(call_id, "diarizing")
                user = users_cache.get(call["user_id"])
                ref_audio = user.get("ref_audio", "") if user else ""
                turns_map[call_id] = self._diarize_turns(
                    call_id, call["_norm_path"], ref_audio
                )

            # Pass B: ASR — модель грузится ОДИН раз на весь батч
            self.asr_runner.load()
            for call in needs_transcribe:
                call_id = call["call_id"]
                try:
                    self.repo.update_call_status(call_id, "transcribing")
                    segs = self._asr_transcribe(
                        call["_norm_path"], turns_map.get(call_id, [])
                    )
                    segments_map[call_id] = segs
                    logger.info("Transcribe: call_id=%d, %d сегментов", call_id, len(segs))
                except Exception as exc:
                    logger.error("Ошибка транскрибирования call_id=%d: %s", call_id, exc)
                    self.repo.update_call_status(call_id, "error", str(exc))
            self.asr_runner.unload()

            # Pass C: сохранить транскрипт (БД) + .txt + stage 2
            for call in needs_transcribe:
                call_id = call["call_id"]
                if call_id not in segments_map:
                    continue
                try:
                    self.repo.save_transcripts(call_id, segments_map[call_id])
                    self._export_text(call, segments_map[call_id])
                    self.repo.update_pipeline_stage(call_id, 2)
                    call["pipeline_stage"] = 2
                except Exception as exc:
                    logger.error("Ошибка транскрипта call_id=%d: %s", call_id, exc)
                    self.repo.update_call_status(call_id, "error", str(exc))

        # ── Фаза 3: Analyze (LLM) ────────────────────────────────────
        if not self.config.features.enable_llm_analysis:
            logger.info("LLM analysis disabled by feature flag; skipping batch analyze phase")
        else:
            for call in calls_data:
                call_id = call["call_id"]
                stage = call.get("pipeline_stage", 0)
                if stage >= 3:
                    logger.info("Resume: call_id=%d пропуск analyze (stage=%d)", call_id, stage)
                    continue
                if call_id not in segments_map:
                    continue
                try:
                    self.repo.update_call_status(call_id, "analyzing")
                    self._analyze_call(call_id, call, segments_map[call_id])
                    self.repo.update_pipeline_stage(call_id, 3)
                    call["pipeline_stage"] = 3
                except Exception as exc:
                    logger.error("Ошибка анализа call_id=%d: %s", call_id, exc)
                    self.repo.update_call_status(call_id, "error", str(exc))

        # ── Фаза 4: Deliver ──────────────────────────────────────────
        for call in calls_data:
            call_id = call["call_id"]
            stage = call.get("pipeline_stage", 0)
            if stage >= 4:
                continue
            if stage < 3:
                continue  # analyze не завершён
            try:
                self.repo.update_call_status(call_id, "delivering")
                self._deliver_call(call_id, call["user_id"], call.get("contact_id"))
                self.repo.update_pipeline_stage(call_id, 4)
                self.repo.update_call_status(call_id, "done")
                logger.info("✓ Звонок %d обработан (batch)", call_id)
            except Exception as exc:
                logger.error("Ошибка доставки call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))

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

    def _export_text(self, call: dict, segments: list[Segment]) -> None:
        """Записать читабельный .txt транскрипт (по ролям).

        Путь: ``pipeline.text_export_dir / <имя_исходника>.txt`` — имя равно
        имени исходного аудиофайла, расширение меняется на ``.txt``.
        Роли: OWNER→[me], OTHER→[s2], UNKNOWN→[?]. На Stage-1 (без диаризации)
        все строки идут с ``[?]``.

        Не фатально: сбой логируется, pipeline продолжается.
        """
        text_dir = getattr(self.config.pipeline, "text_export_dir", "")
        if not text_dir:
            return
        try:
            from callprofiler.transcribe.text_export import write_transcript

            src_name = call.get("source_filename") or f"call_{call.get('call_id')}"
            out_path = write_transcript(text_dir, src_name, segments)
            logger.info("Текст сохранён: %s (%d строк)", out_path, len(segments))
        except Exception as exc:  # noqa: BLE001 — экспорт не валит pipeline
            logger.warning(
                "Не удалось записать текст для call_id=%s: %s",
                call.get("call_id"), exc,
            )

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
        """Запустить LLM-анализ для звонка через AnalysisService."""
        user_id = call["user_id"]
        contact_id = call.get("contact_id")

        # Короткие звонки — skip LLM entirely (Sprint 4)
        transcript_text = " ".join(s.text for s in segments).strip()
        if len(transcript_text) < 50 and not any(
            kw in transcript_text.lower() for kw in ("долг", "обещ", "срок", "завтра", "оплат")
        ):
            logger.info(
                "Короткий звонок call_id=%d (%d символов), skip LLM",
                call_id, len(transcript_text),
            )
            analysis = parse_llm_response(
                "",
                model=self.config.models.llm_model,
                prompt_version="v001",
            )
            analysis.call_type = "short"
        else:
            # Использовать AnalysisService (единая точка анализа, F11.1)
            try:
                from callprofiler.analyze.service import AnalysisService

                svc = AnalysisService(self.config, self.repo)
                analysis = svc.analyze_one_call(call, segments)
            except (ConnectionError, RuntimeError) as exc:
                logger.error("LLM недоступен для call_id=%d: %s", call_id, exc)
                analysis = parse_llm_response(
                    "",
                    model=self.config.models.llm_model,
                    prompt_version="v001",
                )
            except Exception as exc:
                logger.error("Ошибка анализа call_id=%d: %s", call_id, exc)
                self.repo.update_call_status(call_id, "error", str(exc))
                return

        # Сохранить анализ в БД
        self.repo.save_analysis(call_id, analysis)

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

            conn = self.repo._get_conn()
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
