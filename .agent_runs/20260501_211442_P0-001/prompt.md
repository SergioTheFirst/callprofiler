You are a senior Python/software architecture agent working on CallProfiler.

        Project:
        - Name: CallProfiler
        - Root: C:/pro/callprofiler
        - Mission: Локальная мультипользовательская система пост-обработки записей телефонных разговоров: audio -> normalize -> whisper -> pyannote -> llama.cpp/Qwen -> SQLite -> Telegram/caller cards.

        Runtime constraints:
        - Windows 11, системный Python 3.10+, SQLite, без Docker/Redis/PostgreSQL/LangChain.
- GPU-дисциплина: Whisper/pyannote и Qwen llama-server не должны конкурировать за VRAM.
- LLM: локальный llama-server OpenAI-compatible endpoint, целевая модель Qwen3.5-9B.Q8_0.gguf, context 16384.
- Все данные пользователей должны быть изолированы через user_id.
- Оригиналы аудио не модифицировать.

        Mandatory guardrails:
        - Перед правкой читать CONTINUITY.md, CHANGELOG.md, CONSTITUTION.md и релевантные source-файлы.
- Один backlog item = один вертикальный срез, без массового переписывания модулей.
- Не добавлять новые зависимости без отдельной задачи и обоснования.
- Не использовать except/pass и не скрывать ошибки.
- Для каждого изменения добавлять или обновлять узкие тесты.
- Если задача требует изменения схемы SQLite, миграция должна быть идемпотентной и проходить через существующий migration-паттерн Repository/_migrate или graph repository migration.

        Current task:
        - id: P0-001
        - title: Синхронизировать документационный источник истины по LLM/runtime
        - type: documentation
        - priority: 0

        Description:
        Убрать архитектурную неоднозначность: в документах одновременно описаны Ollama/Qwen2.5, llama-server/Qwen3.5 Q5, текущая Qwen3.5 Q8_0, разные host и разные data_dir. Нужно зафиксировать актуальный runtime-контракт, чтобы следующие агенты не делали несовместимые решения.

        Rationale:
        Пока docs противоречат друг другу, любой агент может выбрать старый Ollama API или неправильный путь данных. Это источник повторяющихся регрессий.

        Artifacts:
        ```json
        {
  "touch": [
    "AGENTS.md",
    "CLAUDE.md",
    "CONSTITUTION.md",
    "README.md",
    "ARCHITECTURE_v4.md",
    "STRATEGIC_PLAN_v4.md",
    ".claude/rules/llm.md",
    ".claude/rules/decisions.md",
    "CHANGELOG.md",
    "CONTINUITY.md"
  ],
  "read": [
    "configs/base.yaml",
    "src/callprofiler/analyze/llm_client.py",
    "src/callprofiler/pipeline/orchestrator.py"
  ]
}
        ```

        Implementation notes:
        - Зафиксировать: llama-server.exe -m C:/models/Qwen3.5-9B.Q8_0.gguf -ngl 99 -c 16384 -fa auto --host 0.0.0.0 --port 8080.
- Явно отметить, что Ollama упоминается только как legacy alias, не как runtime.
- Объяснить риск host 0.0.0.0: доступ из LAN; если доступ с других машин не нужен, рекомендовать 127.0.0.1.
- Не менять код в этой задаче.

        Acceptance criteria:
        - В документах нет взаимоисключающих указаний Ollama vs llama-server для текущего runtime.
- CONSTITUTION/AGENTS/llm rules одинаково описывают LLM endpoint и модель.
- CHANGELOG.md и CONTINUITY.md обновлены.

        Verification expected:
        - Прочитать измененные markdown-файлы и проверить отсутствие старых активных инструкций Ollama/Qwen2.5.
- Тесты не обязательны, так как меняется только документация.

        Work rules:
        - Make the smallest vertical change that satisfies this task only.
        - Do not implement later backlog tasks.
        - Do not change files outside artifacts.touch unless unavoidable; explain why.
        - Add/update focused tests when the task touches runtime behavior.
        - Keep changes compatible with local-only Windows + SQLite + llama.cpp architecture.
        - Preserve CHANGELOG.md and CONTINUITY.md discipline when task artifacts include them.

        Response format:
        1. Brief plan.
        2. Unified diff patch in one fenced ```diff block, OR state that you edited files directly if the runner is in direct mode.
        3. Verification commands to run.

        Relevant context follows.

        ## configs/base.yaml
```text
data_dir: "C:\\calls\\data"
log_file: "C:\\calls\\data\\logs\\pipeline.log"

models:
  whisper: "large-v3"
  whisper_device: "cuda"
  whisper_compute: "float16"
  whisper_beam_size: 5
  whisper_language: "ru"
  llm_model: "local"
  llm_url: "http://127.0.0.1:8080/v1/chat/completions"

pipeline:
  watch_interval_sec: 30
  file_settle_sec: 5
  max_retries: 3
  retry_interval_sec: 3600

audio:
  sample_rate: 16000
  channels: 1
  format: "wav"

hf_token: "TOKEN"

```

## src/callprofiler/analyze/llm_client.py
```text
# -*- coding: utf-8 -*-
"""
llm_client.py — клиент для локального LLM (llama.cpp) с OpenAI-совместимым API.

Используется для отправки промптов на локально запущенный llama-server
и получения ответов в формате OpenAI API.

API endpoint: http://127.0.0.1:8080/v1/chat/completions
Формат совместим с OpenAI API, но без необходимости указывать модель.
"""

