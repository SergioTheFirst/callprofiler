# -*- coding: utf-8 -*-
"""
doctor.py — преполётная проверка окружения/схемы (M1, ozalup2.md §3.1).

Ловит целый класс env/schema-крашей из bugs.md одной командой ДО прогона на
боксе: psutil (2026-07-02), Python 3.14 (B1), HF_TOKEN-мусор (2026-06-04),
`no such column` (2026-07-02). Каждый чек изолирован try/except — сбой
одного чека не валит остальные (FAIL с текстом исключения).
"""

from __future__ import annotations

import importlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Критичные колонки по таблицам (M1 §3.1 п.1 db-schema).
_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "calls": ("call_id", "user_id", "status", "pipeline_stage", "audio_path",
              "error_message", "contact_id", "call_datetime"),
    "transcripts": ("call_id", "speaker", "text", "start_ms", "end_ms"),
    "analyses": ("call_id", "prompt_version", "feedback", "risk_score"),
    "contacts": ("contact_id", "user_id"),
    "users": ("user_id", "incoming_dir"),
    "events": ("user_id", "event_type", "who", "status"),
}
# Опциональные слои — их отсутствие легитимно (не запускали ещё этот пасс).
_OPTIONAL_LAYERS: tuple[str, ...] = (
    "contact_age_style", "entities", "bio_scenes", "contact_archetypes",
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # 'OK' | 'FAIL' | 'WARN' | 'SKIP'
    detail: str


def _safe(name: str, fn) -> Check:
    """Обернуть чек: любое исключение внутри -> FAIL с текстом, не краш doctor."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — doctor не должен падать сам
        return Check(name, "FAIL", f"чек упал: {exc}")


def _check_python() -> Check:
    import sys
    v = sys.version_info
    if v < (3, 10):
        return Check("python", "FAIL", f"Python {v.major}.{v.minor} слишком старый, нужен 3.10-3.12")
    if v >= (3, 13):
        return Check("python", "FAIL",
                      f"Python {v.major}.{v.minor} — CUDA-колёс PyTorch нет, нужен Python 3.12 (bugs.md B1)")
    return Check("python", "OK", f"Python {v.major}.{v.minor}.{v.micro}")


def _check_deps_core() -> Check:
    missing = []
    for mod in ("numpy", "requests", "fastapi", "uvicorn", "psutil"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        hint = "; ".join(f"pip install {m}" for m in missing)
        extra = " (psutil — краш /api/system, bugs.md 2026-07-02)" if "psutil" in missing else ""
        return Check("deps-core", "FAIL", f"нет модулей: {', '.join(missing)} — {hint}{extra}")
    return Check("deps-core", "OK", "numpy/requests/fastapi/uvicorn/psutil установлены")


def _check_deps_gpu() -> Check:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return Check("deps-gpu", "WARN", "torch не установлен — норма для дев-ПК; на боксе: requirements-gigaam.txt")
    if not torch.cuda.is_available():
        return Check("deps-gpu", "FAIL", "torch без CUDA — GigaAM обязателен GPU (Hard Constraint)")
    return Check("deps-gpu", "OK", f"CUDA доступна ({torch.cuda.get_device_name(0)})")


def _check_deps_roles() -> Check:
    missing = []
    for mod in ("pyannote.audio", "librosa", "soundfile"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return Check("deps-roles", "WARN",
                      f"нет модулей: {', '.join(missing)} — роли будут UNKNOWN; install-roles.bat")
    return Check("deps-roles", "OK", "pyannote.audio/librosa/soundfile установлены")


def _check_ffmpeg() -> Check:
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([tool, "-version"], capture_output=True, timeout=10, check=False)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return Check("ffmpeg", "FAIL", f"{tool} не найден в PATH")
    return Check("ffmpeg", "OK", "ffmpeg/ffprobe найдены")


def _check_env_hf() -> Check:
    raw = os.environ.get("HF_TOKEN", "")
    if raw.startswith("${") or raw.startswith("%"):
        return Check("env-hf", "FAIL", f"незаэкспанженная переменная HF_TOKEN={raw!r} (bugs.md 2026-06-04)")
    if not raw:
        return Check("env-hf", "WARN", "HF_TOKEN не задан — роли/gated-модели pyannote не скачаются")
    return Check("env-hf", "OK", "HF_TOKEN задан")


def _check_env_tg() -> Check:
    if not os.environ.get("TELEGRAM_BOT_TOKEN", ""):
        return Check("env-tg", "WARN", "TELEGRAM_BOT_TOKEN не задан — digest --send не сработает")
    return Check("env-tg", "OK", "TELEGRAM_BOT_TOKEN задан")


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".doctor_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _check_paths(config: Any, conn) -> Check:
    data_dir = getattr(config, "data_dir", "") or ""
    if not data_dir:
        return Check("paths", "FAIL", "data_dir не задан в конфиге")
    dd = Path(data_dir)
    if not dd.exists():
        return Check("paths", "FAIL", f"data_dir не существует: {data_dir}")
    if not _writable(dd):
        return Check("paths", "FAIL", f"data_dir не писабелен: {data_dir}")

    db_path = dd / "db" / "callprofiler.db"
    if not db_path.exists():
        return Check("paths", "FAIL", f"файл БД не найден: {db_path}")

    if conn is not None:
        rows = conn.execute("SELECT user_id, incoming_dir FROM users").fetchall()
        missing = [r["user_id"] for r in rows if not Path(r["incoming_dir"]).exists()]
        if missing:
            return Check("paths", "FAIL", f"incoming_dir не существует у users: {', '.join(missing)}")

    return Check("paths", "OK", f"data_dir={data_dir}, БД на месте")


def _check_models(config: Any, conn) -> Check:
    models = getattr(config, "models", None)
    if models is not None and getattr(models, "asr_backend", "") == "gigaam":
        model_dir = Path(models.gigaam_model_dir or "")
        if not models.gigaam_model_dir or not model_dir.exists():
            return Check("models", "FAIL", f"gigaam_model_dir не найден: {models.gigaam_model_dir!r}")
        if not (model_dir / "config.json").exists():
            return Check("models", "FAIL", f"нет config.json в gigaam_model_dir: {model_dir}")

    warn = ""
    if conn is not None:
        rows = conn.execute("SELECT user_id, ref_audio FROM users").fetchall()
        missing = [r["user_id"] for r in rows if not r["ref_audio"] or not Path(r["ref_audio"]).exists()]
        if missing:
            warn = f"ref_audio отсутствует у users: {', '.join(missing)} — owner-роль не определится"

    if warn:
        return Check("models", "WARN", warn)
    return Check("models", "OK", "модели/ref_audio на месте")


def _check_db_schema(conn) -> Check:
    if conn is None:
        return Check("db-schema", "SKIP", "нет соединения с БД")

    problems = []
    for table, columns in _REQUIRED_COLUMNS.items():
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            problems.append(f"{table} (таблица отсутствует)")
            continue
        have = {r["name"] for r in rows}
        for col in columns:
            if col not in have:
                problems.append(f"{table}.{col}")

    if problems:
        return Check("db-schema", "FAIL", f"отсутствуют: {', '.join(problems)}")

    layers = []
    for table in _OPTIONAL_LAYERS:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchall()
        layers.append(f"{table}={'есть' if rows else 'нет'}")
    return Check("db-schema", "OK", "все критичные колонки на месте; слои: " + ", ".join(layers))


def _check_db_wal(conn) -> Check:
    if conn is None:
        return Check("db-wal", "SKIP", "нет соединения с БД")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    if str(mode).lower() != "wal":
        return Check("db-wal", "WARN", f"journal_mode={mode} — дашборд real-time требует WAL (bugs.md 2026-06-04)")
    return Check("db-wal", "OK", "journal_mode=wal")


def _check_llm(config: Any) -> Check:
    import requests

    llm_url = getattr(getattr(config, "models", None), "llm_url", "") or ""
    base = llm_url.split("/v1/")[0] if "/v1/" in llm_url else llm_url
    if not base:
        return Check("llm", "WARN", "llm_url не задан")
    try:
        resp = requests.get(base.rstrip("/") + "/health", timeout=2)
        if resp.status_code == 200:
            return Check("llm", "OK", f"llama-server отвечает на {base}")
        return Check("llm", "WARN", f"llama-server вернул {resp.status_code} на {base}")
    except requests.exceptions.ConnectionError:
        return Check("llm", "WARN", "llama-server не запущен — норма вне LLM-окна (GPU sequential)")
    except Exception as exc:  # noqa: BLE001
        return Check("llm", "WARN", f"llm-проба не удалась: {exc}")


def run_checks(config: Any, conn=None) -> list[Check]:
    """Прогнать все преполётные чеки. conn=None -> db-* блоки SKIP."""
    return [
        _safe("python", _check_python),
        _safe("deps-core", _check_deps_core),
        _safe("deps-gpu", _check_deps_gpu),
        _safe("deps-roles", _check_deps_roles),
        _safe("ffmpeg", _check_ffmpeg),
        _safe("env-hf", _check_env_hf),
        _safe("env-tg", _check_env_tg),
        _safe("paths", lambda: _check_paths(config, conn)),
        _safe("models", lambda: _check_models(config, conn)),
        _safe("db-schema", lambda: _check_db_schema(conn)),
        _safe("db-wal", lambda: _check_db_wal(conn)),
        _safe("llm", lambda: _check_llm(config)),
    ]


def format_report(checks: list[Check]) -> str:
    """Выровненная таблица, <=1 строка на чек."""
    icon = {"OK": "🟢", "WARN": "🟡", "FAIL": "🔴", "SKIP": "⚪"}
    width = max((len(c.name) for c in checks), default=4)
    lines = [
        f"{icon.get(c.status, '?')} {c.name.ljust(width)}  {c.status:<4}  {c.detail}"
        for c in checks
    ]
    return "\n".join(lines)
