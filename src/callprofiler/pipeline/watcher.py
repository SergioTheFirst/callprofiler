# -*- coding: utf-8 -*-
"""
watcher.py — автоматический мониторинг папок пользователей.

Сканирует incoming_dir каждого пользователя (рекурсивно, с подпапками),
находит новые аудиофайлы, регистрирует их через Ingester, запускает
Orchestrator, а после успешной транскрибации убирает исходники из incoming
(копия уже в архиве users/{uid}/audio/originals/YYYY/MM).

Цикл (run_loop):
  1. scan_all_users()        — найти новые файлы, зарегистрировать в БД
  2. process_batch(new_ids)  — обработать новые звонки
  3. cleanup_sources()       — убрать исходники транскрибированных из incoming
  4. retry_errors()          — повторить ошибочные
  5. sleep(watch_interval_sec)
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository
    from callprofiler.ingest.ingester import Ingester
    from callprofiler.pipeline.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Поддерживаемые аудио-форматы
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac", ".wma"}

# pipeline_stage >= этого значения → транскрипт сохранён (можно убирать исходник)
_TRANSCRIBED_STAGE = 2


class FileWatcher:
    """Мониторинг папок пользователей и запуск обработки новых файлов.

    Использование:
        watcher = FileWatcher(config, repo, ingester, orchestrator)
        new_ids = watcher.scan_all_users()   # однократное сканирование
        watcher.run_loop()                    # бесконечный цикл
    """

    def __init__(
        self,
        config: Config,
        repo: Repository,
        ingester: Ingester,
        orchestrator: Orchestrator,
    ) -> None:
        """Инициализировать FileWatcher.

        Параметры:
            config       — конфигурация проекта
            repo         — Repository для доступа к данным
            ingester     — Ingester для регистрации файлов
            orchestrator — Orchestrator для обработки звонков
        """
        self.config = config
        self.repo = repo
        self.ingester = ingester
        self.orchestrator = orchestrator
        # call_id → (user_id, incoming-корень, исходный путь) за последнее сканирование
        self._last_sources: dict[int, tuple[str, Path, Path]] = {}
        logger.info("FileWatcher инициализирован")

    def scan_all_users(self) -> list[int]:
        """Сканировать incoming_dir всех пользователей.

        Заполняет ``self._last_sources`` (call_id → исходный путь) для
        последующей очистки. Возвращает список новых call_id.
        """
        self._last_sources = {}

        users = self.repo.get_all_users()
        if not users:
            logger.debug("Нет зарегистрированных пользователей")
            return []

        new_call_ids: list[int] = []

        for user in users:
            user_id = user["user_id"]
            incoming_dir = user.get("incoming_dir", "")

            if not incoming_dir:
                logger.debug("У пользователя %s не задан incoming_dir", user_id)
                continue

            incoming_path = Path(incoming_dir)
            if not incoming_path.exists():
                logger.warning(
                    "incoming_dir не существует: %s (user_id=%s)",
                    incoming_dir, user_id,
                )
                continue

            new_call_ids.extend(self._scan_user_dir(user_id, incoming_path))

        if new_call_ids:
            logger.info("Найдено %d новых файлов", len(new_call_ids))

        return new_call_ids

    def run_once(self) -> int:
        """Один цикл: scan → обработать pending/stalled → cleanup → retry, выход.

        Для тестового/пакетного прогона (bat). Обрабатывает не только новые файлы,
        но и весь backlog (status new/normalizing) через process_pending — иначе
        при повторном запуске «0 new» оставлял бы незаконченные звонки висеть.
        Возвращает число новых зарегистрированных файлов.
        """
        new_ids = self.scan_all_users()
        # process_pending обрабатывает и только что зарегистрированные, и зависшие
        self.orchestrator.process_pending()
        self.cleanup_sources()
        self.orchestrator.retry_errors()
        return len(new_ids)

    def run_loop(self) -> None:
        """Запустить бесконечный цикл мониторинга."""
        interval = self.config.pipeline.watch_interval_sec
        logger.info("Запуск цикла мониторинга (интервал=%d сек)", interval)

        while True:
            try:
                new_ids = self.scan_all_users()

                if new_ids:
                    self.orchestrator.process_batch(new_ids)

                # Убрать исходники успешно транскрибированных
                self.cleanup_sources()

                # Повторить ошибочные
                self.orchestrator.retry_errors()

            except KeyboardInterrupt:
                logger.info("Остановка по Ctrl+C")
                break
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                logger.error("Ошибка в цикле мониторинга: %s", exc)

            time.sleep(interval)

    def cleanup_sources(self) -> int:
        """Убрать из incoming исходники звонков, у которых готов транскрипт.

        Копия уже лежит в архиве (originals/YYYY/MM), поэтому исходник из
        incoming можно удалить. Гейт: ``pipeline.remove_source_on_success``.

        Возвращает число удалённых файлов.
        """
        if not getattr(self.config.pipeline, "remove_source_on_success", True):
            return 0
        if not self._last_sources:
            return 0

        removed = 0
        for call_id, (user_id, root, src_path) in list(self._last_sources.items()):
            call = self.repo.get_call(user_id, call_id)
            if not call:
                continue
            if int(call.get("pipeline_stage", 0) or 0) < _TRANSCRIBED_STAGE:
                continue  # ещё не транскрибирован — оставляем
            self._remove_source(src_path, root)
            removed += 1

        if removed:
            logger.info("Убрано исходников из incoming: %d", removed)
        return removed

    # ── Внутренние методы ──────────────────────────────────────────────

    def _scan_user_dir(self, user_id: str, incoming_path: Path) -> list[int]:
        """Сканировать папку пользователя и зарегистрировать новые файлы.

        Для каждого аудиофайла: MD5 → поиск существующего звонка.
          - звонок есть и транскрибирован (stage>=2) → убрать исходник
            (копия уже в архиве);
          - звонок есть, но НЕ транскрибирован (новый/завис/error) → ОСТАВИТЬ
            (данные не теряем, перезапустится; уберём в следующем цикле, когда
            транскрипт будет готов);
          - звонка нет → ingest_file (регистрация) + запомнить исходник.
        """
        new_ids: list[int] = []
        settle_sec = self.config.pipeline.file_settle_sec
        remove_on_success = getattr(
            self.config.pipeline, "remove_source_on_success", True
        )

        # Рекурсивный обход (с подпапками)
        for root, _dirs, files in os.walk(incoming_path):
            for filename in files:
                filepath = Path(root) / filename

                if filepath.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue

                # Файл ещё пишется → пропустить до следующего цикла
                if not self._is_file_settled(filepath, settle_sec):
                    logger.debug("Файл ещё записывается: %s", filepath)
                    continue

                try:
                    md5 = self._file_md5(filepath)
                except OSError as exc:
                    logger.error("Не удалось прочитать %s: %s", filepath, exc)
                    continue

                existing = self.repo.get_call_by_md5(user_id, md5)
                if existing is not None:
                    # Уже зарегистрирован. Убираем исходник ТОЛЬКО если транскрипт
                    # готов (stage>=2) — иначе оставляем для повторной обработки.
                    stage = int(existing.get("pipeline_stage", 0) or 0)
                    if remove_on_success and stage >= _TRANSCRIBED_STAGE:
                        logger.info(
                            "Дубликат транскрибирован, убираю из incoming: %s", filename
                        )
                        self._remove_source(filepath, incoming_path)
                    continue

                try:
                    call_id = self.ingester.ingest_file(user_id, str(filepath))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ошибка при инжесте %s: %s", filepath, exc)
                    continue

                if call_id is not None:
                    new_ids.append(call_id)
                    self._last_sources[call_id] = (user_id, incoming_path, filepath)
                    logger.info(
                        "Зарегистрирован: %s → call_id=%d (user_id=%s)",
                        filename, call_id, user_id,
                    )

        return new_ids

    @staticmethod
    def _file_md5(filepath: Path) -> str:
        """MD5 файла (та же схема, что в Ingester — для дедупликации)."""
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _remove_source(self, src_path: Path, stop_root: Path | None = None) -> None:
        """Удалить исходник из incoming и подчистить пустые подпапки.

        ``stop_root`` — корень incoming: его и всё, что выше, НЕ трогаем.
        """
        try:
            src_path.unlink(missing_ok=True)
            logger.debug("Исходник убран из incoming: %s", src_path)
            self._prune_empty_parents(src_path.parent, stop_root)
        except OSError as exc:
            logger.warning("Не удалось убрать исходник %s: %s", src_path, exc)

    @staticmethod
    def _prune_empty_parents(directory: Path, stop_root: Path | None) -> None:
        """Удалить пустые подпапки внутри incoming. Сам incoming-корень не трогаем."""
        if stop_root is None:
            return
        try:
            stop = Path(stop_root).resolve()
            current = directory.resolve()
            for _ in range(8):  # ограничитель глубины — без бесконечного цикла
                # current должен быть строго ВНУТРИ stop_root, иначе стоп
                if current == stop or stop not in current.parents:
                    break
                if not current.exists() or any(current.iterdir()):
                    break
                current.rmdir()
                current = current.parent
        except OSError:
            pass

    @staticmethod
    def _is_file_settled(filepath: Path, settle_sec: int) -> bool:
        """Проверить что файл не изменялся последние settle_sec секунд."""
        try:
            mtime = filepath.stat().st_mtime
            age = time.time() - mtime
            return age >= settle_sec
        except OSError:
            return False