from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Клиент для взаимодействия с локальным llama-server (llama.cpp).

    llama-server должен быть запущен с флагом -api для OpenAI-совместимого API.

    Использование:
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        response = client.generate(
            messages=[
                {"role": "system", "content": "Ты анализируешь стенограммы"},
                {"role": "user", "content": "Проанализируй..."}
            ]
        )
        print(response)  # JSON строка или текст ответа
    """

    def __init__(self, base_url: str, timeout: int = 180) -> None:
        """Инициализировать LLM клиент.

        Параметры:
            base_url  — URL endpoint (обычно http://127.0.0.1:8080/v1/chat/completions)
            timeout   — timeout для запроса в секундах (по умолчанию 180 для длинных звонков)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._verify_connection()

    def _verify_connection(self) -> None:
        """Проверить что llama-server доступен при инициализации.

        Raises:
            ConnectionError  — если сервер недоступен
        """
        try:
            # Попытаться минимальный запрос
            response = requests.post(
                self.base_url,
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "temperature": 0.1,
                    "max_tokens": 10,
                },
                timeout=5,
            )
            response.raise_for_status()
            logger.info("✓ LLM сервер доступен на %s", self.base_url)
        except requests.ConnectionError as exc:
            raise ConnectionError(
                f"Не удаётся подключиться к llama-server на {self.base_url}. "
                f"Запустите: llama-server -api"
            ) from exc
        except requests.RequestException as exc:
            logger.warning("Предупреждение при проверке LLM сервера: %s", exc)

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> str | None:
        """Отправить сообщения в LLM и получить ответ.

        Параметры:
            messages     — список сообщений в формате OpenAI API
                          [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            temperature  — параметр температуры (0.0-2.0), по умолчанию 0.3 для консистентного JSON
            max_tokens   — максимальное число токенов в ответе (1500 для полного JSON)

        Возвращает:
            Полный ответ модели (текст или JSON), или None при ошибке
        """
        logger.debug(
            "Отправка промпта в LLM сервер (сообщений: %d, max_tokens: %d)",
            len(messages), max_tokens,
        )

        try:
            response = requests.post(
                self.base_url,
                json={
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            try:
                result = response.json()
                # OpenAI API format: response["choices"][0]["message"]["content"]
                return result["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                logger.error("Невалидный ответ от LLM сервера: %s", response.text[:200])
                return None

        except requests.Timeout as exc:
            logger.error("Timeout при запросе к LLM серверу (timeout=%ds): %s", self.timeout, exc)
            return None
        except requests.RequestException as exc:
            logger.error("Ошибка при запросе к LLM серверу: %s", exc)
            return None


# Для обратной совместимости (если что-то ещё использует OllamaClient)
OllamaClient = LLMClient

```

## src/callprofiler/pipeline/orchestrator.py
```text
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

            if not self.config.features.enable_diarization:
                logger.info("Diarization disabled by feature flag; speakers=UNKNOWN")
            elif ref_audio and Path(ref_audio).exists():
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
            if self.config.features.enable_llm_analysis:
                self.repo.update_call_status(call_id, "analyzing")
                self._analyze_call(call_id, call, segments)
            else:
                logger.info("LLM analysis disabled by feature flag; skipping call_id=%d", call_id)

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

                if not self.config.features.enable_diarization:
                    logger.info("Diarization disabled by feature flag (call_id=%d)", call_id)
                elif ref_audio and Path(ref_audio).exists():
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
        if not self.config.features.enable_llm_analysis:
            logger.info("LLM analysis disabled by feature flag; skipping batch analyze phase")
        else:
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

```

## AGENTS.md
```text
# AGENTS.md — Руководство для AI-агентов

Этот файл — **точка входа для любого AI-агента**, работающего с репозиторием
CallProfiler (Claude Code, Cursor, Codex, любые другие). Он не заменяет
`CONSTITUTION.md`, `CLAUDE.md`, `CHANGELOG.md` и `CONTINUITY.md`, а
связывает их в рабочий процесс.

> **TL;DR для агента:**
> 1. Прочитай `CONTINUITY.md` (где мы остановились) и последние 50 строк `CHANGELOG.md`.
> 2. Сверься с `CONSTITUTION.md` — это merge-blocking правила.
> 3. Сделай задачу в маленьком вертикальном срезе, не ломая GPU-дисциплину и изоляцию по `user_id`.
> 4. Прогоняй `pytest` после каждого нетривиального изменения.
> 5. Перед завершением сессии обнови `CHANGELOG.md` + `CONTINUITY.md` и сделай коммит.

---

## 1. Что это за проект

CallProfiler — локальная мультипользовательская система пост-обработки
записей телефонных разговоров:

```
аудиофайл → normalize → whisper → pyannote → LLM → SQLite → Telegram / caller card
```

Целевая машина: Windows 11 + RTX 3060 12GB + системный Python 3.10+ (без venv).
Никаких облаков, Docker, Redis, PostgreSQL (см. `CONSTITUTION.md` Статья 4).

---

## 2. Структура репозитория

```
callprofiler/
├── AGENTS.md                ← этот файл (руководство для AI)
├── CLAUDE.md                ← исходный план разработки (15 шагов)
├── CONSTITUTION.md          ← merge-blocking правила (18 статей)
├── CHANGELOG.md             ← журнал изменений (Keep a Changelog)
├── CONTINUITY.md            ← журнал непрерывности (где мы остановились)
├── README.md                ← обычный README для людей
├── configs/
│   ├── base.yaml            ← основной конфиг (data_dir, модели, ffmpeg)
│   └── prompts/
│       └── analyze_v001.txt ← системный промпт LLM (версионируется)
├── src/callprofiler/
│   ├── config.py            ← dataclass Config + load_config()
│   ├── models.py            ← CallMetadata, Segment, Analysis
│   ├── audio/normalizer.py        ← ffmpeg + LUFS нормализация
│   ├── transcribe/whisper_runner.py ← faster-whisper large-v3 (GPU)
│   ├── diarize/
│   │   ├── pyannote_runner.py     ← pyannote 3.3.2 + ref embedding (GPU)
│   │   └── role_assigner.py       ← overlap-mapping сегмент→спикер
│   ├── analyze/
│   │   ├── llm_client.py          ← HTTP клиент llama.cpp (OpenAI API)
│   │   ├── prompt_builder.py      ← подстановка в analyze_vNNN.txt
│   │   └── response_parser.py     ← 4-уровневый robust JSON parser
│   ├── bulk/
│   │   ├── enricher.py            ← массовый LLM-анализ (bulk-enrich)
│   │   ├── loader.py              ← импорт готовых транскриптов (bulk-load)
│   │   └── name_extractor.py      ← угадывание имён из транскриптов
│   ├── db/
│   │   ├── schema.sql             ← CREATE TABLE IF NOT EXISTS
│   │   └── repository.py          ← sqlite3 напрямую, без ORM
│   ├── deliver/
│   │   ├── card_generator.py      ← caller cards ({phone}.txt для Android)
│   │   └── telegram_bot.py        ← уведомления + команды /digest /search ...
│   ├── ingest/
│   │   ├── filename_parser.py     ← 5 форматов имён файлов → CallMetadata
│   │   └── ingester.py            ← MD5 дедупликация + регистрация в БД
│   ├── pipeline/
│   │   ├── orchestrator.py        ← главный pipeline (process_call / process_batch)
│   │   └── watcher.py             ← сканирование incoming_dir + автообработка
│   └── cli/main.py                ← точка входа `python -m callprofiler`
├── tests/                   ← pytest (90 тестов, все зелёные)
└── .claude/
    └── skills/              ← доменные skills для AI-агентов
        ├── filename-parser/
        └── journal-keeper/
```

---

## 3. Обязательный рабочий процесс агента

Любая сессия AI-агента над этим репозиторием **должна**:

### 3.1. Старт сессии — чтение журналов

Прежде чем писать код или предлагать план:

1. Прочитать **`CONTINUITY.md`** — текущее состояние, на чём остановились,
   известные технические долги. Это твой briefing.
2. Прочитать последние 50-100 строк **`CHANGELOG.md`** — что было сделано
   за последние сессии, какие баги только что исправлены.
3. При архитектурных решениях — открыть **`CONSTITUTION.md`** и найти
   релевантную статью (1–18). Если твоё решение противоречит Конституции —
   это бракует PR, нужно либо менять решение, либо менять Конституцию
   с измеренным обоснованием.

### 3.2. Во время работы

- **Вертикальные срезы, а не горизонтальные слои** (CONSTITUTION 2.1).
  Не надо рефакторить «всю БД» одним PR.
- **Изоляция `user_id` во всех запросах к БД** (CONSTITUTION 2.5).
  Запрос без `WHERE user_id = ?` к таблицам `contacts/calls/analyses/promises` — баг.
- **GPU-дисциплина** (CONSTITUTION 2.4):
  Whisper + pyannote держатся в VRAM вместе; перед LLM-запросами обе выгружаются.
  Не загружай три GPU-модели одновременно.
- **Ошибки не проглатываются** (CONSTITUTION 6.4).
  Каждый шаг pipeline в try/except → `update_call_status('error', error_message)` →
  продолжить со следующим файлом. `except: pass` запрещён.
- **Оригиналы аудио неприкосновенны** (CONSTITUTION 6.1).
- **Дедупликация по MD5** (CONSTITUTION 6.2).

### 3.3. Финал сессии — запись в журналы

Перед `git commit` ОБЯЗАТЕЛЬНО:

1. Добавить запись в **`CHANGELOG.md`** в секцию `[Unreleased]` или
   `[YYYY-MM-DD]`, указав: что сделано, почему, какие тесты изменились.
2. Обновить **`CONTINUITY.md`** — где остановились, что дальше, новые
   известные ограничения.
3. Сверить изменения с `CONSTITUTION.md` (нет ли нарушений).
4. Запустить тесты.
5. Сделать коммит на ветке `claude/clone-callprofiler-repo-hL5dQ`.

> Этот процесс существует потому, что контекст AI-сессии стирается.
> Журналы — единственный способ преемственности между сессиями
> (принцип «Obsidian-like memory», обозначенный владельцем).

---

## 4. Ключевые команды

### 4.1. Разработка

```bash
# Установка зависимостей (целевая машина — Windows, системный Python)
pip install -e . --break-system-packages

# Запуск всех тестов (должно быть 90 pass)
pytest tests/ -v

# Запуск одного теста
pytest tests/test_repository.py::test_phonebook_name_overwrites_guessed_name -v

# Линт (если настроен ruff)
ruff check src/ tests/
```

### 4.2. CLI приложения

```bash
# Добавить пользователя
python -m callprofiler add-user serhio \
    --display-name "Сергей" \
    --incoming "C:\calls\audio" \
    --ref-audio "C:\pro\mbot\ref\manager.wav" \
    --sync-dir "C:\calls\sync\serhio\cards"

# Обработать один файл
python -m callprofiler process "C:\calls\audio\test.mp3" --user serhio

# Запустить watchdog (основной режим)
python -m callprofiler watch

# Массовые операции
python -m callprofiler bulk-load /path/to/transcripts --user serhio
python -m callprofiler bulk-enrich --user serhio [--limit N]
python -m callprofiler extract-names --user serhio [--dry-run]

# Отладка
python -m callprofiler status
python -m callprofiler reprocess
python -m callprofiler digest serhio --days 7
```

### 4.3. Ветка разработки

Все изменения — на ветке `claude/clone-callprofiler-repo-hL5dQ`.
Не пушить в другие ветки без явного указания владельца.

---

## 5. Стек и жёсткие зависимости (не менять без CONSTITUTION-ревизии)

| Слой         | Решение                              | Обоснование                  |
|--------------|--------------------------------------|------------------------------|
| ASR          | `faster-whisper` large-v3            | Лучшее качество русского     |
| Диаризация   | `pyannote.audio` 3.3.2 + ref embed   | Работает, замерено           |
| LLM          | `llama.cpp` (OpenAI API совместимый) | Локальность, контроль памяти |
| БД           | `sqlite3` + FTS5 (без ORM)           | Один ПК, простота            |
| Telegram     | `python-telegram-bot`                | Стандарт                     |
| GPU          | torch 2.6.0+cu124, RTX 3060 12GB     | Железо пользователя          |

**Обязательные хаки** (иначе не работает, см. CONSTITUTION 13.1):
- `torch.load` monkey-patch (`weights_only=False`)
- `use_auth_token=` (не `token=`) для pyannote 3.3.2
- `HF_TOKEN` из `configs/base.yaml`

---

## 6. Модель данных (краткая карта)

```
users (user_id PK) ──┐
                     │
  contacts (contact_id PK, user_id FK, phone_e164, display_name, guessed_name, name_confirmed)
                     │
  calls (call_id PK, user_id FK, contact_id FK nullable, source_md5 UNIQUE per user, status, direction)
    ├── transcripts (call_id FK, start_ms, end_ms, text, speaker OWNER|OTHER)
    │      └── transcripts_fts (FTS5 virtual table)
    ├── analyses (call_id FK, priority, risk_score, summary, flags JSON, feedback)
    └── promises (call_id FK, contact_id nullable, who, what, due, status)
```

**Приоритет имён контактов** (важнейшая бизнес-логика):
```
МАКСИМАЛЬНЫЙ: display_name (из имени файла = телефонная книга Android)
              + name_confirmed = 1
ВТОРИЧНЫЙ:    guessed_name (авто-извлечение из транскрипта — name_extractor.py)
              записывается только если display_name пустой
```

Подробности — в `CHANGELOG.md` 2026-04-10.

---

## 7. Агенты и skills

CallProfiler — многодоменный проект, где AI-агенту может понадобиться
специализированное знание. Мы оформляем такие знания как **skills**
в каталоге `.claude/skills/`.

### 7.1. Реализованные skills

| Skill             | Что делает                                                            | Где               |
|-------------------|-----------------------------------------------------------------------|-------------------|
| `filename-parser` | Парсинг 5 форматов имён Android-записей → `CallMetadata`              | `.claude/skills/filename-parser/SKILL.md` |
| `journal-keeper`  | Обязательный workflow записи в `CHANGELOG.md` + `CONTINUITY.md`       | `.claude/skills/journal-keeper/SKILL.md` |

### 7.2. Предлагаемые агенты/skills (к созданию по мере нужды)

> Реализуется только при измеренной потребности — принцип CONSTITUTION 2.3.
> Ниже — план команды, а не обязательство.

| Предложение               | Зачем                                                                      | Триггер к созданию                          |
|---------------------------|----------------------------------------------------------------------------|---------------------------------------------|
| `constitution-auditor`    | Проверка PR/кода на нарушение CONSTITUTION (user_id, GPU, форб. стек)      | Чаще 1 раз в неделю нарушение в PR          |
| `llm-json-surgeon`        | Ремонт обрезанного/кривого JSON из LLM (уже есть в `response_parser.py`)   | Новый формат LLM или провал парсинга > 5%   |
| `schema-migrator`         | Шаблоны SQLite миграций (паттерн `Repository._migrate()`)                  | Второй раз при добавлении колонки           |
| `gpu-discipline-checker`  | Верификация load/unload пар моделей и VRAM budget                          | OOM на RTX 3060 в batch pipeline            |
| `bulk-ops-runner`         | Агент-специалист по bulk-enrich / bulk-load / extract-names + ETA/метрики  | Регулярные прогоны на > 1000 файлов          |
| `prompt-version-manager`  | Управление версиями `analyze_vNNN.txt` + A/B-прогоны по feedback'у         | Переход на analyze_v002                     |

### 7.3. Как создать новый skill

1. Создать каталог `.claude/skills/<name>/`.
2. Написать `SKILL.md` с секциями: **Назначение**, **Когда применять**,
   **Инструкции шаг за шагом**, **Анти-паттерны**, **Ссылки на код**.
3. Сослаться на него в секции 7.1 этого файла.
4. Обязательно обновить `CHANGELOG.md` и `CONTINUITY.md`.

Skill должен быть:
- **Узко доменным** (не «как писать на Python»).
- **Self-contained** — при чтении одного файла агент может работать.
- **Привязанным к коду** через ссылки `file:line`.
- **Обновляемым**: если код меняется — SKILL.md тоже.

---

## 8. Анти-паттерны (мгновенный red flag)

- Новый зависимость без записи «замерено — нужно» в `RISKS.md` / `CONTINUITY.md`.
- SQL-запрос к `contacts/calls/analyses/promises` без `WHERE user_id = ?`.
- `except: pass` или `except Exception: pass` без логгера.
- Модификация файла в `audio/originals/`.
- Загрузка Whisper и LLM одновременно в VRAM.
- Новые миграции БД прямым `ALTER TABLE` в обход `Repository._migrate()`.
- Вывод через `print()` вместо `logger` в production-модулях.
- Добавление Docker / Redis / PostgreSQL / LangChain / WhisperX / ECAPA.
- Коммит без обновления `CHANGELOG.md` и `CONTINUITY.md`.
- `git push --force` без явного разрешения владельца.

---

## 9. Полезные ссылки

- Полный план разработки: `CLAUDE.md` (15 шагов)
- Архитектурные правила: `CONSTITUTION.md` (18 статей)
- История изменений: `CHANGELOG.md`
- Текущее состояние: `CONTINUITY.md`
- Прототип, из которого мигрировали: `reference_batch_asr.py`
- Конфиг: `configs/base.yaml`, системные промпты: `configs/prompts/`

---

**Принцип команды:** работающий код важнее идеальной архитектуры, но не
важнее конституции. Конституцию можно менять — но только с замером,
а не «потому что красивее».

```

## CLAUDE.md
```text
# CallProfiler

Local multi-user phone call analysis system. Records → transcripts → LLM structured analysis → Telegram + Android overlay.

## Mission

**System thinks a lot — shows little.** Heavy analysis offline, user sees only short actionable digests.

## Constraints (never violate)

- 100% local. No cloud LLM, no SaaS, no subscriptions.
- Windows + system Python. No Docker/Redis/Celery.
- LLM: `llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" -ngl 99 -c 16384 --host 127.0.0.1 --port 8080` — OpenAI-compatible API at `http://127.0.0.1:8080/v1/chat/completions`. NOT Ollama.
- GPU sequential: Whisper+pyannote together (4.5GB), unload before LLM (10GB).
- Every DB query MUST filter by `user_id`.
- Never hardcode tokens — `os.environ.get()` only.
- Never swallow errors — log + save to DB + continue.

## Session Protocol

```
IF session_start:
  → read CONTINUITY.md + CHANGELOG.md
  → output: "Last state: … / Next: …"

IF code_generated OR schema_changed:
  → update CONTINUITY.md immediately
  → update CHANGELOG.md
  → run tests

IF bug_fixed:
  → write to .claude/rules/bugs.md
  → add regression test

IF architectural_decision:
  → write to .claude/rules/decisions.md
```

## Before Writing Code

THINK (what files affected, what depends on them) → PLAN (3-5 steps) → IMPLEMENT → VERIFY (run tests) → LOG (update CONTINUITY.md)

## Commands

```bash
set PYTHONPATH=C:\pro\callprofiler\src
python -m callprofiler <command>          # CLI entry point
python -m pytest tests/ -v               # Tests
git add . && git commit -m "msg" && git push origin main
```

## Required Hacks

```python
# torch 2.6 — in any module loading pyannote
import torch; _orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, "weights_only": kw.get("weights_only", False)})

# pyannote 3.3.2 — use_auth_token=, NOT token=
```

## Key Paths

```
Project:     C:\pro\callprofiler\          DB:    D:\calls\data\db\callprofiler.db
Audio:       D:\calls\audio                Transcripts: D:\calls\out (18K .txt)
Ref voice:   C:\pro\mbot\ref\manager.wav   Prototype:   reference_batch_asr.py
```

## Transcript Format

`[me]` = owner (Сергей Медведев), `[s2]` = other speaker. Roles may be swapped — LLM determines by context. "Сергей/Серёжа/Медведев" = ALWAYS owner.

## Working Style

- Vertical slice first (end-to-end before broad scaffolding).
- Reuse `reference_batch_asr.py` logic — refactor, don't rewrite.
- Events + aggregates, not ad-hoc queries.
- Precompute after each call (contact_summary → card → ready for next incoming).
- Small testable steps. One commit per logical change.

## Progressive Disclosure

IF referenced @file does not exist → ignore, do not infer its contents.

```
Architecture & pipeline:       @ARCHITECTURE_v4.md
Strategy & phases:             @STRATEGIC_PLAN_v4.md
Constitution & constraints:    @CONSTITUTION.md
Agent coding rules:            @AGENTS.md
LLM prompt template:           @configs/prompts/analyze_v001.txt
Working prototype:             @reference_batch_asr.py
DB rules:                      @.claude/rules/db.md
Pipeline rules:                @.claude/rules/pipeline.md
LLM analysis rules:            @.claude/rules/llm.md
Known bugs & fixes:            @.claude/rules/bugs.md
Architectural decisions log:   @.claude/rules/decisions.md
Narrative journal architecture:@.claude/rules/narrative-journal.md
Biography module overview:     @src/callprofiler/biography/CLAUDE.md
Biography data rules:          @.claude/rules/biography-data.md
Biography style canon:         @.claude/rules/biography-style.md
Biography prompt contracts:    @.claude/rules/biography-prompts.md
Knowledge graph rules:         @.claude/rules/graph.md
```

## Prohibited

- Cloud/SaaS dependencies
- ORM (use sqlite3 directly)
- Ollama API (use llama-server)
- Auto-merge contacts
- Verbose user-facing output
- User-facing output longer than 300 chars or more than 3 facts per item
- Adding components not in current phase plan

## Git Push Authorization

**Push to: `main` branch (not feature branches)**

All commits and pushes should go directly to `main`. Feature branches are not used for this repository.

```bash
git push origin main
```

```

## CONSTITUTION.md
```text
# CONSTITUTION.md — Конституция проекта CallProfiler

**Статус:** merge-blocking. Код, архитектура или практика, противоречащие этому документу, не принимаются.

---

## Статья 1. Назначение системы

CallProfiler — локальная мультипользовательская система обработки записей телефонных разговоров.

Цепочка: телефон записывает → ПК обрабатывает → пользователь получает дайджест в Telegram и видит контекст при входящем звонке на экране Android.

Система обслуживает нескольких пользователей (владельцев телефонов) с полной изоляцией данных между ними.

---

## Статья 2. Фундаментальные принципы

### 2.1. Вертикальный срез, а не горизонтальные слои

Каждая фаза разработки даёт работающий сквозной результат: от аудиофайла до доставки пользователю. Запрещено строить «весь транскрибатор», потом «всю БД», потом «весь LLM».

### 2.2. Работающий код важнее идеальной архитектуры

Рабочий прототип с грубой диаризацией ценнее идеальной диаризации без pipeline. Улучшения — только после измерения проблемы на реальных данных.

### 2.3. Сложность оправдывается только измеренной проблемой

Новый компонент, зависимость или абстракция добавляется только когда:
- измерена конкретная проблема, которую текущее решение не закрывает;
- записан замер (что, где, насколько плохо);
- предложено решение с минимальной дополнительной сложностью.

«Может понадобиться потом» — не основание.

### 2.4. GPU — узкое горлышко

RTX 3060 12GB. Две модели одновременно в VRAM запрещены, кроме пар, которые помещаются вместе (Whisper ~3GB + pyannote ~1.5GB = OK). Перед загрузкой LLM (~10GB) обязательна выгрузка всех остальных моделей.

### 2.5. Данные пользователей изолированы

Каждый запрос к БД, каждая операция с файлами фильтруется по `user_id`. Контакт, звонок, анализ без `user_id` — баг. Один номер телефона у двух пользователей — два разных контакта.

---

## Статья 3. Что система делает

- Принимает аудиозаписи телефонных звонков от нескольких пользователей.
- Транскрибирует русскую речь (faster-whisper large-v3).
- Разделяет на двух спикеров (pyannote + ref embedding → OWNER / OTHER).
- Анализирует локальной LLM (Ollama): саммари, priority, risk, action items, обещания.
- Генерирует caller cards ({phone}.txt) для overlay на Android.
- Отправляет дайджест в Telegram.
- Хранит всё в SQLite с полнотекстовым поиском.

---

## Статья 4. Что система НЕ делает

Следующее запрещено в текущей и ближайших фазах:

| Запрещено | Почему |
|-----------|--------|
| Более двух спикеров | Нет бизнес-задачи |
| Real-time / стриминг | Задача — пост-обработка записей |
| Облачные ASR/LLM | Требование локальности |
| Docker | Один ПК, один процесс, нулевая выгода |
| Redis / Celery / брокеры | SQLite-статусы достаточны |
| PostgreSQL | До измеренных проблем с SQLite |
| Neo4j / ChromaDB / LangChain | Не раньше Фазы 5, по замерам |
| Микросервисы | Одна машина, один pipeline |
| WhisperX word alignment | Для LLM-анализа сегменты достаточны |
| ECAPA-TDNN enrollment | pyannote + ref embedding уже работает |
| Gold-set 30 звонков | Обратная связь через Telegram-кнопки практичнее |
| Своё Android-приложение | MacroDroid + txt решают задачу |
| Schema versioning на JSON | Достаточно prompt_version в analyses |

Добавление любого из этих компонентов требует: замер проблемы → запись в RISKS.md → обновление этой Конституции.

---

## Статья 5. Технологический стек

| Компонент | Решение | Замена допускается при |
|-----------|---------|----------------------|
| ASR | faster-whisper large-v3 | WER > 25% на реальных звонках |
| Диаризация | pyannote 3.3.2 + ref embedding | Ошибка ролей > 15% |
| LLM | Ollama + Qwen3.5-9B.Q8_0 | Качество JSON < 70% |
| БД | SQLite + FTS5 | Contention при > 100K записей |
| Бот | python-telegram-bot | — |
| Overlay | MacroDroid + FolderSync + .txt | Не работает на целевом Android |
| Язык | Python 3.10+ | Никогда |
| OS | Windows (cmd, не WSL) | — |

---

## Статья 6. Правила работы с данными

### 6.1. Оригиналы неприкосновенны

Исходные аудиофайлы копируются в `audio/originals/` и никогда не модифицируются, не перекодируются на месте, не удаляются автоматически.

### 6.2. Дедупликация по MD5

Перед обработкой вычисляется MD5-хеш оригинала. Если хеш уже есть для этого `user_id` — файл пропускается.

### 6.3. Каждый звонок имеет статус

```
new → transcribing → diarizing → analyzing → done
               ↘          ↘          ↘
                error      error      error
```

Звонок без статуса — невалиден. Переход в `error` сохраняет причину в `error_message`. Максимум 3 ретрая.

### 6.4. Ошибки не проглатываются

Каждый шаг pipeline обёрнут в try/except. При ошибке: логирование, запись в БД (status=error, error_message), переход к следующему файлу. Запрещено: голый except без записи, silent fail, потеря стектрейса.

---

## Статья 7. Структура хранения

```
data/
├── users/{user_id}/
│   ├── incoming/              ← FolderSync кладёт записи с телефона
│   ├── audio/originals/       ← копии оригиналов (read-only)
│   ├── audio/normalized/      ← WAV 16kHz mono
│   └── sync/cards/            → FolderSync забирает карточки на телефон
├── db/callprofiler.db         ← одна БД на всех
├── ref/                       ← эталоны голосов
│   ├── {user_id}.wav
└── logs/pipeline.log
```

Правила:
- `data/` — в `.gitignore`.
- Одна БД, изоляция через `user_id` в каждой таблице.
- Cleanup аудио — только ручной, по решению оператора.

---

## Статья 8. Мультипользовательская модель

### 8.1. Определения

**Пользователь (user)** — владелец телефона, чьи звонки записываются. Не путать с «пользователем Telegram» или «администратором».

### 8.2. Изоляция

- Каждый пользователь: своя incoming-папка, своя sync-папка, свой эталон голоса, свой Telegram chat_id.
- Один Telegram-бот на всех. Различает по `chat_id`.
- Незарегистрированные chat_id — игнорируются.
- Пользователи добавляются через CLI (`add-user`), не через Telegram.

### 8.3. Это НЕ SaaS

Нет аутентификации, нет ролей, нет OAuth. Это несколько профилей на одной машине, как учётные записи в OS.

---

## Статья 9. Pipeline

### 9.1. Порядок шагов

```
1. Ingest     — парсинг имени файла, MD5, дедупликация, контакт, запись call
2. Normalize  — ffmpeg → WAV 16kHz mono
3. Transcribe — faster-whisper (GPU)
4. Diarize    — pyannote + ref embedding (GPU) → OWNER/OTHER
5. Analyze    — Ollama LLM (GPU, после выгрузки Whisper+pyannote)
6. Deliver    — карточка + Telegram
```

### 9.2. Batch-оптимизация

Загрузить Whisper + pyannote один раз → обработать все pending файлы (шаги 1-4) → выгрузить → загрузить LLM → обработать все (шаг 5) → доставить (шаг 6).

### 9.3. GPU-дисциплина

```
Whisper (~3GB) + pyannote (~1.5GB) = ~4.5GB  → помещаются вместе → OK
Ollama Qwen3.5-9B.Q8_0 (~10GB)                    → только один → выгрузить остальное
```

Перед загрузкой LLM обязательно:
```python
del whisper_model
del pyannote_pipeline
del inference
gc.collect()
torch.cuda.empty_cache()
```

---

## Статья 10. Caller Cards (overlay)

### 10.1. Принцип

ПК генерирует `{phone_e164}.txt` (≤500 символов) → FolderSync синхронизирует на телефон → MacroDroid при входящем звонке читает файл → показывает overlay.

### 10.2. Формат карточки

```
{display_name} | {категория}
Последний: {дата} | Звонков: {count} | Risk: {avg_risk}
─────────────────────────
{summary последнего звонка, 2-3 строки}
─────────────────────────
Обещания: {открытые promises}
Actions: {незакрытые action items}
```

### 10.3. Обновление

Карточка перезаписывается после каждого обработанного звонка с этого номера. К следующему входящему — уже актуальна.

### 10.4. Offline

Файлы уже на телефоне. Показ overlay не зависит от сети в момент звонка.

---

## Статья 11. Telegram-бот

### 11.1. Один бот, много пользователей

Каждая команда определяет `user_id` по `chat_id`. Все запросы фильтруются по `user_id`.

### 11.2. Автоматические сообщения

После обработки каждого звонка: саммари + priority + action items + кнопки [OK]/[Неточно].

### 11.3. Команды

| Команда | Действие |
|---------|----------|
| `/digest [N]` | Топ по priority за N дней |
| `/search текст` | FTS5-поиск по транскриптам |
| `/contact +7...` | Карточка контакта |
| `/promises` | Открытые обещания |
| `/status` | Состояние очереди |

---

## Статья 12. Промпты LLM

### 12.1. Версионирование

Каждый промпт — файл `configs/prompts/analyze_vNNN.txt`. Поле `prompt_version` в таблице `analyses` фиксирует, какая версия дала результат.

### 12.2. Один промпт → один JSON

Не агентная декомпозиция. Multi-agent — только если один промпт перестаёт справляться (измерить на 50+ звонках, записать замер).

### 12.3. Контекст

Начиная с Фазы 3: промпт получает саммари последних 5 звонков с этим контактом.

---

## Статья 13. Миграция из batch_asr.py

Текущий `batch_asr.py` — единственный работающий код. Его логика ASR и диаризации переносится без изменений:

```
batch_asr.py                    →  callprofiler/
─────────────────────────────────────────────────
convert_to_wav()                →  audio/normalizer.py
load_whisper(), transcribe()    →  transcribe/whisper_runner.py
load_pyannote(), diarize()      →  diarize/pyannote_runner.py
get_embedding()                 →  diarize/pyannote_runner.py
build_ref_embedding()           →  diarize/pyannote_runner.py
assign_speakers()               →  diarize/role_assigner.py
save_txt()                      →  output/transcript_writer.py (опционально)
process_file()                  →  pipeline/orchestrator.py
collect_files()                 →  ingest/file_scanner.py → watcher.py
```

**Правило:** при разрезании не менять логику ASR/diarize. Она работает. Менять только обвязку.

### 13.1. Обязательные хаки из batch_asr.py

```python
# torch 2.6 weights_only fix — ОБЯЗАТЕЛЕН
import torch as _torch
_original_load = _torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_load(*args, **kwargs)
_torch.load = _patched_load
```

```python
# pyannote 3.3.2 — использовать use_auth_token=, НЕ token=
Model.from_pretrained("pyannote/embedding", use_auth_token=HF_TOKEN)
Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=HF_TOKEN)
```

---

## Статья 14. Правила разработки

### 14.1. Среда

- Python 3.10+ системный (без venv).
- `pip install X --break-system-packages` при необходимости.
- Запуск: `python -m callprofiler <command>` из cmd.
- Кодировка: UTF-8 везде.

### 14.2. Секреты

Токены (HF_TOKEN, TELEGRAM_TOKEN) — только через переменные окружения или `.env`. Никогда не в коде, не в YAML, не в git.

### 14.3. Тесты

- `filename_parser` — минимум 15 кейсов.
- `repository` — CRUD + изоляция user_id.
- `response_parser` — валидный JSON, невалидный JSON, markdown-обёртки.
- Каждый модуль должен работать автономно.

### 14.4. Git

- Репозиторий: `https://github.com/SergioTheFirst/callprofiler.git`
- Ветка: `main`.
- Коммит после каждого завершённого шага.
- `.gitignore`: `__pycache__/`, `*.pyc`, `data/`, `.env`.

---

## Статья 15. Фазы развития

| Фаза | Цель | Критерий завершения |
|------|------|-------------------|
| 0 | Разведка: замеры моделей | BENCHMARKS.md заполнен |
| 1 | Сквозной pipeline | Файл → Telegram за 3-5 мин, 10 файлов подряд |
| 2 | Стабилизация + 2-й пользователь | Неделя без вмешательства, изоляция OK |
| 3 | Контекст и качество | Обещания трекаются, FTS5 работает |
| 4 | Веб-интерфейс + API | FastAPI показывает историю звонков |
| 5 | Продвинутое | По замерам: vectors, ECAPA, multi-agent |

---

## Статья 16. Условия пересмотра архитектуры

Архитектура пересматривается только при измеренном доказательстве:

| Триггер | Действие |
|---------|----------|
| Ошибка ролей > 15% на моно | Внедрить ECAPA-TDNN |
| SQLite тормозит при > 100K записей | PostgreSQL |
| Один промпт < 70% качества | Multi-agent |
| FTS5 не хватает | Векторный поиск |
| MacroDroid не работает на целевом Android | Своё приложение или notification fallback |
| faster-whisper WER > 25% | WhisperX или другая модель |

До появления измерения — текущая архитектура не меняется.

---

## Статья 17. Антипаттерны

Следующее запрещено:

- Хранить только текст без таймкодов и метаданных.
- Смешивать LLM-интерпретацию с сырым транскриптом в одних полях.
- Проглатывать ошибки без записи в БД.
- Ретраить без счётчика и лога.
- Удалять оригинальные аудиофайлы.
- Добавлять зависимость без измеренной проблемы.
- Менять логику ASR/diarize из batch_asr.py без замера «до/после».
- Пушить секреты в git.
- Запускать две GPU-модели, которые не помещаются вместе.
- Обращаться к данным без фильтра по `user_id`.

---

## Статья 18. Порядок внесения изменений

1. Изменение в Конституции требует: описание проблемы → замер → решение → обновление этого файла.
2. Код, противоречащий Конституции, не мержится.
3. Исключения фиксируются в RISKS.md с причиной, датой и планом отката.

---

## Статья 19. Память проекта и сессионный протокол

### 19.1. Принцип: непрерывность знаний

Любой разработчик или AI-агент может открыть репозиторий и мгновенно понять:
- что уже сделано;
- что в работе;
- что делать дальше.

Это требует **обязательного ведения трёх журналов**:

### 19.2. CONTINUITY.md — журнал непрерывности

Обновляется **после каждой рабочей сессии**.

Структура:
```
# CONTINUITY.md

## Status
DONE: X  
NOW: Y  
NEXT: Z  
BLOCKERS: список

## Текущое состояние: YYYY-MM-DD HH:MM (краткий заголовок)

### Что сделано в этой сессии
- Commit hash
- Количество строк код
- Перечисление функций/файлов
- Результаты тестов

### Что сделано в предыдущей сессии
- (краткое резюме)
```

**Правило:** перед `git push` всегда обновить CONTINUITY.md.

### 19.3. CHANGELOG.md — история всех изменений

Форматируется по [Keep a Changelog](https://keepachangelog.com/ru/).

Структура:
```
## [Unreleased]

### Added — Title (YYYY-MM-DD)
- `file.py`: что добавлено
- `file.py`: что изменено

### Fixed — Title (YYYY-MM-DD)
- Bug description → fix
```

**Правило:** каждое значимое изменение (коммит с кодом, а не только docs) добавляется в Unreleased → Added/Fixed/Changed/Removed.

### 19.4. Сессионный протокол

При начале сессии:
```
→ прочитать CONTINUITY.md (90 строк, 30 сек)
→ определить DONE/NOW/NEXT/BLOCKERS
→ вывести в консоль: "Last state: [NOW] / Next: [NEXT]"
```

При завершении сессии:
```
→ обновить CONTINUITY.md (Статус, Текущее состояние, Что сделано)
→ обновить CHANGELOG.md (Added/Fixed для каждого коммита)
→ запустить тесты (pytest)
→ git add CONTINUITY.md CHANGELOG.md
→ git commit "session: update journals"
→ git push origin main
```

**Исключение:** если сессия > 4 часов без progress → сохранить state немедленно (не ждать конца сессии).

### 19.5. Минимальное содержимое CONTINUITY.md

```markdown
## Status
DONE: [что завершено в этой сессии или недавних]
NOW: [что выполняется сейчас]
NEXT: [что делать после текущей сессии]
BLOCKERS: [чего ждём, на что не можем влиять]

## Текущое состояние: YYYY-MM-DD HH:MM (название)

### Что сделано в этой сессии (YYYY-MM-DD — тема)

[описание изменений, файлы, коммиты]

**Commit:** `hash` (краткое сообщение)  
**Push:** ✅ hash → origin/main  
**Тесты:** [кол-во passed/failed]

**Следующий шаг:** [что дальше]
```

### 19.6. Обязательность

- **Нарушение этой статьи = нарушение Конституции.**
- Каждый коммит в main должен быть сопровожден обновлением CONTINUITY.md.
- Пропуск обновления журналов = потеря контекста для следующей сессии = нарушение Статьи 19.1.

```

## README.md
```text
# CallProfiler

**Локальная система обработки телефонных звонков в реальном времени** с автоматическим распознаванием речи, идентификацией говорящего и отправкой резюме в Telegram.

> 📱 Запись → 🤖 Обработка (локально) → 💬 Дайджест → 📲 Telegram + Android overlay

---

## 🎯 Назначение

CallProfiler обрабатывает звонки, полученные на локальной машине Windows, и:

1. **Распознаёт речь** (Whisper + faster-whisper) в текст с временными метками
2. **Идентифицирует говорящих** (pyannote.audio 3.3.2) с разделением по `user_id`
3. **Нормализует аудио** (EBU R128) перед обработкой
4. **Сохраняет данные** в SQLite с полнотекстовым поиском (FTS5)
5. **Генерирует дайджесты** и отправляет в Telegram
6. **Синхронизирует оверлей** на Android (через FolderSync + MacroDroid)

Результат: **структурированный архив звонков с быстрым поиском и мобильным доступом**.

---

## ⚙️ Системные требования

| Параметр | Значение |
|----------|----------|
| **ОС** | Windows 10/11 |
| **GPU** | RTX 3060 12GB (или совместимый CUDA-чип) |
| **CUDA** | 12.4+ |
| **PyTorch** | 2.6.0+cu124 |
| **Python** | 3.10+ |
| **Свободное место** | ≥50 GB (модели + архив) |

### Модели (автозагрузка)

- **Whisper**: ~3 GB (faster-whisper)
- **pyannote.audio**: ~1.5 GB (speaker diarization)
- **Ollama Qwen 14B Q4**: ~10 GB (опционально, для обобщений)

---

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/SergioTheFirst/callprofiler.git
cd callprofiler
```

### 2. Зависимости

```bash
pip install --break-system-packages \
    torch==2.6.0+cu124 \
    torchaudio \
    faster-whisper \
    pyannote.audio==3.3.2 \
    torch-audiomentations \
    librosa \
    numpy \
    requests \
    python-telegram-bot
```

### 3. Авторизация pyannote

pyannote требует `use_auth_token` (не `token`):

```python
from pyannote.audio import Pipeline
pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token="YOUR_HUGGINGFACE_TOKEN"  # ← важно!
)
```

Получить токен: https://huggingface.co/settings/tokens

### 4. Переменные окружения

```bash
# .env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
LLM_SERVER_URL=http://127.0.0.1:8080  # Опционально (llama-server)
```

---

## 📋 Архитектура

```
callprofiler/
├── src/
│   ├── audio_processor.py       # Нормализация (EBU R128), сегментация
│   ├── speech_recognizer.py     # Whisper + временные метки
│   ├── speaker_diarizer.py      # pyannote.audio, идентификация
│   ├── database.py              # SQLite + FTS5, multi-user isolation
│   ├── telegram_notifier.py     # Отправка дайджестов
│   └── llm_adapter.py           # OpenAI-совместимый LLM (Ollama/llama-server)
├── config/
│   ├── config.json              # Параметры: device, batch_size, output_paths
│   └── users.json               # Маппинг speaker_id → user_id
├── models/
│   ├── whisper-model            # Кэш Whisper
│   └── pyannote-checkpoint      # Кэш pyannote
├── archive/
│   └── calls_db.sqlite          # База звонков (FTS5)
├── documents/
│   ├── STRATEGIC_PLAN_v3.md     # Долгосрочное видение
│   ├── ARCHITECTURE_v3.md       # Технический дизайн
│   ├── DEVELOPMENT_PLAN.md      # 15-step implementation plan
│   ├── CONSTITUTION.md          # 18-article merge-blocking rules
│   └── AGENTS.md                # AI-агенты для обработки
└── tests/
    └── test_pipeline.py         # Smoke tests (18/18 passing)
```

---

## 🔧 Использование

### Базовый pipeline

```python
from src.audio_processor import AudioProcessor
from src.speech_recognizer import SpeechRecognizer
from src.speaker_diarizer import SpeakerDiarizer
from src.database import CallDatabase

# 1. Загрузить аудио
audio_processor = AudioProcessor()
normalized_audio = audio_processor.normalize_ebu_r128("path/to/call.wav")

# 2. Распознать речь
recognizer = SpeechRecognizer()
transcript = recognizer.transcribe(normalized_audio)  
# → [{'start': 0.5, 'end': 3.2, 'text': 'Привет', 'speaker': 'speaker_0'}, ...]

# 3. Идентифицировать говорящих
diarizer = SpeakerDiarizer()
speakers = diarizer.diarize(normalized_audio, transcript)
# → {'speaker_0': 'user_123', 'speaker_1': 'user_456'}

# 4. Сохранить в БД
db = CallDatabase("archive/calls_db.sqlite")
db.save_call(
    call_id="call_20250409_120000",
    user_id="user_123",
    transcript=transcript,
    speakers=speakers,
    audio_duration=125.5
)

# 5. Поиск
results = db.full_text_search("важное слово", user_id="user_123")
```

### Отправка в Telegram

```python
from src.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier(token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)

digest = {
    "call_id": "call_20250409_120000",
    "duration": "2:05",
    "speakers": ["Иван", "Петя"],
    "summary": "Обсудили квартальный план",
    "key_points": ["Deadline 30 апреля", "Нужна презентация"]
}

notifier.send_digest(digest)
```

### LLM-адаптер (опционально)

Для обобщений используется **llama-server** (совместимо с OpenAI API):

```bash
# Запуск локального LLM (Qwen 3.5 9B)
llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" \
  -ngl 99 -c 16384 --host 127.0.0.1 --port 8080
```

```python
from src.llm_adapter import LLMAdapter

llm = LLMAdapter(base_url="http://127.0.0.1:8080/v1")
summary = llm.summarize_transcript(transcript)
```

---

## 🗄️ База данных

### Схема SQLite

```sql
CREATE TABLE calls (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration REAL,
    transcript TEXT,
    speakers JSON,
    metadata JSON
);

CREATE VIRTUAL TABLE calls_fts USING fts5(
    id UNINDEXED,
    user_id UNINDEXED,
    transcript,
    content=calls,
    content_rowid=rowid
);
```

### Изоляция по user_id

Все запросы **обязательно** фильтруют по `user_id` — исключена утечка данных между пользователями:

```python
db.search("текст", user_id="user_123")  # ← Безопасно
db.search("текст")                       # ✗ Ошибка: user_id не указан
```

---

## 🚨 Критические особенности

### ⚠️ torch.load()

**Проблема**: pyannote требует `weights_only=False` при загрузке чекпоинтов.

```python
# Неправильно (вызывает ошибку):
checkpoint = torch.load("model.pt")

# Правильно:
checkpoint = torch.load("model.pt", weights_only=False)
```

### ⚠️ pyannote токен

**Проблема**: параметр `token=` устарел.

```python
# Неправильно:
Pipeline.from_pretrained(..., token="hf_...")

# Правильно:
Pipeline.from_pretrained(..., use_auth_token="hf_...")
```

### ⚠️ Выгрузка моделей перед LLM

Whisper (~3GB) + pyannote (~1.5GB) занимают GPU память. Перед запуском Ollama Qwen 14B (~10GB) нужна очистка:

```python
# После обработки звонка
del recognizer, diarizer
torch.cuda.empty_cache()

# Теперь безопасно запустить LLM
llm = LLMAdapter(...)
```

### ✅ --break-system-packages

На Windows 10/11 без venv нужен флаг:

```bash
pip install --break-system-packages torch faster-whisper pyannote.audio
```

---

## 📱 Мобильная интеграция

### Android overlay (MacroDroid + FolderSync)

1. **FolderSync** синхронизирует `archive/` → Android
2. **MacroDroid** читает `.txt` файлы (результаты) и показывает overlay при входящем звонке
3. CallProfiler пишет в `archive/pending_overlay/{caller_id}.txt`

```
archive/
├── calls_db.sqlite
├── transcripts/
│   ├── call_20250409_120000.json
│   └── call_20250409_120100.json
└── pending_overlay/
    ├── +71234567890.txt          ← Появляется перед звонком
    ├── +71234567891.txt
    └── ...
```

---

## 📊 Документация проекта

| Документ | Описание |
|----------|---------|
| **STRATEGIC_PLAN_v3.md** | Долгосрочное видение: масштабирование, новые источники, интеграции |
| **ARCHITECTURE_v3.md** | Полный технический дизайн: компоненты, потоки данных, обработка ошибок |
| **DEVELOPMENT_PLAN.md** | 15-шаговый план реализации (текущий статус: Step 5 завершён) |
| **CONSTITUTION.md** | 18 статей merge-blocking: качество кода, testing, документация |
| **AGENTS.md** | AI-агенты для автоматизации (анализ, категоризация, поиск паттернов) |

---

## ✅ Тестирование

### Smoke tests (18/18 passing)

```bash
python tests/test_pipeline.py
```

Покрытие:
- ✓ Нормализация аудио (EBU R128)
- ✓ Распознавание речи (Whisper)
- ✓ Дарваризация (pyannote)
- ✓ Сохранение в БД
- ✓ Поиск (FTS5)
- ✓ Отправка в Telegram
- ✓ LLM-адаптер

---

## 🔒 Безопасность

- ✓ Изоляция данных по `user_id` (multi-user safe)
- ✓ Локальная обработка (нет передачи в облако)
- ✓ Шифрование Telegram токена в `.env`
- ✓ HTTPS для HuggingFace API

---

## 📈 Производительность

| Операция | Время | GPU |
|----------|-------|-----|
| Нормализация 10 мин аудио | 5 сек | CPU |
| Распознавание (Whisper) | 2-3x реальное время | RTX 3060 |
| Дарваризация (pyannote) | 1-2x реальное время | RTX 3060 |
| LLM-обобщение | зависит от длины | Ollama Qwen |

---

## 🐛 Известные проблемы

| Проблема | Решение |
|----------|---------|
| `RuntimeError: Model not found` (pyannote) | Установить `use_auth_token` с валидным HF токеном |
| CUDA out of memory при 2+ параллельных звонках | Использовать `--break-system-packages`, выгружать модели после каждого звонка |
| Telegram сообщения не отправляются | Проверить `TELEGRAM_BOT_TOKEN`, интернет-соединение |
| FTS5 поиск очень медленный на >10k записях | Добавить индексы: `CREATE INDEX idx_user_id ON calls(user_id)` |

---

## 🤝 Контрибьютинг

Любые PR должны соответствовать **CONSTITUTION.md** (18 статей). Ключевые требования:

- [ ] Код покрыт тестами
- [ ] Документация актуальна
- [ ] Совместимость с Python 3.10+, PyTorch 2.6.0+
- [ ] Изоляция по `user_id` (multi-user safe)
- [ ] Нет нарушений CONSTITUTION.md

---

## 📄 Лицензия

MIT License. Используй свободно, но указывай авторство.

---

## 👤 Автор

**Sergio** (@SergioTheFirst)  
GitHub: https://github.com/SergioTheFirst  
CallProfiler Repository: https://github.com/SergioTheFirst/callprofiler

---

## 📚 Ссылки

- [PyTorch + CUDA Setup](https://pytorch.org/get-started/locally/)
- [faster-whisper docs](https://github.com/guillaumekln/faster-whisper)
- [pyannote.audio](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [llama.cpp server](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md)

---

**Последнее обновление**: Апрель 2026  
**Статус**: Production Ready (Phase 1 complete, Step 5/15)

```

## ARCHITECTURE_v4.md
```text
# CallProfiler — Архитектура v4

## Изменения относительно v3

- Добавлена классификация звонков (call_type)
- Добавлена таблица contact_summaries (materialized aggregate)
- Структурированный формат карточки overlay
- Hook-фраза в промпте LLM
- Глобальный risk_score по контакту
- Отвергнуты: Event Store, NeMo, LLM Role Correction, USB-буфер

---

## Pipeline (обновлённый)

```
[Аудиофайл / .txt файл]
    │
    ▼
[1. Ingest] → parse filename, MD5, contact, call record
    │
    ▼
[2. Normalize] → ffmpeg WAV 16kHz mono (только для аудио)
    │
    ▼
[3. Transcribe] → faster-whisper large-v3 (GPU)
    │
    ▼
[4. Diarize] → pyannote + ref embedding → OWNER/OTHER
    │
    ▼
[5. Classify] → NEW: определить call_type
    │           short (<50 символов) → skip LLM, автозаполнение
    │           остальные → продолжить
    │
    ▼
[6. LLM Analyze] → llama-server Qwen3.5-9B
    │               Выход: summary, priority, risk, bs_score,
    │               action_items, promises, hook, call_type,
    │               contact_name_guess, people, companies, amounts
    │
    ▼
[7. Aggregate] → NEW: пересчитать contact_summary
    │             global_risk, open_promises, hook, advice
    │
    ▼
[8. Generate Card] → CallNotes/{phone}.txt (≤512 байт)
    │                 Структурированный формат
    │
    ▼
[9. Deliver] → Telegram + FolderSync → телефон
```

## Классификация звонков (шаг 5)

**До LLM (по длине текста):**
```
< 50 символов → call_type = 'short', пропустить LLM
< 200 символов → подать в LLM с пометкой "короткий звонок"
≥ 200 символов → полный анализ
```

**LLM определяет (в JSON ответе):**
```
call_type: business | personal | smalltalk | spam | unknown
```

**Влияние на агрегаты:**
```
business  → вес 1.0 в contact_summary
personal  → вес 0.7
smalltalk → вес 0.1 (только personal_facts)
short     → вес 0.0 (не влияет)
spam      → вес 0.0
```

## contact_summary (materialized aggregate)

Пересчитывается после каждого обработанного звонка.

```
Алгоритм пересчёта contact_summary(contact_id):

1. Выбрать все analyses для этого контакта
2. Отфильтровать: исключить short и spam
3. global_risk = weighted_avg(risk_score, weight=call_type_weight)
   с decay: свежие звонки важнее старых (half-life = 90 дней)
4. avg_bs_score = weighted_avg(bs_score) аналогично
5. open_promises = все promises где status='open'
6. open_debts = promises с суммами (amounts не пустой)
7. personal_facts = key_topics из smalltalk звонков (последние 5)
8. top_hook = hook из последнего business-звонка
   Если нет business → hook из последнего personal
   Если нет ничего → "Нет значимой истории"
9. advice = генерируется по правилам:
   - risk > 70 → "Говори первым. Фиксируй договорённости."
   - bs_score > 60 → "Осторожно: частые размытые обещания."
   - open_debts не пуст → "Начни с долга."
   - иначе → "Нейтральный контакт."
10. contact_role = contact_company_guess из последнего analysis
11. Записать в contact_summaries
```

## Формат карточки overlay

```
header: {display_name или guessed_name} — {contact_role}
risk: {global_risk} {🔴|🟡|🟢}
hook: {top_hook}
bullet1: {open_debts[0] или open_promises[0]}
bullet2: {contradictions или следующий promise}
bullet3: {personal_facts[0] или пусто}
advice: {advice}
```

Правила цвета risk:
- 🔴 risk ≥ 70
- 🟡 30 ≤ risk < 70
- 🟢 risk < 30

Если контакт новый (0 звонков с анализом):
```
header: Неизвестный ({phone}) — новый
risk: — ⚪
hook: Первый звонок. Нет истории.
advice: Слушай внимательно.
```

## Обновлённый промпт LLM

Добавлены поля к текущему промпту:

```json
{
  "call_type": "business|personal|smalltalk|spam",
  "hook": "одна фраза-напоминание для следующего звонка",
  "contradictions": ["противоречия с предыдущими звонками"],
  "debts": [{"who": "Me|S2", "amount": "сумма", "deadline": "дата"}]
}
```

## Модуль summary_builder.py

```
src/callprofiler/aggregate/
├── __init__.py
└── summary_builder.py

class SummaryBuilder:
    def __init__(self, repo: Repository)

    def rebuild_contact(self, contact_id: int) → None
        """Пересчитать contact_summary для одного контакта"""

    def rebuild_all(self, user_id: str) → None
        """Пересчитать все contact_summaries для пользователя"""

    def generate_card(self, contact_id: int) → str
        """Сгенерировать текст карточки из contact_summary"""

    def write_card(self, contact_id: int, sync_dir: str) → None
        """Записать {phone}.txt"""

    def write_all_cards(self, user_id: str) → None
        """Пересоздать все карточки"""
```

CLI:
```
python -m callprofiler rebuild-summaries --user serhio
python -m callprofiler rebuild-cards --user serhio
```

## Что НЕ меняется

- Весь текущий pipeline (ingest, normalize, transcribe, diarize)
- SQLite как единственная БД
- pyannote + ref embedding для диаризации
- llama-server (не Ollama) на http://127.0.0.1:8080
- Мультипользовательская модель с user_id
- FolderSync для синхронизации (без USB-буфера)
- MacroDroid для overlay

## Условия пересмотра

| Замер | Триггер | Действие |
|-------|---------|----------|
| Ошибка ролей | > 15% на 100 звонках | LLM Role Correction |
| pyannote DER | > 25% | Попробовать NeMo |
| FTS5 скорость | > 2 сек на запрос | Векторный поиск |
| Контакты с N номерами | > 5% контактов | Zero False Merge |
| JSON parse failures | > 10% | Упростить промпт |
| SQLite locks | Измеримые задержки | PostgreSQL |

```

## STRATEGIC_PLAN_v4.md
```text
# CallProfiler — Обновлённый стратегический план v4

## Статус проекта (апрель 2026)

**Что работает:**
- Pipeline: ingest → normalize → transcribe → diarize → LLM analyze
- БД SQLite с FTS5, мультипользовательская модель
- filename_parser для всех 5 форматов
- bulk-load: 18 000 .txt файлов загружены в БД
- bulk-enrich: LLM-анализ запущен (llama-server + Qwen3.5-9B)
- extract-names: regex-извлечение имён собеседников
- card_generator: генерация .txt карточек для overlay

**Что не работает / требует доработки:**
- JSON от LLM иногда обрезается → response_parser нуждается в robust починке
- Нет contact_summary (агрегированная карточка контакта)
- Нет глобального risk_score по контакту
- Нет фильтрации коротких/бессмысленных звонков
- Карточка overlay — plain text, не структурированная

---

## Критика документа LCIS

| Идея LCIS | Вердикт | Обоснование |
|-----------|---------|-------------|
| Event Store | ❌ Отвергнуто | SQLite с tables = event store без overengineering |
| NeMo telephonic | ❌ Отвергнуто | pyannote работает, менять без замера ошибки нельзя |
| LLM Role Correction | ❌ Отложено | Удваивает время обработки. Внедрять после замера влияния ошибок ролей на качество анализа |
| Precomputed HUD | ✅ Принято | Уже реализовано, улучшить формат |
| Фильтрация коротких/small-talk | ✅ Принято | Добавить call_type в analyses |
| Глобальный risk_score | ✅ Принято | Weighted average по контакту |
| contact_summary materialized | ✅ Принято | Пересчитывать после каждого звонка |
| USB-буфер в роутере | ❌ Отвергнуто | FolderSync достаточен |
| Zero False Merge | ⏸ Отложено | После обработки 18K файлов |
| Векторный поиск | ⏸ Отложено | FTS5 покрывает 90% |

---

## Принятые улучшения из LCIS

### 1. Структурированная карточка overlay

Текущий plain text заменить на структурированный формат:

```
header: Иван Иванов — Прораб
risk: 87 🔴
hook: Просрочил смету на 9 дней. Обещал вчера отправить.
bullet1: Долг 47 000 ₽ (срок 28.03)
bullet2: Противоречие: вчера «уже оплатил», сегодня «ещё не перевёл»
bullet3: Спроси про сына (поступает в институт)
advice: Говори первым. Не давай новых сроков без подтверждения.
```

Максимум 512 байт. MacroDroid парсит построчно по ключам.

### 2. contact_summary (materialized aggregate)

Новая таблица:

```sql
CREATE TABLE contact_summaries (
    contact_id    INTEGER PRIMARY KEY REFERENCES contacts(id),
    user_id       TEXT NOT NULL,
    total_calls   INTEGER DEFAULT 0,
    last_call_date TEXT,
    global_risk   INTEGER DEFAULT 0,       -- weighted avg risk_score
    avg_bs_score  INTEGER DEFAULT 0,       -- weighted avg bs_score
    top_hook      TEXT,                     -- главная фраза для карточки
    open_promises TEXT,                     -- JSON: незакрытые обещания
    open_debts    TEXT,                     -- JSON: долги
    personal_facts TEXT,                    -- JSON: small-talk факты
    contact_role  TEXT,                     -- "Прораб", "Поставщик"
    call_types    TEXT,                     -- JSON: {"business": 12, "smalltalk": 3, "short": 5}
    advice        TEXT,                     -- рекомендация по общению
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Пересчитывается после каждого обработанного звонка с этим контактом.

### 3. Классификация звонков

Добавить в analyses:

```sql
ALTER TABLE analyses ADD COLUMN call_type TEXT
    CHECK(call_type IN ('business','smalltalk','short','spam','personal','unknown'))
    DEFAULT 'unknown';
```

Правила:
- `short`: текст < 50 символов → пропустить LLM, автозаполнение
- `smalltalk`: LLM определяет (confidence > 0.8) → вес 0.1 в агрегатах
- `spam`: повторные короткие с неизвестных номеров → вес 0 в агрегатах
- `business`/`personal`: основной контент, полный вес

### 4. Генерация hook-фразы

LLM при анализе каждого звонка дополнительно генерирует `hook` — одну фразу, которая будет отображаться при следующем входящем звонке от этого контакта.

Добавить в промпт:
```
"hook": "одна фраза-напоминание для следующего звонка с этим человеком"
```

При генерации карточки: hook берётся из последнего бизнес-звонка, а не из small-talk.

---

## Обновлённые фазы

### ФАЗА 1.5 — Завершение массовой обработки (текущая, 1-2 недели)

1. **Починить response_parser** — robust JSON parsing с починкой обрезанных ответов
2. **Прогнать bulk-enrich на всех 18 000 файлах** — запустить и оставить на несколько дней
3. **Добавить call_type** — автоклассификация short/smalltalk/business
4. **Добавить hook в промпт LLM**

### ФАЗА 2 — Агрегация и карточки (1-2 недели после Фазы 1.5)

1. **Создать contact_summaries** — materialized aggregate
2. **Создать summary_builder.py** — пересчёт contact_summary после каждого звонка
3. **Обновить card_generator.py** — структурированный формат (header/risk/hook/bullets/advice)
4. **Пересчитать карточки для всех контактов** — bulk-rebuild-cards

### ФАЗА 3 — Telegram-бот и стабилизация (2-3 недели)

1. **Telegram-бот** — /digest, /search, /contact, /promises
2. **Утренний дайджест** — топ-N по priority + просроченные обещания
3. **Обратная связь** — кнопки [OK]/[Неточно]
4. **Второй пользователь** — проверка изоляции
5. **Автозапуск** — Task Scheduler при старте Windows

### ФАЗА 4 — Веб-интерфейс (2-3 недели)

1. **FastAPI + Jinja2** — таблица звонков, карточка контакта, аудиоплеер
2. **REST API** — /calls, /contacts, /search
3. **Дашборд** — топ контактов по risk, bs_score, активности

### ФАЗА 5 — Продвинутое (по замерам)

| Триггер | Действие |
|---------|----------|
| Ошибка ролей > 15% | LLM Role Correction (двухэтапная из LCIS) |
| FTS5 не хватает | Векторный поиск |
| Контакт меняет номер > 5% случаев | Zero False Merge (phones + contact_links) |
| pyannote DER > 25% | Попробовать NeMo telephonic |

---

## Текущий приоритет

```
СЕЙЧАС: починить parser → дообработать 18 000 файлов → contact_summaries → карточки
ПОТОМ:  Telegram-бот → веб-интерфейс
КОГДА-НИБУДЬ: LLM role correction, векторный поиск, NeMo
```

Порядок не меняется пока нет измеренной проблемы.

```

## .claude/rules/llm.md
```text
# LLM Rules

- Server: llama-server at http://127.0.0.1:8080/v1/chat/completions (OpenAI format)
- Use requests.post() directly. No openai SDK. No Ollama API.
- Prompt template: configs/prompts/analyze_v001.txt
- prompt_version field in analyses tracks which version produced result
- JSON parsing: strip markdown fences → extract {…} → fix truncated → dict.get(key, default)
- If parse fails completely: save raw_llm, return Analysis with defaults, mark as partial
- Timeout: 120 seconds per request
- Roles in transcript: [me]=owner, [s2]=other. Roles may be swapped.
- "Сергей/Серёжа/Серёж/Медведев" = ALWAYS owner regardless of label.
- Max input: if transcript > 3000 chars → first 1500 + "[...]" + last 1500

```

## .claude/rules/decisions.md
```text
# Architecture Decisions

## Core Stack Decisions

### Why SQLite (not PostgreSQL/cloud)?
- **CONSTITUTION Rule 4:** Local-only, no external dependencies
- Single-file database fits Windows deployment
- User isolation via schema design (all queries filter by user_id)
- Fast enough for single-user 100+ calls/week

### Why Ollama (not OpenAI/cloud)?
- **CONSTITUTION Rule 4:** Local inference, full privacy
- Qwen 2.5 14B fits RTX 3060 12GB (float16)
- No API calls = no latency, no costs, no rate limits
- Can swap models without code changes

### Why Whisper (not WhisperX)?
- Simpler pipeline, fewer dependencies
- Good enough accuracy for business context extraction
- No speaker clustering (use Pyannote separately)
- faster-whisper = fast inference on GPU

### Why Pyannote 3.3.2 (not 4.0)?
- 3.3.2 stable with GPU support
- 4.0 requires complex setup
- Reference embedding approach (compare user's voice) works well
- use_auth_token= pattern is proven

### Why exponential decay for risk (not average)?
- Recent calls more relevant than old ones
- 90-day half-life matches human memory (3 months = half-weight)
- Recent context = better decision-making
- Avoids "one bad call 6 months ago" blocking all trust

### Why user_id isolation (not multi-tenant)?
- Simpler model (one user per Windows machine)
- CONSTITUTION Rule 2.5: "Every query filters by user_id"
- Future: can add multiple users to same machine if needed
- Zero data leakage between users

## Data Model Decisions

### Why separate Events + Promises tables?
- **Events:** 7 types (promise, debt, task, fact, risk, contradiction, smalltalk) with confidence
- **Promises:** Legacy table, keeps backward compatibility
- Events = structured extraction; Promises = specific caller debts
- Allows flexible query patterns (open promises ≠ open debts)

### Why contact_summaries (not compute on-read)?
- Telegram commands need fast response (/<1 sec)
- Computing risk from 50+ calls each time = too slow
- Rebuild on call enrichment = O(1) lookup
- Risk calculation is expensive (exponential decay)

### Why JSON fields for arrays (not separate tables)?
- Simpler queries for readonly data (promises, debts, facts)
- No joins needed for UI display
- Bounded size (max 10 promises per contact)
- Trade: harder to search/filter, but acceptable

### Why risk_score 0-100 (not continuous)?
- Easy to understand (>70 = red flag)
- Matches emoji system (🟢 <30, 🟡 30-70, 🔴 >70)
- Simple advice rules (if risk>70 → "speak first")
- Granular enough for business decisions

## Delivery Strategy Decisions

### Why Telegram (not SMS/email)?
- Instant notifications (bot runs in background)
- Rich formatting (HTML, inline buttons)
- Feedback loop (click [OK] / [Wrong])
- User has control (enable/disable per contact)

### Why caller cards (not just Telegram)?
- Android overlay (caller ID screen integration)
- FolderSync = automatic sync to phone
- Offline access (no internet needed)
- Visual risk indicator (emoji at a glance)

### Why inline feedback buttons (not separate message)?
- One-click feedback (no conversation)
- Saved to analyses.feedback field
- Trains LLM for next session (could improve prompts)
- Respects user's time

## Process Decisions

### Why Memory Protocol (CONTINUITY.md + CHANGELOG.md)?
- AI context resets between sessions
- Only way to ensure continuity = written logs
- Every change must be recorded immediately
- Prevents "context loss" spirals

### Why direct push to main (no PR)?
- Single developer (you) making decisions
- PR overhead not worth it for 1 person
- CLAUDE.md documents the decision
- Easier to experiment and iterate

### Why .bat automation files?
- Windows-native (no WSL, no bash)
- new-session.bat = reproducible briefing
- save-session.bat = safe commit (runs tests first)
- emergency-save.bat = untested quick save

## Known Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| SQLite | Simple, local | Limited to 1 machine |
| Ollama local | No API calls | Must have GPU |
| Exponential decay | Recent bias | Old context fades |
| JSON arrays | Simple | Hard to search |
| No multi-tenant | Simpler code | Can't scale easily |
| Memory Protocol | Continuity | Must update journals |

## Future Flexibility

- **Model swap:** Ollama model can change (Llama, Mistral, etc)
- **Database migration:** Could move to PostgreSQL if needed
- **Multi-user:** Can add user_id branching logic later
- **Cloud option:** Could add cloud fallback if needed
- **Telegram alternative:** Could add Discord/Slack later

```

## CHANGELOG.md
```text
# CHANGELOG.md

Все значимые изменения в проекте фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/).
Версионирование: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added — Atomic agent backlog + unattended runner (2026-05-01)

- `agent_backlog.json`:
  - Added 30 ultra-atomic backlog items derived from the architecture audit: LLM runtime contract, Orchestrator/LLM API mismatch, prompt formatting, schema_version persistence, canonical parsed JSON, SQLite idempotency, user_id isolation, graph fact_type semantics, graph-health, resource phase runner, quality gold-set, and documentation cleanup.
  - Each item includes `id`, `type`, `status`, `priority`, `artifacts`, implementation notes, acceptance criteria, and verification commands.
- `tools/agent_runner.py`:
  - Added dependency-free unattended runner that picks the next `todo` task, renders a bounded prompt, calls an external agent command, applies either unified diff patches or direct edits, runs verification, updates backlog status, and writes per-task logs under `.agent_runs/`.
  - Supports time/task/failure limits, file allowlist guard from `artifacts.touch`, clean-git preflight, optional checkpoint commits, and optional push.

**Verification:** `python -m py_compile tools/agent_runner.py`; `agent_backlog.json` parsed successfully with 30 tasks.

### Added — Duration weighting + full-transcript ASR cleaning + motivation wiring (2026-05-01)

- `src/callprofiler/biography/prompts.py`:
  - `_SCENE_SYS` rule: duration > 600s → +10 importance per 600s, max +30. Long calls = high signal.
  - `build_scene_prompt()`: adds `dur_ctx` — duration emphasis line for calls >= 600s or >= 1800s.
- `src/callprofiler/biography/p1_scene.py`:
  - `_clean_transcript()`: cleans full transcript (not just quotes) — removes Russian filled pauses, 3+ repeated words, isolated vowel artifacts. Preserves speaker labels.
  - Transcript passed through `_clean_transcript()` before LLM call.
- `src/callprofiler/biography/p5_portraits.py`:
  - `motivation_data` now loaded from graph profile and passed to `build_portrait_prompt()`.

### Added — Psychological profiling layer + entity network (Weeks 2-4 complete, 2026-05-01)

- `src/callprofiler/biography/psychology_profiler.py`:
  - `_classify_temperament()`: Hippocrates-Galen temperament (choleric/sanguine/phlegmatic/melancholic) from call frequency × emotional tone variance.
  - `_estimate_big_five()`: OCEAN traits (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism) from entity_metrics, relations, and behavioral counters.
  - `_detect_motivation()`: McClelland's needs (achievement/power/affiliation/security) from promise chains, conflict counts, and centrality.
  - `_analyze_network()`: Social network position — centrality, density, bridge score, top connections.
  - `build_profile()` now returns `temperament`, `big_five`, `motivation`, `network` alongside existing profile data.
- `src/callprofiler/biography/prompts.py`:
  - `build_portrait_prompt()` accepts `temperament`, `big_five`, `motivation` — injects deterministic psych profile as LLM context.
  - `build_chapter_prompt()` accepts `entity_network` — shows co‑occurrence graph between chapter characters.
  - `build_thread_prompt()` accepts `connections` — shows entity's social links.
  - Bumped `p1_scene`→v3, `p3_threads`→v2, `p5_portraits`→v3, `p9_yearly`→v2.
- `src/callprofiler/biography/p1_scene.py`:
  - Added `_clean_quote()` — removes ASR artifacts (filled pauses «эээ», repeated words, isolated vowels) from `key_quote` before persisting.
- `src/callprofiler/biography/p5_portraits.py`:
  - Loads `temperament` and `big_five` from `PsychologyProfiler` graph profile, passes to portrait prompt.
- `src/callprofiler/biography/p6_chapters.py`:
  - `_build_network_section()` — computes entity co‑occurrence pairs from scene entities, injects into chapter prompt.

### Added — Adaptive token budget + guaranteed resume (Week 1 complete, 2026-05-01)

- `src/callprofiler/biography/prompts.py`:
  - Added `TokenBudget` class — priority-weighted adaptive allocator. Sections compete for a global char budget; unused space is redistributed proportionally.
  - Added `BUDGETS` dict with per-pass profiles (e.g. p6: portraits 50%, arcs 25%, scenes 25% of 17K chars).
  - Replaced ALL `[:NNNN]` hard caps in 9 builder functions with `BUDGETS[name].allocate()` / `.trim_one()` calls.
  - `build_chapter_prompt()` now accepts `prev_chapter_context` and `yearly_context` for cross-chapter narrative continuity.
  - `build_yearly_summary_prompt()` now accepts `psychology_profiles` — injects entity psychology data into the annual retrospective.
  - Added per-pass `PASS_VERSIONS` dict for granular cache invalidation; bumped global to `bio-v10`.
- `src/callprofiler/biography/schema.py`:
  - Added `bio_checkpoint_items` table — per-item completion tracking for fast resume.
- `src/callprofiler/biography/repo.py`:
  - Added `save_checkpoint_item()`, `get_completed_items()`, `clear_checkpoint_items()`.
  - Fixed `start_checkpoint()`: when status is `running`/`paused`/`failed` → keeps counters and completed items (resume). When status is `done` → resets for fresh run.
  - `tick_checkpoint()` now auto-saves completed items to `bio_checkpoint_items`.
- `src/callprofiler/biography/p1_scene.py`:
  - Loads `done_ids` from checkpoint items at loop start → skips already-processed calls without DB queries.
- `src/callprofiler/biography/p5_portraits.py`:
  - Same resume logic: skips entities with completed checkpoint items.
- `src/callprofiler/biography/p6_chapters.py`:
  - Same resume logic + passes `prev_chapter_context` and `yearly_context` to `build_chapter_prompt()`.

### Fixed — Pipeline logging encoding crash + BAT progress visibility (2026-04-30)

- `src/callprofiler/cli/main.py`:
  - `_setup_logging()`: reconfigure `sys.stdout`/`sys.stderr` to UTF-8 with `errors='replace'` — prevents `UnicodeEncodeError` on Windows cp1251 locale when writing Unicode characters (checkmarks, emoji) to redirected log files.
  - Added `--log-file` top-level argument to override `cfg.log_file` from the command line.
  - `cmd_reenrich_v2`, `cmd_graph_backfill`, `cmd_graph_health`, `cmd_profile_all`, `cmd_biography_run`: now pass `cfg.log_file` (or `args.log_file`) to `_setup_logging()` so every pipeline stage has a proper UTF-8 FileHandler.
- `src/callprofiler/bulk/enricher.py`:
  - Replaced Unicode `✓` (U+2713) → `"OK"` and `✗` (U+2717) → `"ERR"` in log messages — these characters could not be encoded by the default Windows cp1251 stream encoding.
- `build-book-and-profiles.bat`:
  - All 5 stages now pass `--log-file "%LOG_FILE%"` for consistent dual logging (console + file).
  - Added a second PowerShell progress-monitor window that tails the last 5 log lines, so file-level operations (call_id, speed, ETA) are visible during the batch run without opening the log file.
  - Improved error display with `pause` before exit so the user can read failure messages.

### Changed — Stage 2–5 downstream hardening for graph-driven biographies (2026-04-29)

- `src/callprofiler/cli/main.py`
  - `graph-backfill` now passes full transcript text into `GraphBuilder.update_from_call()` for stronger fact validation.
  - `graph-backfill` now writes a `graph_replay_runs`-compatible health snapshot and triggers BS calibration, so `graph-health` can evaluate the current batch workflow without requiring a separate replay.
  - `profile-all` now prioritizes high-signal human and org entities first instead of raw `id` order and reports cache hits.
- `src/callprofiler/graph/repository.py`
  - Added `entity_profiles` table for persisted, user-scoped entity dossiers (`profile_type`, `summary`, `interpretation`, `payload_json`, `source_signature`).
- `src/callprofiler/biography/psychology_profiler.py`
  - Added persistence and signature-based reuse for psychology profiles.
  - Repeated `social` lookups inside `_interpret()` were removed; one aggregated social snapshot now feeds the prompt.
- `src/callprofiler/graph/replay.py`
  - Replay now clears `entity_profiles` together with other derived graph layers, preventing stale dossier rows after a full graph rebuild.
- `src/callprofiler/biography/orchestrator.py`
  - `p6_chapters` now automatically receives graph access.
- `src/callprofiler/biography/repo.py`
  - Portrait fetch now includes `contact_id` and aliases for graph bridging.
- `src/callprofiler/biography/p6_chapters.py`
  - Biography portraits are now resolved to graph entities via `contact_id` evidence first, then canonical/alias name fallback.
- `src/callprofiler/biography/data_extractor.py`
  - Chapter generation can now read persisted psychology summaries/interpretations back from graph storage.
- `src/callprofiler/biography/prompts.py`
  - `build_chapter_prompt()` now carries condensed graph-derived metrics, conflicts, promises, relations, temporal patterns, and psychology summaries into chapter context.
  - Bumped `PROMPT_VERSION` to `bio-v8` so memoization does not reuse pre-enrichment chapter prompts.

### Added

- `tests/test_biography_graph_bridge.py`
  - Verifies `bio portrait -> graph entity` resolution by `contact_id` and alias fallback.
- `tests/test_psychology_profiler.py`
  - Added coverage for `entity_profiles` persistence, signature-based cache reuse, and graph→biography profile extraction.

### Verification

- `pytest tests/test_psychology_profiler.py tests/test_biography_graph_bridge.py tests/test_bs_calibration.py tests/test_replay_metrics.py -q` → `47 passed`
- `pytest tests/test_graph.py -q` → `62 passed`

## [2026-04-25e] — Psychology Profiler MVP (biography/psychology_profiler.py)

### Added — biography/psychology_profiler.py, configs/prompts/psychology_profile.txt

**Задача:** Генерировать психологический профиль контакта из агрегированных данных Knowledge Graph + ONE LLM call.

**Новые файлы:**
- `src/callprofiler/biography/psychology_profiler.py` — `PsychologyProfiler` class:
  - `build_profile(entity_id, user_id)` → полный dict профиля
  - `_analyze_temporal()` — avg_calls_per_week, preferred_hours/days, trend
  - `_extract_patterns()` — behavioral patterns с severity из entity_metrics
  - `_analyze_social()` — org_links, open_promises, conflict_count, centrality
  - `_build_evolution()` — годовые avg_risk bucket-ы
  - `_interpret()` — ONE LLM call → 3 параграфа, fallback to None
- `configs/prompts/psychology_profile.txt` — шаблон промпта (3 параграфа ≤ 250 слов)
- `.claude/rules/biography-style.md` — Psychology Profile Output Contract

**CLI:**
- `person-profile --user ID ENTITY_ID [--json]`
- `profile-all --user ID [--limit N]`

**Тесты:** 11 новых тестов в `tests/test_psychology_profiler.py`, итого 197 pass.

---

## [2026-04-25d] — HEALTH GATE (graph-health CLI command)

### Added — cli/main.py: cmd_graph_health, .claude/rules/graph.md update

**Задача:** Дать gate-команду, которую нужно пройти перед `book-chapter`.

**4 проверки (exit 0 = все прошли, exit 1 = что-то упало):**
1. Last replay run: `rejection_rate < 0.90`
2. `graph-audit` → audit_critical == 0
3. `entity_metrics` has >= 1 row для user_id
4. `bs_thresholds` has >= 1 row для user_id

**Output пример:**
```
Graph Health — user: serhio
───────────────────────────────────────────────�

[... truncated by agent_runner ...]

er_id, call_id)` — отправить саммари с inline кнопками [OK]/[Неточно]
  - `handle_feedback()` — обработка нажатия кнопки обратной связи
  - Команды (CONSTITUTION.md Статья 11.3):
    - `/digest [N]` — топ звонков по priority за N дней
    - `/search текст` — FTS5 поиск по транскриптам
    - `/contact +7...` — карточка контакта с риском и саммари
    - `/promises` — открытые обещания
    - `/status` — состояние очереди (ожидают/ошибки)
  - Один бот для всех пользователей (различает по chat_id)
  - Лениво загружает `python-telegram-bot` (не требуется для импорта модуля)
  - Все данные изолированы по `user_id` (CONSTITUTION.md Статья 2.5)

### Added — Шаг 10: Caller Cards (Android overlay)
- `src/callprofiler/deliver/card_generator.py`:
  - **Класс `CardGenerator`** — генерация caller cards для Android overlay
  - `generate_card(user_id, contact_id) -> str` — сборка карточки ≤ 500 символов
    (формат CONSTITUTION.md Статья 10.2: имя, статистика, саммари, обещания, actions)
  - `write_card(user_id, contact_id, sync_dir)` — запись {phone_e164}.txt для FolderSync
  - `update_all_cards(user_id)` — пересоздание карточек всех контактов пользователя
  - Автоматическое создание sync_dir, обрезка до 500 символов, пропуск контактов без phone
- `src/callprofiler/db/repository.py`:
  - `get_all_contacts_for_user(user_id)` — список контактов для update_all_cards
  - `get_call_count_for_contact(user_id, contact_id)` — подсчёт звонков контакта
- `tests/test_card_generator.py` — 12 тест-кейсов (CRUD, обрезка, файлы, изоляция user_id)

### Added — Шаг 9: LLM анализ (Ollama + prompt builder + response parser)
- `src/callprofiler/analyze/llm_client.py`:
  - **Класс `OllamaClient`** — HTTP клиент для локального Ollama сервера
  - `generate(prompt, stream=False) -> str` — POST /api/generate, temperature=0.3
  - `list_models() -> list[str]` — доступные модели через GET /api/tags
  - Проверка подключения при инициализации (`_verify_connection`)
  - Поддержка streaming для больших ответов
  - Timeout 300сек для qwen2.5:14b
- `src/callprofiler/analyze/prompt_builder.py`:
  - **Класс `PromptBuilder`** — построение промптов с подстановкой переменных
  - `build(transcript_text, metadata, previous_summaries, version)` — главный метод
  - Извлечение длительности из временных меток `[MM:SS]` в стенограмме
  - Контекст из последних 3 анализов (max 100 символов каждый)
  - Форматирование datetime в DD.MM.YYYY HH:MM
  - Версионирование промптов: `analyze_v001.txt`, `analyze_v002.txt` и т.д.
- `src/callprofiler/analyze/response_parser.py`:
  - **Функция `parse_llm_response(raw, model, prompt_version) -> Analysis`**
  - 3-уровневый fallback: прямой JSON → markdown-обёртка → очистка → дефолты
  - Безопасное извлечение полей: `_get_int`, `_get_str`, `_get_list`, `_get_dict`
  - Graceful degradation: при сбое парсинга → Analysis с нейтральными дефолтами
  - Сохранение raw_response для отладки
- `configs/prompts/analyze_v001.txt`:
  - Шаблон JSON-промпта для LLM с метаданными и стенограммой
  - Возвращаемые поля: priority, risk_score, summary, action_items, promises, flags, key_topics

---

## [0.1.0] — 2026-03-30

### Added — Шаг 0: Структура проекта
- Полное дерево каталогов `src/callprofiler/` со всеми подпакетами
- `pyproject.toml` (name=callprofiler, version=0.1.0)
- Пустые `__init__.py` во всех пакетах
- `__main__.py` — точка входа `python -m callprofiler`
- `data/db/`, `data/logs/`, `data/users/`, `tests/fixtures/` (с `.gitkeep`)
- `reference_batch_asr.py` — эталонный прототип для извлечения логики

### Added — Шаг 1: Конфигурация
- `configs/base.yaml` — базовая конфигурация (пути, модели, pipeline, audio)
- `configs/models.yaml` — спецификации моделей
- `configs/prompts/analyze_v001.txt` — шаблон промпта для LLM-анализа
- `src/callprofiler/config.py` — загрузчик YAML, dataclass Config, валидация
  - Проверка существования `data_dir`
  - Проверка доступности ffmpeg в PATH

### Added — Шаг 2: Модели данных
- `src/callprofiler/models.py`:
  - `CallMetadata` — метаданные звонка (телефон, дата, направление)
  - `Segment` — сегмент транскрипции (start_ms, end_ms, text, speaker)
  - `Analysis` — результат LLM-анализа (priority, risk_score, summary, …)

### Added — Шаг 3: База данных
- `src/callprofiler/db/schema.sql` — схема SQLite:
  - Таблицы: users, contacts, calls, transcripts, analyses, promises
  - FTS5 виртуальная таблица `transcripts_fts` для полнотекстового поиска
- `src/callprofiler/db/repository.py` — класс `Repository`:
  - CRUD для users, contacts, calls, transcripts, analyses, promises
  - Изоляция данных по `user_id` во всех запросах
  - FTS5 поиск по транскрипциям
- `tests/test_repository.py` — тесты in-memory SQLite, проверка CRUD + изоляции

### Added — Шаг 4: Парсер имён файлов
- `src/callprofiler/ingest/filename_parser.py`:
  - Функция `parse_filename(filename) -> CallMetadata`
  - Поддержка форматов: BCR, скобочный, ACR, нераспознанный
  - Нормализация номера в E.164 (`8(916)123-45-67` → `+79161234567`)
- `tests/test_filename_parser.py` — 15+ тест-кейсов, включая "грязные" имена

### Added — Шаг 5: Нормализация аудио
- `src/callprofiler/audio/normalizer.py`:
  - `normalize(src, dst, *, loudnorm, sample_rate, channels)`:
    - Двухпроходная EBU R128 LUFS-нормализация (цель: -16 LUFS / TP -1.5 dBFS)
    - Fallback к простой конвертации при сбое анализа
    - Защита от битых файлов (проверка минимального размера)
  - `get_duration_sec(wav_path) -> int` — длительность через ffprobe
  - Проверка ffmpeg/ffprobe при импорте модуля
  - Логирование через стандартный `logging`
  - Создание родительских директорий для dst автоматически

### Added — Шаг 8: Приём файлов (Ingester)
- `src/callprofiler/ingest/ingester.py`:
  - **Класс `Ingester`** — приём аудиофайлов в очередь обработки
  - `ingest_file(user_id, filepath) -> int | None`:
    - Парсинг имени файла (filename_parser)
    - Вычисление MD5 для дедупликации
    - Проверка repo.call_exists(user_id, md5) → None если дубликат
    - Создание/получение контакта (repo.get_or_create_contact)
    - Копирование оригинала в data/users/{user_id}/audio/originals/
    - Обработка конфликтов имён (добавление MD5 префикса)
    - Запись call в БД (repo.create_call) → call_id
  - Внутренние методы: `_compute_md5()`, `_copy_original()`
  - Логирование всех операций (parse, md5, дубликат, contact, copy, create)
  - **Изоляция по user_id** (CONSTITUTION.md Статья 2.5):
    - Все пути содержат {user_id}
    - Контакты привязаны к (user_id, phone) паре
    - Один номер у двух users → два разных контакта

### Added — Шаг 7: Диаризация (Pyannote + reference embedding)
- `src/callprofiler/diarize/pyannote_runner.py`:
  - **Класс `PyannoteRunner`** — инкапсуляция pyannote.audio с управлением GPU-памятью
  - `load(ref_audio_path)` — загрузка embedding + diarization моделей, построение reference embedding
  - `diarize(wav_path) -> list[dict]`:
    - Pyannote pipeline с min/max_speakers=2
    - Фильтрация сегментов < 400мс
    - Cosine similarity маппинг: найти label, похожий на ref → OWNER, другие → OTHER
    - Конвертация float сек → int мс, сортировка по времени
  - `unload()` — выгрузка (del, gc.collect, torch.cuda.empty_cache)
  - Внутренние методы: `_get_embedding()`, `_build_ref_embedding()`, `_find_owner_label()`
  - Логирование device, статус операций, similarity score
  - **Обязательные хаки из batch_asr.py:**
    - `use_auth_token=` (не `token=`) для pyannote 3.3.2
    - Embedding model: "pyannote/embedding"
    - Diarization: "pyannote/speaker-diarization-3.1"
- `src/callprofiler/diarize/role_assigner.py`:
  - **Функция `assign_speakers(segments, diarization) -> list[Segment]`**
  - Сопоставление Segment из Whisper с диаризационными интервалами
  - Алгоритм: max overlap → ближайший по времени → fallback
  - Возврат новых Segment с назначенными ролями (исходные не меняются)

### Added — Шаг 6: Транскрибирование (Whisper)
- `src/callprofiler/transcribe/whisper_runner.py`:
  - **Класс `WhisperRunner`** — инкапсуляция загрузки/выгрузки faster-whisper
  - `load()` — загрузка модели (cuda/cpu автоматически, compute_type из config)
  - `transcribe(wav_path) -> list[Segment]`:
    - Конвертация float секунд → int миллисекунды
    - VAD-фильтр (min_silence_duration_ms=400), beam search, condition on previous text
    - Язык, beam_size из config
    - Возврат `list[Segment]` (не dict) с speaker='UNKNOWN'
    - Фильтрация пустых сегментов
  - `unload()` — выгрузка (del, gc.collect, torch.cuda.empty_cache)
  - Логирование device, GPU-info, статус операций
  - Типизированный код, обработка ошибок с контекстом

---

## Технический стек

| Компонент | Версия |
|-----------|--------|
| Python | 3.x (системный) |
| torch | 2.6.0+cu124 |
| faster-whisper | latest |
| pyannote.audio | 3.3.2 |
| GPU | NVIDIA RTX 3060 12GB |
| CUDA | 12.4 |

```

## CONTINUITY.md
```text
# CONTINUITY.md — Журнал непрерывности разработки

Этот файл обновляется после **каждой рабочей сессии**.
Цель: любой разработчик или AI-агент может открыть репозиторий и мгновенно
понять, что уже сделано, что в работе, и что делать дальше.

---

## Status

DONE: Atomic agent backlog + unattended runner for opencode/DeepSeek work queue (2026-05-01)
NOW: 30 todo tasks in agent_backlog.json; runner ready at tools/agent_runner.py
NEXT: Run runner in dry-run first, then run with opencode command in direct or patch mode
BLOCKERS: Local PowerShell in Codex session fails with Windows PowerShell error 8009001d; files were created via filesystem API
DONE: Week 1 — Adaptive TokenBudget, guaranteed checkpoint resume, all hard caps eliminated (2026-05-01)
DONE: Biography quality improvements — cross-chapter context, context window fix, graph integration, per-pass versioning (2026-04-30)
DONE: ALL 4 WEEKS — Full pipeline hardening: TokenBudget, psych profilers (temperament+BigFive+motivation), network graph, ASR cleaning, guaranteed resume, docs (2026-05-01)
NOW: 196 tests pass, reenrich-v2 real data test OK (3 files, 0 errors)
NEXT: Run build-book-and-profiles.bat for full Stages 1-5
BLOCKERS: None
DONE: Pipeline logging crash fix — UnicodeEncodeError resolved, BAT progress monitor added (2026-04-30)
DONE: Biography arch-fixes — export filter, p8 idempotency, checkpoint reset, p8b dedup (2026-04-20)
DONE: D:\calls → C:\calls path migration (2026-04-20)
DONE: Biography p9 wired + insight field pipeline (2026-04-20)
DONE: Biography module v6 — время звонка + годовой итог p9 (2026-04-20)
DONE: Biography Behavioral Engine p3b — bio-v7 (2026-04-20)
DONE: Knowledge Graph Этапы 1-2 — schema, graph module, 25 tests pass (2026-04-24)
DONE: Knowledge Graph Этапы 3-4 — EntityResolver fixes + Auditor + LLM Disambiguator (2026-04-25)
DONE: Knowledge Graph Этап 1 — REPLAY (идемпотентная пересборка, 13 tests) (2026-04-25)
DONE: Knowledge Graph Этап 2.1 — FACT VALIDATOR (citation validation, speaker detection, 13 tests) (2026-04-25)
DONE: Knowledge Graph Этап 2.2 — DRIFT CHECK (validator_impact_drift auditor check, 6 tests) (2026-04-25)
DONE: Knowledge Graph Этап 3 — BS CALIBRATION (percentile-based thresholds, 18 tests) (2026-04-25)
DONE: Knowledge Graph Этап 4 — THRESHOLD INTEGRATION (data-driven card emoji, 186 tests pass) (2026-04-25)
DONE: HEALTH GATE — graph-health CLI command, 4 checks, exit 0/1 (2026-04-25)
DONE: PSYCHOLOGY PROFILER MVP — PsychologyProfiler class + CLI person-profile/profile-all (2026-04-25)
NOW: 196 tests pass — ready for next pipeline run
NEXT: Run build-book-and-profiles.bat to complete Stages 2-5
BLOCKERS: None

---

## Текущее состояние: 2026-05-01 (Atomic agent backlog + unattended runner)

### Что сделано

- Создан `agent_backlog.json` — machine-readable очередь из 30 атомарных задач для автономной работы агента:
  - P0 runtime/docs alignment;
  - LLMClient/Orchestrator API repair;
  - prompt formatting fix;
  - schema_version/canonical JSON persistence;
  - SQLite idempotency;
  - user_id isolation;
  - graph fact_type/BS-index correctness;
  - graph-health/resource runner/quality gold-set;
  - final docs and stabilization tasks.
- Создан `tools/agent_runner.py` — dependency-free runner:
  - берет следующий `todo`;
  - формирует prompt с project brief, guardrails, artifacts и контекстом файлов;
  - вызывает внешний агент через `--agent-cmd`;
  - поддерживает `--apply-mode patch` и `--apply-mode direct`;
  - применяет file guard по `artifacts.touch`;
  - запускает tests/lint;
  - пишет logs/prompts/responses в `.agent_runs/`;
  - обновляет статусы backlog;
  - умеет checkpoint commits через `--commit-every`.

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Тесты
- `python -m py_compile tools/agent_runner.py` — OK
- `agent_backlog.json` parsed successfully — 30 tasks, all `todo`
- Полный pytest не запускался в этой Codex-сессии: локальный PowerShell падает с ошибкой 8009001d до выполнения команд.

### Следующий шаг
- Выполнить dry-run:
  `python tools/agent_runner.py --repo C:\pro\callprofiler --dry-run`
- Затем подключить реальную команду opencode/DeepSeek и выбрать режим:
  - `--apply-mode direct`, если opencode сам редактирует файлы;
  - `--apply-mode patch`, если opencode печатает unified diff.

---

## Текущее состояние: 2026-04-30 (Pipeline logging crash fix)

### Что сделано

- **Encoding crash fix:** `_setup_logging()` теперь реконфигурирует `sys.stdout`/`sys.stderr` на UTF-8 с `errors='replace'`, что предотвращает падение `UnicodeEncodeError` при записи Unicode-символов в cp1251-строки на Windows.
- **Safe characters in enricher.py:** `✓` → `"OK"`, `✗` → `"ERR"` — лог-сообщения теперь безопасны для любых кодировок.
- **`--log-file` argument:** Добавлен как top-level аргумент CLI; все 5 pipeline-команд передают `cfg.log_file` / `args.log_file` в `_setup_logging()`.
- **BAT progress monitor:** `build-book-and-profiles.bat` запускает второе PowerShell-окно с `Get-Content -Wait -Tail 5`, которое показывает последние 5 строк лога (per-file operations: call_id, speed, ETA) в реальном времени.
- **BAT hardening:** Все стадии теперь передают `--log-file "%LOG_FILE%"`, улучшен вывод ошибок с `pause` перед exit.

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Тесты
196 passed, 6 failed (pre-existing Windows PermissionError in tempdir cleanup — не связаны с изменениями).

### Следующий шаг
- Запустить `build-book-and-profiles.bat` и наблюдать за стадиями 2-5

---

## Session Update: 2026-04-29

### What changed
- Hardened the active `build-book-and-profiles` downstream path without touching the currently running Stage 1 wrapper:
  - `graph-backfill` now feeds transcript text into fact validation
  - `graph-backfill` now saves a `graph_replay_runs`-compatible snapshot and triggers BS calibration
  - `profile-all` now persists cached `entity_profiles`
  - `p6_chapters` now resolves biography portraits into graph entities and injects condensed graph dossiers into chapter prompts
  - `PROMPT_VERSION` bumped to `bio-v8`
- Added graph-derived dossier storage cleanup to `graph/replay.py`

### Verification
- `pytest tests/test_psychology_profiler.py tests/test_biography_graph_bridge.py tests/test_bs_calibration.py tests/test_replay_metrics.py -q` → `47 passed`
- `pytest tests/test_graph.py -q` → `62 passed`

### Next
- Let the live batch reach Stages 2–5 and observe whether:
  - `graph-health` now passes for real workflow reasons
  - `entity_profiles` fill with useful dossiers
  - `p6_chapters` enriched context improves cohesion without overflowing context
- After this run, decide separately whether `build-book-and-profiles.bat` should become fail-fast on `graph-health`.

### Known constraints
- `build-book-and-profiles.bat` itself was not edited during this session because it is already executing; editing a live `.bat` mid-run is risky.
- `p5_portraits` still does not consume saved graph dossiers directly; the current integration point is `p6_chapters`.
feat: psychology profiler MVP
```

### Что сделано в этой сессии (2026-04-25, часть 6)

**HEALTH GATE (Block A):**
- `cmd_graph_health()` в `cli/main.py` — 4 проверки: replay rejection < 0.90, audit no-critical, entity_metrics > 0, bs_thresholds > 0
- Subparser `graph-health --user ID` зарегистрирован
- Dispatch entry добавлен
- `.claude/rules/graph.md` — добавлено правило "graph-health exit 0 required before book-chapter"

**PSYCHOLOGY PROFILER MVP (Block B):**
- `src/callprofiler/biography/psychology_profiler.py` — `PsychologyProfiler` class
  - `build_profile()` → dict с keys: entity_id, canonical_name, metrics, patterns, temporal, social, evolution, top_facts, interpretation
  - `_analyze_temporal()`, `_extract_patterns()`, `_analyze_social()`, `_build_evolution()`, `_interpret()`
- `configs/prompts/psychology_profile.txt` — prompt template
- CLI: `person-profile` и `profile-all`
- `tests/test_psychology_profiler.py` — 11 тестов, итого 197 pass
- `.claude/rules/biography-style.md` — Psychology Profile Output Contract (новый файл)

### Следующий шаг
- Narrative journal extraction: `narrative-extract` CLI command

### Известные ограничения / долги
- `_interpret()` делает 3 SQL запроса `_analyze_social()` вместо одного — незначительно

---

## Текущее состояние: 2026-04-25 (Knowledge Graph Этап 4 — THRESHOLD INTEGRATION)

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Последний коммит
```
Step 4: THRESHOLD INTEGRATION — Use BSCalibrator for data-driven risk emoji in cards (cedb0c5)
```

### Что сделано в этой сессии (2026-04-25, часть 5 — BS CALIBRATION)

**ШАГ 3 — BS CALIBRATION (вычисление пороговых значений на основе перцентилей):**
- `src/callprofiler/graph/calibration.py` — BSCalibrator class (новый файл)
- Метод analyze(user_id, min_calls=3, min_promises=1):
  - Получить отфильтрованные BS-индексы (исключить archived + owner)
  - Вычислить перцентили: p25, p50, p75, p90 (линейная интерполяция)
  - Определить пороги: reliable_max=p25, noisy_max=p50, risky_max=p75, unreliable_max=p90
  - Сохранить в bs_thresholds table с std_dev
  - Вернуть ok=True если >= 3 entities, иначе ok=False
- Метод get_label(bs_index, user_id):
  - Получить пороги из bs_thresholds
  - Присвоить label: reliable/noisy/risky/unreliable/critical/uncalibrated
  - Вернуть (label, emoji) где emoji из LABEL_MAP
- Статический метод _percentile(data, p):
  - Линейная интерполяция: rank = (p/100) * (n-1)
  - lower_idx, upper_idx, fraction
  - Результат: lower_val + fraction * (upper_val - lower_val)

**LABEL_MAP (5 категорий риска + uncalibrated):**
- 🟢 reliable: bs_index <= p25
- 🟡 noisy: p25 < bs_index <= p50
- 🔴 risky: p50 < bs_index <= p75
- 🔴 unreliable: p75 < bs_index <= p90
- ⚫ critical: bs_index > p90
- ⚪ uncalibrated: no thresholds available

**Тесты:** 18 новых в `test_bs_calibration.py`:
- test_calibrator_analyze_empty_user: no entities → ok=False
- test_calibrator_analyze_few_entities: < 3 entities → ok=False
- test_calibrator_analyze_sufficient_entities: >= 3 entities → ok=True with thresholds
- test_calibrator_analyze_computes_percentil

[... truncated by agent_runner ...]



---

## Детали шага 12: pipeline/orchestrator.py

### Orchestrator — главный оркестратор pipeline

**Методы класса:**
- `__init__(config, repo, telegram=None)` — инициализация всех компонентов
- `process_call(call_id) -> bool` — полная обработка одного звонка
- `process_batch(call_ids)` — batch-обработка с GPU-оптимизацией
- `process_pending()` — обработать все звонки со статусом 'new'
- `retry_errors()` — повторить звонки со статусом 'error' (retry_count < max)

**Поток process_call():**
1. Normalize — ffmpeg → WAV 16kHz mono + LUFS нормализация
2. Transcribe — загрузить Whisper → транскрибировать → выгрузить
3. Diarize — загрузить pyannote → диаризация с ref embedding → assign speakers → выгрузить
4. Analyze — построить промпт → отправить в Ollama → распарсить JSON → сохранить
5. Deliver — обновить caller card + отправить Telegram саммари

**Поток process_batch() (GPU-оптимизация, CONSTITUTION.md Ст. 9.2):**
1. Normalize все файлы
2. Загрузить Whisper → транскрибировать ВСЕ → выгрузить
3. Для каждого файла: загрузить pyannote → diarize → выгрузить
4. Для каждого: LLM analyze (Ollama сам управляет моделью)
5. Для каждого: deliver (карточка + Telegram)

**Ключевые особенности:**
- При ошибке на любом шаге: логирование + update_call_status('error') → не роняет pipeline
- Все статусы в БД: normalizing → transcribing → diarizing → analyzing → delivering → done
- Async Telegram через asyncio.get_event_loop() / new_event_loop()
- Контекст из последних 5 анализов для промпта
- Graceful degradation: нет ref_audio → пропуск диаризации

---

## Детали шага 11: deliver/telegram_bot.py

### TelegramNotifier — Telegram-бот для уведомлений и команд

**Методы класса:**
- `__init__(token, repo)` — инициализация с токеном и репозиторием
- `send_summary(user_id, call_id)` — отправить саммари с кнопками [OK]/[Неточно]
- `handle_feedback()` — обработать нажатие кнопки обратной связи
- Команды: `cmd_digest [N]`, `cmd_search текст`, `cmd_contact +7...`, `cmd_promises`, `cmd_status`
- `run()` — запустить polling в отдельном потоке

**Ключевые особенности:**
- Один бот на всех пользователей (различает по `chat_id`)
- Лениво загружает `python-telegram-bot` (не требуется для импорта)
- Все данные фильтруются по `user_id` (CONSTITUTION.md Статья 2.5)
- HTML-форматирование сообщений
- Inline кнопки для обратной связи

**Команды (CONSTITUTION.md Статья 11.3):**
- `/digest [N]` — топ звонков по priority за N дней
- `/search текст` — FTS5 поиск по транскриптам
- `/contact +7...` — карточка контакта (имя, звонки, риск, саммари)
- `/promises` — открытые обещания
- `/status` — состояние очереди (ожидают, ошибки)

---

## Детали шага 10: deliver/card_generator.py

### CardGenerator — caller cards для Android overlay

**Методы класса:**
- `__init__(repo: Repository)` — инициализация с репозиторием
- `generate_card(user_id, contact_id) -> str` — собрать карточку ≤ 500 символов
- `write_card(user_id, contact_id, sync_dir)` — записать {phone_e164}.txt
- `update_all_cards(user_id)` — пересоздать карточки для всех контактов

**Формат карточки (CONSTITUTION.md Статья 10.2):**
```
{display_name}
Последний: {дата} | Звонков: {count} | Risk: {risk_score}
─────────────────────────
{summary последнего звонка}
─────────────────────────
Обещания: {открытые promises, макс 3}
Actions: {action items, макс 3}
```

**Поток данных:**
1. `get_contact()` → display_name, phone_e164
2. `get_call_count_for_contact()` → кол-во звонков
3. `get_recent_analyses(limit=1)` → последний анализ (summary, risk_score, action_items)
4. `get_contact_promises()` → открытые обещания (filter status='open')
5. Сборка карточки → обрезка до 500 символов

**Дополнения в Repository:**
- `get_all_contacts_for_user(user_id)` — для `update_all_cards`
- `get_call_count_for_contact(user_id, contact_id)` — COUNT(*) звонков

**Тесты (12 тест-кейсов):**
- Базовая карточка (имя, звонки, risk, саммари, обещания, actions)
- Карточка без анализа, без обещаний, без actions
- Несуществующий контакт → пустая строка
- Обрезка до 500 символов при длинном содержимом
- Запись файла {phone}.txt в sync_dir
- Пропуск контакта без phone_e164
- Создание несуществующего sync_dir
- update_all_cards для множества контактов
- Правильный подсчёт множества звонков
- Изоляция карточек по user_id

---

## Сессия 2026-04-10: Phonebook name priority fix

### Исправление: имя из телефонной книги не обновлялось в БД

**Проблема:** `get_or_create_contact()` возвращал `contact_id` без обновления `display_name`
если контакт уже существовал.

**Правило:** Имя в имени файла = имя из телефонной книги Android = АБСОЛЮТНЫЙ ПРИОРИТЕТ.

**Исправлено** в `repository.py`:
- При каждом вызове `get_or_create_contact()` с `display_name≠None` → UPDATE + `name_confirmed=1`
- При создании нового контакта → INSERT с `name_confirmed=1` если есть имя

**Схема приоритетов:**
- `display_name` + `name_confirmed=1` = из телефонной книги (WINNER всегда)
- `guessed_name` = из транскрипта (name_extractor, только если display_name пустой)

**Тесты: 3 новых в test_repository.py, итого 90 pass**

---

## Сессия 2026-04-09: Bug fixes, JSON parsing, оптимизация enricher

### Выполненные работы (6 коммитов):

#### 1. **SQL binding fix** (369935e)
- **Проблема:** enricher.py WHERE c.user_id = ? без параметров
- **Решение:** добавлена (user_id,) в execute()
- **Статус:** ✅ Все 87 тестов pass

#### 2. **FOREIGN KEY constraint fix** (bef94e9)
- **Проблема:** promises требует contact_id NOT NULL, но calls.contact_id может быть NULL
- **Решение:** 
  - schema.sql: contact_id в promises → nullable
  - repository.save_promises(): пропускаем если contact_id = NULL
  - enricher.py: лучший error handling для batch writes
- **Статус:** ✅ Все 87 тестов pass

#### 3. **Оптимизация bulk_enrich** (6034fc0)
- **5 оптимизаций:**
  1. **Сжатие транскрипта** — убрать сегменты < 3 символов (except "да"/"ну"/"угу")
  2. **max_tokens: 1024** (было 2048, JSON редко > 600 токенов)
  3. **Батчевая запись в БД** — новый Repository.save_batch() для одной транзакции
  4. **Пропуск коротких звонков** — transcript < 50 символов → stub, без LLM
  5. **Логирование** — per-file timing, ~tok/s, ETA
- **Статус:** ✅ Все 87 тестов pass

#### 4. **Robust JSON parsing** (668e44c)
- **Новые уровни спасения обрезанного JSON:**
  1. Markdown extraction (```json ... ```)
  2. Text bounds extraction ({...})
  3. **_repair_json()** — auto-close truncated structures
  4. **Regex fallback** — извлечение ключевых полей если JSON совсем сломан
- **Type coercion:** "75" → 75, list из string → [string]
- **Дефолты:** summary='', risk_score=0 (более мягкие чем раньше)
- **Статус:** ✅ Все 87 тестов pass

#### 5. **LLM client improvements** (668e44c)
- **max_tokens:** 2048 → 1500 (достаточно для полного JSON)
- **timeout:** 300s → 180s (лучше для длинных звонков)
- **Error handling:** generate() возвращает None вместо exception
- **Статус:** ✅ Совместимо со всеми модулями

#### 6. **Syntax error fix** (8cd8d5c)
- **Проблема:** unmatched ')' в response_parser.py line 138
- **Решение:** endswith(('}',)) ) → endswith(('}',))
- **Статус:** ✅ Все 87 тестов pass

### Упрощение промпта (analyze_v001.txt)
- **Было:** 30+ полей в огромной структуре
- **Стало:** компактная структура с 15 обязательными полями:
  - Основное: summary, category, priority, risk_score, sentiment
  - Действия: action_items[], promises[]
  - Данные: people, companies, amounts
  - Оценка: contact_name_guess, bs_score, bs_evidence
  - Флаги: {urgent, conflict, money, legal_risk}

### Готовность к production
- ✅ SQL binding: исправлены все параметризованные запросы
- ✅ FK constraints: обработана NULL-безопасность
- ✅ JSON парсинг: 4-уровневая защита от обрезанного JSON
- ✅ LLM интеграция: graceful degradation на ошибках
- ✅ Оптимизация: транскрипты сжимаются, батчи в БД, пропуск пустых

### Оставшиеся задачи (на следующую сессию)
- Тестирование на реальных звонках > 10 мин
- Мониторинг GPU memory при длинных батчах
- (опционально) Интеграция с Android overlay-окном

---

## Как подхватить работу

```bash
git checkout claude/clone-callprofiler-repo-hL5dQ
git pull origin claude/clone-callprofiler-repo-hL5dQ

# Следующий шаг:
# ШАГ 15: Интеграционный тест (ручной прогон)
# python -m callprofiler add-user serhio --incoming D:\calls\audio \
#   --ref-audio C:\pro\mbot\ref\manager.wav --sync-dir D:\calls\sync\serhio\cards
# python -m callprofiler process "D:\calls\audio\test.mp3" --user serhio
# python -m callprofiler status
# python -m callprofiler watch
```

```
