# -*- coding: utf-8 -*-
"""
watcher.py — автоматический мониторинг папок пользователей.

Сканирует incoming_dir каждого пользователя, находит новые аудиофайлы,
передаёт их в Ingester, затем запускает Orchestrator для обработки.

Цикл:
  1. scan_all_users() — найти новые файлы, зарегистрировать в БД
  2. orchestrator.process_batch() — обработать новые звонки
  3. orchestrator.retry_errors() — повторить ошибочные
  4. sleep(watch_interval_sec)
"""

from __future__ import annotations

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
        logger.info("FileWatcher инициализирован")

    def scan_all_users(self) -> list[int]:
        """Сканировать incoming_dir всех пользователей.

        Для каждого пользователя:
          1. Получить incoming_dir из БД
          2. Найти аудиофайлы (mp3, m4a, wav, ogg, opus, flac, aac, wma)
          3. Проверить что файл «устоялся» (file_settle_sec)
          4. Передать в ingester.ingest_file()

        Возвращает:
            Список новых call_id
        """
        users = self.repo.get_all_users()
        if not users:
            logger.debug("Нет зарегистрированных пользователей")
            return []

        new_call_ids = []

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

            user_ids = self._scan_user_dir(user_id, incoming_path)
            new_call_ids.extend(user_ids)

        if new_call_ids:
            logger.info("Найдено %d новых файлов", len(new_call_ids))

        return new_call_ids

    def run_loop(self) -> None:
        """Запустить бесконечный цикл мониторинга.

        Цикл:
          1. Сканировать все папки пользователей
          2. Обработать новые файлы (process_batch)
          3. Повторить ошибочные (retry_errors)
          4. Подождать watch_interval_sec
        """
        interval = self.config.pipeline.watch_interval_sec
        logger.info(
            "Запуск цикла мониторинга (интервал=%d сек)", interval
        )

        while True:
            try:
                # Сканировать и зарегистрировать новые файлы
                new_ids = self.scan_all_users()

                # Обработать новые
                if new_ids:
                    self.orchestrator.process_batch(new_ids)

                # Повторить ошибочные
                self.orchestrator.retry_errors()

            except KeyboardInterrupt:
                logger.info("Остановка по Ctrl+C")
                break
            except Exception as exc:
                logger.error("Ошибка в цикле мониторинга: %s", exc)

            time.sleep(interval)

    def _scan_user_dir(self, user_id: str, incoming_path: Path) -> list[int]:
        """Сканировать папку пользователя и зарегистрировать новые файлы.

        Параметры:
            user_id       — идентификатор пользователя
            incoming_path — путь к incoming_dir

        Возвращает:
            Список новых call_id
        """
        new_ids = []
        settle_sec = self.config.pipeline.file_settle_sec

        # Рекурсивный обход (с подпапками)
        for root, _dirs, files in os.walk(incoming_path):
            for filename in files:
                filepath = Path(root) / filename

                # Проверить расширение
                if filepath.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue

                # Проверить что файл «устоялся» (не записывается)
                if not self._is_file_settled(filepath, settle_sec):
                    logger.debug(
                        "Файл ещё записывается: %s", filepath
                    )
                    continue

                # Передать в Ingester
                try:
                    call_id = self.ingester.ingest_file(user_id, str(filepath))
                    if call_id is not None:
                        new_ids.append(call_id)
                        logger.info(
                            "Зарегистрирован: %s → call_id=%d (user_id=%s)",
                            filename, call_id, user_id,
                        )
                    # call_id=None → дубликат, пропускаем молча
                except Exception as exc:
                    logger.error(
                        "Ошибка при инжесте %s: %s", filepath, exc
                    )

        return new_ids

    @staticmethod
    def _is_file_settled(filepath: Path, settle_sec: int) -> bool:
        """Проверить что файл не изменялся последние settle_sec секунд.

        Параметры:
            filepath    — путь к файлу
            settle_sec  — минимальное время «покоя» в секундах

        Возвращает:
            True если файл устоялся
        """
        try:
            mtime = filepath.stat().st_mtime
            age = time.time() - mtime
            return age >= settle_sec
        except OSError:
            return False
