# -*- coding: utf-8 -*-
"""
purge_files.py — безопасное удаление файлов пользователя (quarantine в trash).

Поддерживает file quarantine: вместо удаления, перемещение в trash-папку с
временной меткой для возможного восстановления.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_user_id(user_id: str) -> None:
    """Validate user_id to prevent path traversal attacks.

    Raises ValueError if user_id contains path separators, starts with '/',
    contains '..', or is empty.
    """
    if not user_id:
        raise ValueError("user_id cannot be empty")
    if user_id.startswith("/") or user_id.startswith("\\"):
        raise ValueError("user_id cannot start with path separator")
    if ".." in user_id:
        raise ValueError("user_id cannot contain '..'")
    if "/" in user_id or "\\" in user_id:
        raise ValueError("user_id cannot contain path separators")


def user_file_roots(config, user_id: str) -> list[Path]:
    """Вернуть список корневых папок пользователя.

    Включает:
    - users/{user_id} в data_dir
    - users/{user_id} в text_export_dir (если задан)
    - Per-user subdir в sync_dir (если задан и существует)

    Возвращает ТОЛЬКО существующие пути.
    """
    validate_user_id(user_id)
    roots: list[Path] = []

    # users/{user_id} в data_dir
    data_user_root = Path(config.data_dir) / "users" / user_id
    if data_user_root.exists():
        roots.append(data_user_root)

    # text_export_dir/users/{user_id}
    if hasattr(config, "pipeline") and hasattr(config.pipeline, "text_export_dir"):
        text_dir = config.pipeline.text_export_dir
        if text_dir:
            text_user_root = Path(text_dir) / "users" / user_id
            if text_user_root.exists():
                roots.append(text_user_root)

    # sync_dir/{user_id}
    if hasattr(config, "sync_dir") and config.sync_dir:
        sync_user_root = Path(config.sync_dir) / user_id
        if sync_user_root.exists():
            roots.append(sync_user_root)

    return roots


def purge_user_files(
    config, user_id: str, apply: bool = False, now: Optional[datetime] = None
) -> dict[str, int]:
    """Переместить все файлы пользователя в quarantine (trash-папку).

    ``apply=False`` — только счётчик файлов (ничего не трогает).
    ``apply=True`` — перемещает в trash/{user_id}-{timestamp}/{parent_name}/ (не удаляет вообще).
    ``now`` — для тестов, переопределяет текущую дату/время.

    Проверки безопасности:
    - root ДОЛЖЕН быть строго ВНУТРИ родительской папки (защита от escape)
    - root НЕ может быть РАВЕН родительской папке
    - Симлинки НЕ следуются (shutil.move переместит сам симлинк, не его target)

    Возвращает {str(root): count_files} — количество файлов в каждой папке.
    """
    roots = user_file_roots(config, user_id)
    counts: dict[str, int] = {}

    if not roots:
        return counts

    if now is None:
        now = datetime.now()

    timestamp = now.strftime("%Y%m%d%H%M%S")
    trash_dir = Path(config.data_dir) / "trash"

    for root in roots:
        # Containment check: root MUST be strictly inside parent, not equal to it
        try:
            root_resolved = root.resolve()
            parent_resolved = root.parent.resolve()

            # Проверка: parent_resolved не должна быть None (всегда есть)
            # root_resolved строго внутри parent_resolved (не равна ей)
            if not root_resolved.is_relative_to(parent_resolved):
                logger.warning(
                    "purge_files: root %s не внутри parent %s, пропускаем",
                    root_resolved,
                    parent_resolved,
                )
                counts[str(root)] = 0
                continue

            if root_resolved == parent_resolved:
                logger.warning(
                    "purge_files: root %s равна parent, пропускаем (защита)",
                    root_resolved,
                )
                counts[str(root)] = 0
                continue
        except (ValueError, RuntimeError) as e:
            logger.warning(
                "purge_files: containment check failed for root %s: %s, пропускаем",
                root,
                e,
            )
            counts[str(root)] = 0
            continue

        # Проверка: если это симлинк, пропускаем (но можно переместить сам симлинк)
        if root.is_symlink():
            logger.warning("purge_files: root %s is a symlink, пропускаем", root)
            counts[str(root)] = 0
            continue

        # Count files (не следуем за симлинками в подпапках)
        file_count = 0
        try:
            for p in root.rglob("*"):
                if p.is_file() and not p.is_symlink():
                    file_count += 1
                # Симлинки на файлы не считаются
        except (OSError, PermissionError) as e:
            logger.warning("purge_files: ошибка при подсчёте файлов в %s: %s", root, e)

        counts[str(root)] = file_count

        if apply and file_count > 0:
            # Переместить в trash/{user_id}-{timestamp}/{parent_name}/{basename}
            #例: data_dir/users/testuser -> trash/testuser-{timestamp}/users
            trash_user_dir = trash_dir / f"{user_id}-{timestamp}"
            trash_user_dir.mkdir(parents=True, exist_ok=True)

            # Get parent directory name (e.g., "users" from "data_dir/users/testuser")
            parent_name = root.parent.name

            # Destination: trash/{user_id}-{timestamp}/{parent_name}
            # Note: shutil.move will rename root to parent_name if it doesn't exist
            dest = trash_user_dir / parent_name

            try:
                # Validate dest is contained within trash_dir (prevent symlink escapes)
                try:
                    dest.resolve().relative_to(trash_dir.resolve())
                except ValueError:
                    raise ValueError(
                        f"purge_files: destination {dest.resolve()} escapes trash {trash_dir.resolve()}"
                    )

                # Walk and move only real files, explicitly skip symlinks
                # (prevent symlinks to external paths from being preserved in trash)
                dest.mkdir(parents=True, exist_ok=True)
                moved_count = 0
                for src_file in root.rglob("*"):
                    if src_file.is_symlink():
                        # Skip symlinks entirely - do not move them to trash
                        continue
                    # Check for hardlinks (st_nlink > 1): prevent hardlink-based injection
                    try:
                        stat_info = os.stat(src_file)
                        if stat_info.st_nlink > 1:
                            logger.warning(
                                "purge_files: skipping hardlink %s (st_nlink=%d)",
                                src_file, stat_info.st_nlink
                            )
                            continue
                    except (OSError, RuntimeError) as e:
                        logger.warning("purge_files: could not stat %s: %s", src_file, e)
                        continue

                    if src_file.is_file():
                        # Calculate relative path and create destination
                        rel_path = src_file.relative_to(root)
                        # Validate rel_path contains no '..' components (path traversal guard)
                        if any(p == ".." for p in rel_path.parts):
                            logger.error(
                                "purge_files: relative path %s contains '..', skipping %s",
                                rel_path, src_file
                            )
                            continue
                        dest_file = dest / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src_file), str(dest_file))
                        moved_count += 1

                # Remove empty directories from source
                for src_dir in sorted(root.rglob("*"), reverse=True):
                    if src_dir.is_dir() and not src_dir.is_symlink():
                        try:
                            src_dir.rmdir()
                        except OSError:
                            # Directory not empty or other error, skip
                            pass

                # Try to remove root if now empty
                try:
                    root.rmdir()
                except OSError:
                    pass

                logger.info(
                    "purge_files: moved %s (%d real files, skipped symlinks) to %s",
                    root, moved_count, dest
                )
            except (OSError, PermissionError) as e:
                logger.error(
                    "purge_files: ошибка при перемещении %s в trash: %s", root, e
                )
                counts[str(root)] = 0  # Отмечаем как не перемещённое

    return counts
