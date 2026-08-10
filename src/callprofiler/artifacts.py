# -*- coding: utf-8 -*-
"""artifacts.py — atomic publication of file artifacts (T-08).

Windows ``os.replace()`` is atomic only within the same volume — temp files
are therefore always created in the SAME directory as the destination,
never under ``%TEMP%``. Any failure removes the temp file; no orphans
survive a crash mid-write/mid-copy.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

_COPY_BUFFER_SIZE = 1024 * 1024  # 1MB — audio files are large


def _tmp_path(dest: Path) -> Path:
    return dest.with_name(f".{dest.name}.tmp{os.getpid()}")


def file_fingerprint(path: str | Path) -> str:
    """Дешёвый детерминированный отпечаток файла: путь + размер + mtime_ns.

    Не читает файл целиком. Живёт здесь, а не в ``diarize/pyannote_runner``,
    потому что это чистая работа с файловой системой: держать её рядом с
    моделью означало бы тянуть torch ради сравнения двух путей — и делать
    сторож reference-эмбеддинга (T-10) непроверяемым там, где ML-стека нет.
    """
    p = os.path.abspath(os.path.normpath(str(path)))
    try:
        st = os.stat(path)
        return f"{p}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        return f"{p}|missing"


def atomic_write_bytes(dest: str | Path, data: bytes) -> Path:
    """Write ``data`` to ``dest`` atomically: tmp file → fsync → os.replace.

    Leaves no partial/orphan file behind on any exception.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(dest)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return dest


def atomic_write_text(dest: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Text convenience wrapper around :func:`atomic_write_bytes`."""
    return atomic_write_bytes(dest, text.encode(encoding))


def atomic_copy_file(
    src: str | Path,
    dest: str | Path,
    expected_hash: str | None = None,
    hash_algo: str = "md5",
) -> tuple[Path, str]:
    """Copy ``src`` to ``dest`` atomically, hashing the stream while copying.

    Hash is computed in the SAME pass as the copy (no second read over the
    file). If ``expected_hash`` is given (e.g. already computed by the
    caller for dedup), the digest and the copied size are verified against
    the source before the atomic rename — mismatch raises ``ValueError``
    and leaves no partial/renamed file at ``dest``.

    Returns ``(dest_path, hex_digest)``.
    """
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(dest)
    hasher = hashlib.new(hash_algo)
    try:
        with open(src, "rb") as fsrc, open(tmp, "wb") as fdst:
            while chunk := fsrc.read(_COPY_BUFFER_SIZE):
                fdst.write(chunk)
                hasher.update(chunk)
            fdst.flush()
            os.fsync(fdst.fileno())
        digest = hasher.hexdigest()
        src_size = src.stat().st_size
        tmp_size = tmp.stat().st_size
        if tmp_size != src_size:
            raise ValueError(f"Размер не совпадает: src={src_size} copied={tmp_size}")
        if expected_hash is not None and digest != expected_hash:
            raise ValueError(f"Хеш не совпадает: ожидался {expected_hash}, получен {digest}")
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return dest, digest
