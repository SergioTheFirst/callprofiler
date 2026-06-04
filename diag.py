# -*- coding: utf-8 -*-
"""
diag.py — собрать диагностику CallProfiler для разработчика. ТОЛЬКО ЧТЕНИЕ.

Запуск через diag.bat (пишет в C:\\Users\\SERGE\\Desktop\\diag.txt).
Каждая секция в своём try/except — скрипт всегда доходит до конца.
"""
import glob
import importlib
import os
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path
from shutil import which

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = r"C:\calls\data\db\callprofiler.db"
DB_STALE = r"C:\calls\data\callprofiler.db"
TEXT = r"C:\calls\text"
INCOMING = r"C:\calls\in"
MODEL = r"C:\models\GigaAM-v3-rnnt"
PROJECT = r"C:\pro\callprofiler"


def hr(title):
    print("\n" + "=" * 72)
    print("  " + title)
    print("=" * 72)


def section(title, fn):
    hr(title)
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        print("!! секция упала:", type(e).__name__, e)
        traceback.print_exc()


# ── 1. ENVIRONMENT ──────────────────────────────────────────────────────
def env():
    print("python      :", sys.version.replace("\n", " "))
    print("executable  :", sys.executable)
    for mod in ["torch", "torchaudio", "transformers", "pyannote.audio",
                "numpy", "hydra", "omegaconf", "sentencepiece",
                "fastapi", "uvicorn", "jinja2", "soundfile", "librosa"]:
        try:
            m = importlib.import_module(mod)
            print(f"{mod:16}: {getattr(m, '__version__', '?')}")
        except Exception as e:  # noqa: BLE001
            print(f"{mod:16}: НЕ УСТАНОВЛЕН ({type(e).__name__})")
    try:
        import torch
        print("CUDA available :", torch.cuda.is_available())
        if torch.cuda.is_available():
            print("GPU            :", torch.cuda.get_device_name(0))
    except Exception as e:  # noqa: BLE001
        print("torch CUDA check err:", e)
    print("ffmpeg in PATH :", which("ffmpeg") or "НЕТ")
    print("HF_TOKEN env   :", "ЗАДАН" if os.environ.get("HF_TOKEN") else "НЕ ЗАДАН")


# ── 2. GIT ──────────────────────────────────────────────────────────────
def git():
    for cmd in (["git", "rev-parse", "--abbrev-ref", "HEAD"],
                ["git", "rev-parse", "--short", "HEAD"],
                ["git", "log", "-1", "--oneline"],
                ["git", "status", "--short"]):
        try:
            out = subprocess.run(cmd, cwd=PROJECT, capture_output=True,
                                 text=True, timeout=15)
            txt = (out.stdout or out.stderr).strip()
            print("$", " ".join(cmd[1:]), "->", txt[:400] if txt else "(пусто)")
        except Exception as e:  # noqa: BLE001
            print("git err:", e)


# ── 3. DB ───────────────────────────────────────────────────────────────
def _q(con, sql, args=()):
    try:
        return con.execute(sql, args).fetchall()
    except Exception as e:  # noqa: BLE001
        print("  SQL err:", e, "|", sql[:60])
        return []


