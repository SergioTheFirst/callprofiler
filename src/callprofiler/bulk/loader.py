# -*- coding: utf-8 -*-
"""
loader.py — массовая загрузка существующих .txt транскриптов в БД.

Функция bulk_load() ищет все .txt файлы в папке, парсит имена (CallMetadata),
разбирает содержимое по меткам [me]: / [s2]:, и загружает в БД.

Пример использования:
  from callprofiler.bulk.loader import bulk_load
  bulk_load("/path/to/transcripts", user_id="serhio", db_path="/path/to/db.db")
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path

from callprofiler.db.repository import Repository
from callprofiler.ingest.filename_parser import parse_filename
from callprofiler.models import Segment

log = logging.getLogger(__name__)

# Регулярка для разделения сегментов
_SEGMENT_SEP = re.compile(r"\[(?:me|s2)\]:?\s*", re.IGNORECASE)
_SPEAKER_RE = re.compile(r"\[(?P<speaker>me|s2)\]:?\s*", re.IGNORECASE)


def _calculate_md5(content: bytes) -> str:
    """Вычислить MD5 хеш содержимого файла."""
    return hashlib.md5(content).hexdigest()


def _parse_segments(text: str) -> list[Segment]:
    """
    Разбить текст на сегменты по меткам [me]: и [s2]:.
    Возвращает список Segment объектов с назначенными ролями.

    Пример:
      [me]: Привет, как дела?
      [s2]: Хорошо, спасибо.
      [me]: Отлично!

    Результат:
      [Segment(..., text="Привет, как дела?", speaker="OWNER"),
       Segment(..., text="Хорошо, спасибо.", speaker="OTHER"),
       Segment(..., text="Отлично!", speaker="OWNER")]
    """
    if not text or not isinstance(text, str):
        return []

    segments: list[Segment] = []
    start_ms = 0
    duration_ms = 100  # фиксированная длительность каждого сегмента (100ms)

    # Найти все сегменты вместе с их спикерами
    parts = _SPEAKER_RE.split(text.strip())

    # split() с группами возвращает: [пред-текст, спикер1, текст1, спикер2, текст2, ...]
    # Если нет маркеров, вернуть пустой список
    if len(parts) < 3:  # нужно минимум [пред-текст, спикер, текст]
        return []

    # Пропускаем первый элемент если он пусто (начинаем с метки)
    i = 0
    if parts and not parts[0].strip():
        i = 1

    while i < len(parts) - 1:  # -1 чтобы не выходить за границы
        speaker_raw = parts[i].lower().strip()  # 'me' или 's2'
        speaker = "OWNER" if speaker_raw == "me" else "OTHER"
        text_content = parts[i + 1].strip()

        if text_content:
            end_ms = start_ms + duration_ms
            segments.append(
                Segment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text_content,
                    speaker=speaker,
                )
            )
            start_ms = end_ms

        i += 2

    return segments


# ───────────────────────────────────────────────────────────────
# Основная функция загрузки
# ───────────────────────────────────────────────────────────────

def bulk_load(
    txt_folder: str,
    user_id: str,
    db_path: str,
) -> dict[str, int]:
    """
    Массовая загрузка .txt транскриптов в БД.

    Args:
        txt_folder: папка с .txt файлами транскриптов
        user_id: ID пользователя в системе
        db_path: путь к SQLite БД

    Returns:
        dict с статистикой: {
            'loaded': количество загруженных файлов,
            'skipped': дубликаты (по MD5),
            'errors': ошибки парсинга,
            'unique_contacts': уникальные контакты,
        }
    """
    txt_path = Path(txt_folder)
    if not txt_path.is_dir():
        log.error("Папка не найдена: %s", txt_folder)
        return {
            'loaded': 0,
            'skipped': 0,
            'errors': 0,
            'unique_contacts': 0,
        }

    repo = Repository(db_path)
    repo.init_db()

    # Проверить что пользователь существует
    user = repo.get_user(user_id)
    if not user:
        log.error("Пользователь '%s' не найден", user_id)
        return {
            'loaded': 0,
            'skipped': 0,
            'errors': 0,
            'unique_contacts': 0,
        }

    # Найти все .txt файлы рекурсивно
    txt_files = list(txt_path.rglob("*.txt"))
    log.info("[bulk_load] Найдено %d .txt файлов в %s", len(txt_files), txt_folder)

    stats = {
        'loaded': 0,
        'skipped': 0,
        'errors': 0,
        'unique_contacts': set(),
    }

    for idx, filepath in enumerate(txt_files, 1):
        try:
            # Логировать прогресс каждые 100 файлов
            if idx % 100 == 0:
                log.info(
                    "[bulk_load] Обработано %d/%d файлов (загружено: %d, пропущено: %d, ошибки: %d)",
                    idx, len(txt_files),
                    stats['loaded'], stats['skipped'], stats['errors'],
                )

            # Парсить имя файла
            metadata = parse_filename(filepath.name)

            # Прочитать содержимое файла
            content_bytes = filepath.read_bytes()
            content_text = content_bytes.decode("utf-8", errors="replace")
            md5_hash = _calculate_md5(content_bytes)

            # Дедупликация по MD5
            if repo.call_exists(user_id, md5_hash):
                log.debug("[bulk_load] Дубликат (MD5): %s", filepath.name)
                stats['skipped'] += 1
                continue

            # Разбить на сегменты
            segments = _parse_segments(content_text)
            if not segments:
                log.warning("[bulk_load] Сегменты не найдены в файле: %s", filepath.name)
                stats['errors'] += 1
                continue

            # Создать/получить контакт
            contact_id = None
            if metadata.phone:
                contact_id = repo.get_or_create_contact(
                    user_id=user_id,
                    phone_e164=metadata.phone,
                    display_name=metadata.contact_name,
                )
                stats['unique_contacts'].add(contact_id)

            # Создать звонок (status='done' — уже обработан)
            call_id = repo.create_call(
                user_id=user_id,
                contact_id=contact_id,
                direction=metadata.direction,
                call_datetime=metadata.call_datetime.isoformat() if metadata.call_datetime else None,
                source_filename=filepath.name,
                source_md5=md5_hash,
                audio_path=str(filepath),
            )

            # Обновить статус в 'done'
            repo.update_call_status(call_id, "done")

            # Сохранить транскрипт
            repo.save_transcripts(call_id, segments)

            log.debug(
                "[bulk_load] Загружен файл: %s (call_id=%d, segments=%d, phone=%s)",
                filepath.name, call_id, len(segments), metadata.phone or "None",
            )
            stats['loaded'] += 1

        except Exception as e:
            log.error("[bulk_load] Ошибка при обработке %s: %s", filepath.name, e, exc_info=True)
            stats['errors'] += 1

    # Завершить и вывести статистику
    unique_count = len(stats['unique_contacts'])
    stats['unique_contacts'] = unique_count

    log.info(
        "\n[bulk_load] Завершено!\n"
        "  Загружено файлов    : %d\n"
        "  Пропущено (дубли)   : %d\n"
        "  Ошибки парсинга     : %d\n"
        "  Уникальных контактов: %d\n"
        "  Всего обработано    : %d",
        stats['loaded'],
        stats['skipped'],
        stats['errors'],
        unique_count,
        len(txt_files),
    )

    return stats
