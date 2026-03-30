# -*- coding: utf-8 -*-
"""
ingester.py — приём аудиофайлов от пользователя в обработку.

Workflow:
  1. Парсинг имени файла → CallMetadata
  2. Вычисление MD5-хеша оригинала
  3. Проверка дедупликации (repo.call_exists)
  4. Создание/получение контакта
  5. Копирование оригинала в data/users/{user_id}/audio/originals/
  6. Запись в БД (repo.create_call) → call_id
  7. Возврат call_id или None (если дубликат)

Правила изоляции (CONSTITUTION.md Статья 2.5):
  - Все операции фильтруются по user_id
  - Один номер у двух пользователей → два разных контакта
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from callprofiler.ingest.filename_parser import parse_filename

if TYPE_CHECKING:
    from callprofiler.config import Config
    from callprofiler.db.repository import Repository

logger = logging.getLogger(__name__)

_MD5_BUFFER_SIZE = 8192


class Ingester:
    """Приём и регистрация аудиофайлов в очередь обработки.

    Использование:
        ingester = Ingester(repo, config)
        call_id = ingester.ingest_file(user_id="serhio", filepath="/path/to/call.mp3")
        if call_id:
            print(f"Зарегистрирован звонок {call_id}")
        else:
            print("Дубликат, пропущен")
    """

    def __init__(self, repo: Repository, config: Config) -> None:
        """Инициализировать ingester.

        Параметры:
            repo    — Repository для доступа к БД
            config  — Config с параметрами data_dir и т.д.
        """
        self.repo = repo
        self.config = config

    def ingest_file(self, user_id: str, filepath: str) -> int | None:
        """Приняти аудиофайл, зарегистрировать его в pipeline.

        Workflow:
          1. Проверить что файл существует
          2. Парсить имя → CallMetadata
          3. Вычислить MD5 оригинала
          4. Проверить дедупликацию: repo.call_exists(user_id, md5)
          5. Получить или создать контакт
          6. Скопировать оригинал в data/users/{user_id}/audio/originals/
          7. Создать запись call в БД (status='new')
          8. Вернуть call_id (или None если дубликат)

        Параметры:
            user_id  — ID пользователя (владельца телефона)
            filepath — путь к аудиофайлу (локальный или полный)

        Возвращает:
            call_id (int) если успешно зарегистрирован
            None если файл является дубликатом

        Raises:
            FileNotFoundError  — если файл не существует
            RuntimeError       — если копирование или запись в БД упали
        """
        fpath = Path(filepath)

        # 1. Проверить что файл существует
        if not fpath.exists():
            raise FileNotFoundError(f"Файл не найден: {filepath}")

        if not fpath.is_file():
            raise FileNotFoundError(f"Не файл: {filepath}")

        logger.info("ingest_file: %s (user_id=%s)", fpath.name, user_id)

        # 2. Парсить имя файла
        try:
            metadata = parse_filename(fpath.name)
        except Exception as exc:
            logger.error("Ошибка при парсинге имени %s: %s", fpath.name, exc)
            raise RuntimeError(f"Не удалось распарсить имя файла: {fpath.name}") from exc

        # 3. Вычислить MD5
        try:
            file_md5 = self._compute_md5(fpath)
        except Exception as exc:
            logger.error("Ошибка при вычислении MD5 для %s: %s", fpath.name, exc)
            raise RuntimeError(f"Не удалось вычислить MD5: {filepath}") from exc

        # 4. Проверить дедупликацию
        if self.repo.call_exists(user_id, file_md5):
            logger.info("Дубликат: %s (MD5=%s, user_id=%s)", fpath.name, file_md5, user_id)
            return None

        # 5. Получить или создать контакт
        try:
            contact_id = self.repo.get_or_create_contact(
                user_id=user_id,
                phone_e164=metadata.phone,
                display_name=metadata.contact_name,
            )
            logger.debug("contact_id=%d для phone=%s", contact_id, metadata.phone)
        except Exception as exc:
            logger.error("Ошибка при создании контакта для %s: %s", metadata.phone, exc)
            raise RuntimeError(f"Не удалось создать контакт: {exc}") from exc

        # 6. Скопировать оригинал в data/users/{user_id}/audio/originals/
        try:
            dest_audio_path = self._copy_original(user_id, fpath, file_md5)
        except Exception as exc:
            logger.error("Ошибка при копировании оригинала: %s", exc)
            raise RuntimeError(f"Не удалось скопировать оригинал: {exc}") from exc

        # 7. Создать запись call в БД
        try:
            call_id = self.repo.create_call(
                user_id=user_id,
                contact_id=contact_id,
                direction=metadata.direction,
                call_datetime=metadata.call_datetime,
                source_filename=fpath.name,
                source_md5=file_md5,
                audio_path=dest_audio_path,
            )
            logger.info(
                "Зарегистрирован call_id=%d для %s (user_id=%s)",
                call_id,
                fpath.name,
                user_id,
            )
            return call_id
        except Exception as exc:
            logger.error("Ошибка при создании записи call в БД: %s", exc)
            raise RuntimeError(f"Не удалось записать call в БД: {exc}") from exc

    # ── Внутренние методы ──────────────────────────────────────────────────────

    def _compute_md5(self, filepath: Path) -> str:
        """Вычислить MD5-хеш файла (для дедупликации).

        Параметры:
            filepath  — Path объект

        Возвращает:
            Шестнадцатиричная строка MD5 хеша (32 символа)
        """
        md5_hash = hashlib.md5()
        with open(filepath, "rb") as f:
            while chunk := f.read(_MD5_BUFFER_SIZE):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def _copy_original(self, user_id: str, src_path: Path, file_md5: str) -> str:
        """Скопировать оригинальный аудиофайл в архив.

        Путь назначения: data/users/{user_id}/audio/originals/{filename}

        Параметры:
            user_id   — ID пользователя
            src_path  — Path к исходному файлу
            file_md5  — MD5-хеш (для логирования)

        Возвращает:
            Полный путь к скопированному файлу (абсолютный)

        Raises:
            RuntimeError  — если копирование упало
        """
        # Построить путь назначения
        dest_dir = Path(self.config.data_dir) / "users" / user_id / "audio" / "originals"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Имя файла: {filename} (можно добавить MD5 префикс при конфликтах)
        dest_path = dest_dir / src_path.name

        # Если файл с таким именем уже есть → проверить что это не разные файлы
        if dest_path.exists():
            existing_md5 = self._compute_md5(dest_path)
            if existing_md5 == file_md5:
                # Это один и тот же файл, уже скопирован (но дедупликация должна была срабо­тать)
                logger.debug(
                    "Файл %s уже скопирован (MD5 совпадает), переиспользуем",
                    dest_path.name,
                )
                return str(dest_path)
            else:
                # Разные файлы с одинаковым именем → добавить MD5 в имя
                stem = dest_path.stem
                suffix = dest_path.suffix
                dest_path = dest_dir / f"{stem}_{file_md5[:8]}{suffix}"
                logger.info(
                    "Конфликт имён: переименовываем в %s",
                    dest_path.name,
                )

        # Скопировать
        try:
            shutil.copy2(src_path, dest_path)
            logger.debug(
                "Оригинал скопирован: %s → %s (MD5=%s)",
                src_path.name,
                dest_path,
                file_md5,
            )
            return str(dest_path)
        except Exception as exc:
            raise RuntimeError(
                f"Не удалось скопировать {src_path} → {dest_path}: {exc}"
            ) from exc