def db():
    print("DB main :", DB, "| exists:", os.path.exists(DB),
          "| size:", (os.path.getsize(DB) if os.path.exists(DB) else 0))
    print("DB stale:", DB_STALE, "| exists:", os.path.exists(DB_STALE),
          "| size:", (os.path.getsize(DB_STALE) if os.path.exists(DB_STALE) else 0))
    if not os.path.exists(DB):
        print("!! основной DB не найден")
        return
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    print("\n-- calls по status --")
    for r in _q(con, "SELECT status, COUNT(*) c FROM calls GROUP BY status ORDER BY c DESC"):
        print(f"  {r['status']:14}: {r['c']}")

    print("\n-- error: распределение pipeline_stage --")
    for r in _q(con, "SELECT pipeline_stage s, COUNT(*) c FROM calls WHERE status='error' GROUP BY pipeline_stage ORDER BY s"):
        print(f"  stage {r['s']}: {r['c']}")

    print("\n-- error: распределение retry_count --")
    for r in _q(con, "SELECT retry_count rc, COUNT(*) c FROM calls WHERE status='error' GROUP BY retry_count ORDER BY rc"):
        print(f"  retry {r['rc']}: {r['c']}")

    print("\n-- error_message: ТОП причин (почему упали) --")
    for r in _q(con, "SELECT COALESCE(error_message,'(null)') em, COUNT(*) c FROM calls WHERE status='error' GROUP BY em ORDER BY c DESC LIMIT 15"):
        print(f"  [{r['c']:5}] {str(r['em'])[:240]}")

    print("\n-- 5 свежих error-звонков (есть ли файлы на диске) --")
    for r in _q(con, "SELECT call_id, source_filename, audio_path, norm_path, pipeline_stage, retry_count, error_message FROM calls WHERE status='error' ORDER BY updated_at DESC LIMIT 5"):
        ap = r["audio_path"] or ""
        npth = r["norm_path"] or ""
        print(f"  call_id={r['call_id']} stage={r['pipeline_stage']} retry={r['retry_count']}")
        print(f"     source : {r['source_filename']}")
        print(f"     audio  : {ap}")
        print(f"              exists={os.path.exists(ap) if ap else 'n/a'}")
        print(f"     norm   : {npth} exists={os.path.exists(npth) if npth else 'n/a'}")
        print(f"     ERROR  : {str(r['error_message'])[:240]}")

    print("\n-- normalizing(зависшие): распределение stage --")
    for r in _q(con, "SELECT pipeline_stage s, COUNT(*) c FROM calls WHERE status='normalizing' GROUP BY pipeline_stage ORDER BY s"):
        print(f"  stage {r['s']}: {r['c']}")

    print("\n-- users --")
    for r in _q(con, "SELECT user_id, incoming_dir, ref_audio FROM users"):
        ra = r["ref_audio"] or ""
        print(f"  {r['user_id']}: incoming={r['incoming_dir']}")
        print(f"     ref_audio={ra} exists={os.path.exists(ra) if ra else 'НЕТ'}")

    print("\n-- transcripts: распределение speaker (есть ли роли) --")
    for r in _q(con, "SELECT speaker, COUNT(*) c FROM transcripts GROUP BY speaker ORDER BY c DESC"):
        print(f"  {r['speaker']}: {r['c']}")
    con.close()


# ── 4. FILES ────────────────────────────────────────────────────────────
def files():
    inc = glob.glob(INCOMING + r"\**\*.*", recursive=True)
    audio_ext = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac", ".aac", ".wma"}
    inc_audio = [p for p in inc if Path(p).suffix.lower() in audio_ext]
    print("incoming аудио (рекурсивно):", len(inc_audio))
    for p in inc_audio[:3]:
        print("   ", p)
    txts = glob.glob(TEXT + r"\*.txt")
    print("text файлов (.txt):", len(txts))
    if txts:
        p = txts[0]
        print("пример .txt:", p)
        try:
            for ln in Path(p).read_text(encoding="utf-8", errors="replace").splitlines()[:8]:
                print("    |", ln[:120])
        except Exception as e:  # noqa: BLE001
            print("read err:", e)


# ── 5. MODEL FILE STATE ─────────────────────────────────────────────────
def model_file():
    mf = Path(MODEL) / "modeling_gigaam.py"
    print("modeling_gigaam.py:", mf, "| exists:", mf.exists())
    if mf.exists():
        try:
            lines = mf.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, ln in enumerate(lines[275:295], start=276):
                if "pyannote" in ln or "import" in ln.lower():
                    print(f"   {i}: {ln.rstrip()[:110]}")
        except Exception as e:  # noqa: BLE001
            print("read err:", e)


# ── 6. GIGAAM LOAD TEST (тяжёлый, ~20-60с) ──────────────────────────────
def gigaam():
    try:
        import torch
        from transformers import AutoModel
    except Exception as e:  # noqa: BLE001
        print("импорт torch/transformers не удался:", e)
        return
    print("грузим", MODEL, "(check_imports + weights_only обходы как в runner)...")
    try:
        import transformers.dynamic_module_utils as dmu
        if hasattr(dmu, "get_relative_imports"):
            dmu.check_imports = dmu.get_relative_imports
    except Exception:
        pass
    _ol = torch.load
    torch.load = lambda *a, **k: _ol(*a, **{**k, "weights_only": False})
    try:
        m = AutoModel.from_pretrained(MODEL, trust_remote_code=True)
        print("OK загружена:", type(m).__name__, "| asr:", type(m.model).__name__)
        if torch.cuda.is_available():
            m = m.to("cuda").eval()
            print("перенос на CUDA: OK")
        else:
            print("CUDA нет — модель на CPU")
    except Exception as e:  # noqa: BLE001
        print("!! ЗАГРУЗКА GIGAAM УПАЛА:", type(e).__name__, e)
        traceback.print_exc()
    finally:
        torch.load = _ol


if __name__ == "__main__":
    print("CallProfiler diagnostics")
    section("1. ENVIRONMENT", env)
    section("2. GIT", git)
    section("3. DATABASE", db)
    section("4. FILES (incoming / text)", files)
    section("5. MODEL FILE (modeling_gigaam.py imports)", model_file)
    section("6. GIGAAM LOAD TEST", gigaam)
    print("\n=== END OF DIAGNOSTICS ===")
