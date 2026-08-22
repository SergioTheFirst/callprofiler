# -*- coding: utf-8 -*-
"""purge_files.py — T-06: карантин файлов пользователя (move в trash, никогда rmtree).

Корни пользователя: ``data_dir/users/{uid}``, ``text_export_dir/users/{uid}``, ``sync_dir/{uid}``.
``apply=False`` — только счётчики; ``apply=True`` — ОДИН ``shutil.move`` корня целиком в
``data_dir/trash/{uid}-{YYYYmmddHHMMSS}/{i}-{parent}/{uid}`` (восстановление = move обратно).
Гарды: user_id без разделителей/``..``; корень строго внутри своей базы и не равен ей; корень-симлинк
пропускается; назначение строго внутри trash. Симлинки внутри корня переезжают как симлинки (move =
rename, содержимое целей не трогается; hardlink-записи — тоже просто переименование).
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_user_id(user_id: str) -> None:
    """ValueError, если user_id пуст или содержит разделители пути / ``..``."""
    if not user_id or ".." in user_id or any(ch in user_id for ch in "/\\"):
        raise ValueError(f"недопустимый user_id: {user_id!r}")


def _roots(config, user_id: str) -> list[tuple[Path, Path]]:
    """[(база, корень)] — только существующие корни."""
    validate_user_id(user_id)
    cands = [(Path(config.data_dir), Path(config.data_dir) / "users" / user_id)]
    text_dir = getattr(getattr(config, "pipeline", None), "text_export_dir", None)
    if text_dir:
        cands.append((Path(text_dir), Path(text_dir) / "users" / user_id))
    sync_dir = getattr(config, "sync_dir", None)
    if sync_dir:
        cands.append((Path(sync_dir), Path(sync_dir) / user_id))
    return [(b, r) for b, r in cands if r.exists()]


def user_file_roots(config, user_id: str) -> list[Path]:
    return [r for _, r in _roots(config, user_id)]


def _count_files(root: Path) -> int:
    # os.walk не следует за симлинк-папками; симлинк-файлы не считаем (переедут как ссылки)
    return sum(1 for d, _, fs in os.walk(root) for f in fs if not os.path.islink(os.path.join(d, f)))


def _inside(path: Path, base: Path) -> bool:
    p, b = path.resolve(), base.resolve()
    return p != b and p.is_relative_to(b)


def purge_user_files(config, user_id: str, apply: bool = False, now: datetime | None = None) -> dict[str, int]:
    """{str(корень): файлов}. apply=True → корни перемещены в trash (см. модуль)."""
    counts: dict[str, int] = {}
    trash = Path(config.data_dir) / "trash" / f"{user_id}-{(now or datetime.now()).strftime('%Y%m%d%H%M%S')}"
    for i, (base, root) in enumerate(_roots(config, user_id)):
        if root.is_symlink() or not _inside(root, base):
            logger.warning("purge_files: пропуск %s (симлинк или вне базы %s)", root, base)
            continue
        counts[str(root)] = _count_files(root)
        if not apply:
            continue
        dest = trash / f"{i}-{root.parent.name}" / root.name
        if not _inside(dest, trash.parent):
            raise ValueError(f"purge_files: назначение {dest} вне trash")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(dest))
        logger.info("purge_files: %s → %s (%d файлов)", root, dest, counts[str(root)])
    return counts
