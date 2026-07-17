# -*- coding: utf-8 -*-
"""quarterly.py — D3: квартальный отчёт о социальной вселенной.

gather_aggregates — ТОЛЬКО агрегаты (STRATEGIC_PLAN D3): никаких транскриптов
идут в LLM, только числа/имена/даты. build_report кэширует по (user_id, period,
prompt_version) в insight_reports — второй вызов без --force не зовёт LLM.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import requests

from . import repository as repo

log = logging.getLogger(__name__)

PROMPT_VERSION_QREPORT = "qreport-v1"
_PROMPT_PATH = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "quarterly_v001.txt"
_DEFAULT_LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
_LLM_TIMEOUT_SEC = 120
_LLM_TEMPERATURE = 0.4
_LLM_MAX_TOKENS = 2000
_DATA_CLIP_CHARS = 7000
_REPORTS_DIR = Path(r"C:\calls\reports")

RISK_SHIFT_THRESHOLD = 15.0
RELIABILITY_MIN_SAMPLE = 3
_TOP_RISERS_FALLERS = 8
_TOP_NEW_PEOPLE = 8
_TOP_OLDEST_OVERDUE = 3
_TOP_DORMANT = 5


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _quarter_bounds(period: str) -> tuple[date, date]:
    year_s, q_s = period.split("-Q")
    year, q = int(year_s), int(q_s)
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    end = date(year, 12, 31) if end_month == 12 else date(year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def _prev_period(period: str) -> str:
    year_s, q_s = period.split("-Q")
    year, q = int(year_s), int(q_s)
    return f"{year - 1}-Q4" if q == 1 else f"{year}-Q{q - 1}"


def gather_aggregates(conn: sqlite3.Connection, user_id: str, period: str) -> dict:
    """Только числа/имена/даты — НИКАКИХ транскриптов (STRATEGIC_PLAN D3)."""
    start, end = _quarter_bounds(period)
    prev_start, prev_end = _quarter_bounds(_prev_period(period))

    def _calls_by_contact(lo: date, hi: date) -> dict[int, int]:
        rows = conn.execute(
            """SELECT contact_id, COUNT(*) AS n FROM calls
                WHERE user_id = ? AND contact_id IS NOT NULL
                  AND date(call_datetime) BETWEEN ? AND ?
                GROUP BY contact_id""",
            (user_id, lo.isoformat(), hi.isoformat()),
        ).fetchall()
        return {r["contact_id"]: r["n"] for r in rows}

    def _avg_risk_by_contact(lo: date, hi: date) -> dict[int, float]:
        rows = conn.execute(
            """SELECT c.contact_id AS contact_id, AVG(a.risk_score) AS avg_risk
                 FROM calls c JOIN analyses a ON a.call_id = c.call_id
                WHERE c.user_id = ? AND c.contact_id IS NOT NULL
                  AND date(c.call_datetime) BETWEEN ? AND ?
                GROUP BY c.contact_id""",
            (user_id, lo.isoformat(), hi.isoformat()),
        ).fetchall()
        return {r["contact_id"]: r["avg_risk"] for r in rows if r["avg_risk"] is not None}

    def _name(cid: int) -> str:
        row = conn.execute(
            "SELECT COALESCE(display_name, guessed_name, phone_e164, '?') AS name "
            "FROM contacts WHERE contact_id = ? AND user_id = ?",
            (cid, user_id),
        ).fetchone()
        return row["name"] if row else "?"

    cur_calls = _calls_by_contact(start, end)
    prev_calls = _calls_by_contact(prev_start, prev_end)
    deltas = []
    for cid in set(cur_calls) | set(prev_calls):
        d = cur_calls.get(cid, 0) - prev_calls.get(cid, 0)
        if d != 0:
            deltas.append({"contact_id": cid, "name": _name(cid), "delta": d,
                            "direction": "riser" if d > 0 else "faller"})
    deltas.sort(key=lambda x: abs(x["delta"]), reverse=True)
    risers_fallers = deltas[:_TOP_RISERS_FALLERS]

    cur_risk = _avg_risk_by_contact(start, end)
    prev_risk = _avg_risk_by_contact(prev_start, prev_end)
    risk_shifts = []
    for cid in set(cur_risk) & set(prev_risk):
        d = cur_risk[cid] - prev_risk[cid]
        if abs(d) >= RISK_SHIFT_THRESHOLD:
            risk_shifts.append({"contact_id": cid, "name": _name(cid),
                                 "delta": round(d, 1), "sign": "+" if d > 0 else "-"})
    risk_shifts.sort(key=lambda x: abs(x["delta"]), reverse=True)

    new_people = []
    if _has_table(conn, "entities"):
        rows = conn.execute(
            """SELECT canonical_name, created_at FROM entities
                WHERE user_id = ? AND UPPER(entity_type) = 'PERSON'
                  AND date(created_at) BETWEEN ? AND ?
                ORDER BY created_at DESC LIMIT ?""",
            (user_id, start.isoformat(), end.isoformat(), _TOP_NEW_PEOPLE),
        ).fetchall()
        new_people = [{"name": r["canonical_name"], "created_at": r["created_at"]} for r in rows]

    from callprofiler.deliver.digest import overdue_items
    overdue = overdue_items(conn, user_id, today=end.isoformat())
    unresolved = {
        "owner_count": sum(1 for i in overdue if i["side"] == "owner"),
        "contact_count": sum(1 for i in overdue if i["side"] == "contact"),
        "oldest": [
            {"name": i["contact_name"], "what": (i["what"] or "")[:100],
             "deadline": i["deadline"], "days_overdue": i["days_overdue"]}
            for i in overdue[:_TOP_OLDEST_OVERDUE]
        ],
    }

    from .dormancy import dormant_valuable
    dormant = dormant_valuable(conn, user_id, today=end, top=_TOP_DORMANT)

    result: dict = {
        "period": period, "risers_fallers": risers_fallers, "risk_shifts": risk_shifts,
        "new_people": new_people, "unresolved": unresolved, "dormant": dormant,
    }

    if _has_table(conn, "promise_outcomes"):
        rows = conn.execute(
            """SELECT contact_id, status, COUNT(*) AS n FROM promise_outcomes
                WHERE user_id = ? AND contact_id IS NOT NULL
                GROUP BY contact_id, status""",
            (user_id,),
        ).fetchall()
        by_contact: dict[int, dict[str, int]] = {}
        for r in rows:
            by_contact.setdefault(r["contact_id"], {})[r["status"]] = r["n"]
        reliability = []
        for cid, counts in by_contact.items():
            kept, broken = counts.get("kept", 0), counts.get("broken", 0)
            total = kept + broken
            if total < RELIABILITY_MIN_SAMPLE:
                continue
            reliability.append({"contact_id": cid, "name": _name(cid),
                                 "kept_ratio": round(kept / total, 2), "n": total})
        reliability.sort(key=lambda x: x["kept_ratio"])
        result["reliability_shifts"] = (
            reliability[:3] + reliability[-3:] if len(reliability) > 6 else reliability
        )

    return result


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _prompt_hash(period: str, data_json: str) -> str:
    raw = f"{period}|{PROMPT_VERSION_QREPORT}|{data_json}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def build_report(
    conn: sqlite3.Connection, user_id: str, period: str, *,
    llm_url: str = _DEFAULT_LLM_URL, timeout: int = _LLM_TIMEOUT_SEC, force: bool = False,
    reports_dir: str | Path | None = None,
) -> dict:
    """Кэш по (user_id, period, prompt_version); --force игнорирует кэш и пересчитывает.

    ``reports_dir`` переопределяет ``C:\\calls\\reports`` (тесты — dev-машина без
    реального C:\\calls, CLAUDE.md dev/run split).

    Raises:
        RuntimeError: llama-server недоступен (CLI ловит и делает exit 2).
    """
    repo.apply_insight_schema(conn)

    if not force:
        row = conn.execute(
            "SELECT body_md, created_at FROM insight_reports "
            "WHERE user_id = ? AND period = ? AND prompt_version = ?",
            (user_id, period, PROMPT_VERSION_QREPORT),
        ).fetchone()
        if row:
            return {"body_md": row["body_md"], "cached": True, "created_at": row["created_at"]}

    aggregates = gather_aggregates(conn, user_id, period)
    data_json = json.dumps(aggregates, ensure_ascii=False, default=str)[:_DATA_CLIP_CHARS]
    prompt = _load_prompt_template().replace("{data_json}", data_json)
    phash = _prompt_hash(period, data_json)

    try:
        resp = requests.post(
            llm_url,
            json={"model": "local", "messages": [{"role": "user", "content": prompt}],
                  "temperature": _LLM_TEMPERATURE, "max_tokens": _LLM_MAX_TOKENS},
            timeout=timeout,
        )
        resp.raise_for_status()
        body_md = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 — единая точка входа, оборачиваем в RuntimeError
        raise RuntimeError(f"llama-server недоступен: {exc}") from exc

    conn.execute(
        """INSERT OR REPLACE INTO insight_reports
               (user_id, period, prompt_version, prompt_hash, body_md)
           VALUES (?,?,?,?,?)""",
        (user_id, period, PROMPT_VERSION_QREPORT, phash, body_md),
    )
    conn.commit()

    out_path = Path(reports_dir or _REPORTS_DIR) / f"{user_id}-{period}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body_md, encoding="utf-8")

    return {"body_md": body_md, "cached": False, "path": str(out_path)}
