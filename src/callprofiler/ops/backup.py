# -*- coding: utf-8 -*-
"""
backup.py — T-20: verified SQLite backup/restore (P-OPS-01 gate before T-05).

Online backup API only (sqlite3.Connection.backup) — raw file copy is rejected
because WAL can be mid-checkpoint (.claude/rules/db.md, bugs.md 2026-06-04).
Every snapshot is verified (quick_check + foreign_key_check + counts + sha256)
BEFORE it gets a manifest and enters retention. A snapshot that fails
verification is deleted immediately and never displaces a good one.

Connections always go through db.connection.ConnectionFactory (T-04) — never
a bare sqlite3.connect() — so WAL/foreign_keys/busy_timeout stay consistent
with the rest of the app.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from callprofiler.artifacts import atomic_write_text
from callprofiler.db.connection import ConnectionFactory

# Таблицы, чей COUNT(*) идёт в манифест — ядро системы (db.md/pipeline.md).
TRACKED_TABLES: tuple[str, ...] = (
    "calls", "analyses", "transcripts", "contacts", "events",
)

_FREE_SPACE_MARGIN = 1.2  # +20% поверх размера БД на копию
_FREE_SPACE_FLOOR_BYTES = 10 * 1024 * 1024  # минимум 10MB запаса всегда

MANIFEST_SUFFIX = ".manifest.json"


def _app_version() -> str:
    """Версия приложения — из pyproject.toml (пакет не проинсталлирован, dev/run split)."""
    try:
        root = Path(__file__).resolve().parents[3]  # src/callprofiler/ops/ -> repo root
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "unknown"


@dataclass
class BackupManifest:
    filename: str
    created_at: str
    sha256: str
    size_bytes: int
    user_version: int
    app_version: str
    python_version: str
    os_name: str
    table_counts: dict[str, int]
    kind: str = "manual"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "BackupManifest":
        return cls(**json.loads(text))


@dataclass
class VerifyResult:
    ok: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    ok: bool
    problems: list[str] = field(default_factory=list)


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TRACKED_TABLES:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = int(row[0])
        except sqlite3.OperationalError:
            counts[table] = -1  # таблица отсутствует (старая схема) — не крашим манифест
    return counts


def _manifest_path(backup_path: str | Path) -> Path:
    return Path(str(backup_path) + MANIFEST_SUFFIX)


def _read_manifest(backup_path: str | Path) -> BackupManifest:
    mp = _manifest_path(backup_path)
    return BackupManifest.from_json(mp.read_text(encoding="utf-8"))


def _assert_dest_not_in_source(backup_dir: str | Path, source_db_path: str | Path) -> None:
    """Preflight: каталог назначения не может лежать внутри каталога исходной БД."""
    source_dir = Path(source_db_path).resolve().parent
    dest = Path(backup_dir).resolve()
    try:
        dest.relative_to(source_dir)
    except ValueError:
        return  # не вложен — ок
    raise ValueError(
        f"Backup dir {dest} is inside source data dir {source_dir} — refused"
    )


def _assert_free_space(backup_dir: str | Path, needed_bytes: int) -> None:
    check_dir = Path(backup_dir)
    while not check_dir.exists():
        check_dir = check_dir.parent
    free = shutil.disk_usage(check_dir).free
    required = max(int(needed_bytes * _FREE_SPACE_MARGIN), needed_bytes + _FREE_SPACE_FLOOR_BYTES)
    if free < required:
        raise OSError(
            f"Not enough free space at {check_dir}: have {free}, need {required}"
        )


def _open_backup_conn(path: str | Path) -> sqlite3.Connection:
    """RO-ish connection to a standalone backup file (via the shared factory)."""
    return ConnectionFactory(str(path)).reader()


@dataclass
class _Inspection:
    quick_check: str
    fk_violations: int
    user_version: int
    table_counts: dict[str, int]


def _inspect(path: str | Path) -> _Inspection:
    """Open a snapshot and run the integrity checks shared by create/verify.

    Raises sqlite3.DatabaseError if the file cannot even be opened as SQLite
    (corrupt/truncated) — callers decide how to report that.
    """
    conn = _open_backup_conn(path)
    try:
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        counts = _table_counts(conn)
    finally:
        conn.close()
    return _Inspection(quick_check, len(fk_violations), int(user_version), counts)


def create_backup(
    db_path: str,
    backup_dir: str,
    *,
    kind: str = "manual",
    retention_daily: int = 7,
    retention_weekly: int = 4,
) -> BackupManifest:
    """Snapshot db_path into backup_dir via SQLite online backup API.

    Verifies before publishing. Raises on preflight failure or if the
    resulting snapshot fails verification (no partial/bad backup is left
    behind, no rotation happens).
    """
    db_path = str(db_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    _assert_dest_not_in_source(backup_dir, db_path)
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    _assert_free_space(backup_dir, os.path.getsize(db_path))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stem = Path(db_path).stem
    final_name = f"{stem}-{ts}.db"
    final_path = Path(backup_dir) / final_name
    tmp_path = Path(backup_dir) / f".tmp-{final_name}"

    src_conn = ConnectionFactory(db_path).reader()
    try:
        dest_conn = ConnectionFactory(str(tmp_path)).writer()
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    # Verify the tmp snapshot BEFORE it becomes a real (manifested) backup.
    # Any failure here (corrupt open, or an unexpected error) must delete the
    # tmp file and never publish/rotate — a half-checked backup is not a backup.
    try:
        inspection = _inspect(tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Backup snapshot failed verification: {exc}") from exc

    problems = []
    if inspection.quick_check != "ok":
        problems.append(f"quick_check: {inspection.quick_check}")
    if inspection.fk_violations:
        problems.append(f"foreign_key_check: {inspection.fk_violations} violations")
    if problems:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("Backup snapshot failed verification: " + "; ".join(problems))

    sha = _sha256_file(tmp_path)
    size = tmp_path.stat().st_size

    os.replace(tmp_path, final_path)

    manifest = BackupManifest(
        filename=final_name,
        created_at=datetime.now(timezone.utc).isoformat(),
        sha256=sha,
        size_bytes=size,
        user_version=inspection.user_version,
        app_version=_app_version(),
        python_version=sys.version.split()[0],
        os_name=os.name,
        table_counts=inspection.table_counts,
        kind=kind,
    )
    # Манифест — тоже атомарно (реюз T-08 artifacts): снимок публикуется через
    # os.replace, а манифест обычным write_text давал бы усечённый файл при
    # крахе в этот момент. Такой снимок verify_backup отвергнет, а retention,
    # работающий "по манифесту", посчитает файл чужим и не тронет — накопится
    # неудаляемый орфан. Атомарная запись убирает это состояние.
    atomic_write_text(_manifest_path(final_path), manifest.to_json())

    apply_retention(backup_dir, retention_daily=retention_daily, retention_weekly=retention_weekly)
    return manifest


def verify_backup(backup_path: str) -> VerifyResult:
    """Re-verify an already-published backup against its manifest."""
    problems: list[str] = []
    bp = Path(backup_path)
    if not bp.exists():
        return VerifyResult(False, [f"backup file missing: {bp}"])

    try:
        manifest = _read_manifest(bp)
    except FileNotFoundError:
        return VerifyResult(False, [f"manifest missing: {_manifest_path(bp)}"])
    except Exception as exc:
        return VerifyResult(False, [f"manifest unreadable: {exc}"])

    actual_sha = _sha256_file(bp)
    if actual_sha != manifest.sha256:
        problems.append("sha256 mismatch (file tampered/corrupt or manifest tampered)")

    actual_size = bp.stat().st_size
    if actual_size != manifest.size_bytes:
        problems.append(f"size mismatch: {actual_size} != {manifest.size_bytes}")

    try:
        inspection = _inspect(bp)
        if inspection.quick_check != "ok":
            problems.append(f"quick_check: {inspection.quick_check}")
        if inspection.fk_violations:
            problems.append(f"foreign_key_check: {inspection.fk_violations} violations")
        if inspection.table_counts != manifest.table_counts:
            problems.append(
                f"table counts mismatch: {inspection.table_counts} != {manifest.table_counts}"
            )
    except sqlite3.DatabaseError as exc:
        problems.append(f"open failed (corrupt/truncated): {exc}")

    return VerifyResult(ok=not problems, problems=problems)


def restore_backup(
    backup_path: str,
    to_path: str,
    *,
    overwrite: bool = False,
    snapshot_dir_on_overwrite: str | None = None,
) -> RestoreResult:
    """Restore a verified backup into to_path.

    Refuses to overwrite an existing file unless overwrite=True. When
    overwriting and snapshot_dir_on_overwrite is given, snapshots the
    current file there first (kind='pre-restore').
    """
    verify = verify_backup(backup_path)
    if not verify.ok:
        return RestoreResult(False, ["backup failed verification, refusing to restore"] + verify.problems)

    to_p = Path(to_path)
    if to_p.exists():
        if not overwrite:
            return RestoreResult(False, [f"destination exists: {to_p} (pass overwrite=True)"])
        if snapshot_dir_on_overwrite:
            create_backup(str(to_p), snapshot_dir_on_overwrite, kind="pre-restore")

    to_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = to_p.with_name(to_p.name + ".part")
    shutil.copyfile(backup_path, tmp)
    os.replace(tmp, to_p)
    # os.replace only swaps the main db file. A `-wal`/`-shm` sidecar left
    # over from whatever was previously at to_p belongs to that OLD file's
    # WAL generation, not to the just-restored content — but WAL mode
    # (connection.py: every connection sets journal_mode=WAL) replays any
    # `-wal` file it finds next to the db file regardless of whether it
    # actually matches, silently reverting the restore back to the old
    # content on first open. Drop both before anything reads to_p.
    Path(str(to_p) + "-wal").unlink(missing_ok=True)
    Path(str(to_p) + "-shm").unlink(missing_ok=True)

    problems: list[str] = []
    try:
        inspection = _inspect(to_p)
        if inspection.quick_check != "ok":
            problems.append(f"quick_check after restore: {inspection.quick_check}")
        manifest = _read_manifest(backup_path)
        if inspection.table_counts != manifest.table_counts:
            problems.append(
                f"counts after restore mismatch: {inspection.table_counts} != {manifest.table_counts}"
            )
    except sqlite3.DatabaseError as exc:
        problems.append(f"restored db failed to open: {exc}")

    return RestoreResult(ok=not problems, problems=problems)


def _load_manifests(backup_dir: str) -> list[BackupManifest]:
    out: list[BackupManifest] = []
    for mp in Path(backup_dir).glob(f"*{MANIFEST_SUFFIX}"):
        db_file = Path(str(mp)[: -len(MANIFEST_SUFFIX)])
        if not db_file.exists():
            continue
        try:
            out.append(BackupManifest.from_json(mp.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda m: m.created_at, reverse=True)
    return out


def apply_retention(backup_dir: str, retention_daily: int = 7, retention_weekly: int = 4) -> list[str]:
    """Keep the N most recent backups + one per ISO week for retention_weekly weeks.

    Only touches files with a matching manifest — an unrelated file dropped
    into backup_dir by the user is never deleted.
    """
    manifests = _load_manifests(backup_dir)
    keep = {m.filename for m in manifests[:retention_daily]}

    weekly_seen: dict[tuple[int, int], str] = {}
    for m in manifests[retention_daily:]:
        try:
            wk = datetime.fromisoformat(m.created_at).isocalendar()[:2]
        except ValueError:
            continue
        if wk not in weekly_seen and len(weekly_seen) < retention_weekly:
            weekly_seen[wk] = m.filename
    keep.update(weekly_seen.values())

    removed: list[str] = []
    for m in manifests:
        if m.filename in keep:
            continue
        db_file = Path(backup_dir) / m.filename
        db_file.unlink(missing_ok=True)
        _manifest_path(db_file).unlink(missing_ok=True)
        removed.append(m.filename)
    return removed


def latest_verified_backup(backup_dir: str) -> str | None:
    """Newest manifested backup path, or None. Caller should still verify_backup() before restore."""
    manifests = _load_manifests(backup_dir)
    if not manifests:
        return None
    return str(Path(backup_dir) / manifests[0].filename)
