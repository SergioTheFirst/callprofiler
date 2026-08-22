# -*- coding: utf-8 -*-
"""promise_outcomes.py — B3: поведенческая надёжность обещаний (det + мемоизированный LLM).

Каждое обещание (events promise/debt + legacy promises, дедуп как в A1/digest.py)
получает исход kept/late/broken/unknown через дет-эвристику по ПОЗДНЕЙШИМ сегментам
речи ТОЙ ЖЕ стороны (кто обещал) с ТЕМ ЖЕ контактом. LLM донасыщает только unknown,
только по --llm, memoized по sha1(prompt+версия) — паттерн contact_age_estimates
(age_estimate.py): det-реран без --llm переиспользует уже оплаченный LLM-результат,
не платит дважды и не откатывает статус обратно в unknown.

events/promises.status НЕ мутируются (decisions.md) — исход живёт в СВОЕЙ таблице.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import statistics
from datetime import timedelta
from pathlib import Path

from callprofiler.analyze.roles import side_of

from .age_estimate import _parse_llm_json
from .features.accommodation import _STOPWORDS
from .features.base import normalize_lemma, tokenize
from . import repository as repo_mod

log = logging.getLogger(__name__)

PROMPT_VERSION_PROMISE = "promise-v1"

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "configs" / "prompts" / "promise_outcome_v001.txt"
_DEFAULT_LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
_LLM_TIMEOUT_SEC = 120
_LLM_TEMPERATURE = 0.1
_LLM_MAX_TOKENS = 400
_LLM_CANDIDATES = 6
_LLM_CLIP_CHARS = 4000
_HALLUCINATION_PENALTY = 0.15
_LLM_CONF_RESOLVED = 0.5
_LLM_CONF_LATE = 0.35

_WINDOW_DAYS = 120
_MIN_TOKEN_LEN = 4
_CONF_ONE_WORD = 0.6
_CONF_TWO_WORDS = 0.75
_LATE_GRACE_DAYS = 2
_QUOTE_CLIP = 240

_KEPT_RATIO_HIGH = 0.8
_KEPT_RATIO_MID = 0.5
_MIN_RELIABILITY_N = 3
_DELAY_THRESHOLD_DAYS = 2

_RE_DONE = re.compile(
    r"\b(сделал|сделала|отправил|отправила|перев[ёе]л|привез|привезла|готово|"
    r"закончил|оплатил|скинул|выслал|подписал|доделал)\w*", re.I)
_RE_FAIL = re.compile(
    r"\b(не\s+смог|не\s+получилось|не\s+успел|забыл|не\s+вышло|сорвалось|отменилось)\w*", re.I)


def _content_words(text: str) -> set[str]:
    return {normalize_lemma(t) for t in tokenize(text)
            if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS}


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _parse_date(raw):
    from datetime import datetime
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10]).date()
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _side(who: str | None) -> str | None:
    """R-08: одна нормализация на все пути — live-обещания промпта (``Me``/``S2``)
    раньше не попадали в outcomes, потому что здесь понимались только
    канонические ``OWNER``/``OTHER``."""
    return side_of(who)


def _dedup_key(call_id: int, what: str | None) -> tuple:
    return (call_id, (what or "").strip().lower()[:40])


def _gather_promises(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """UNION promises+events(promise/debt), дедуп по (call_id, what[:40]) — events приоритетнее."""
    merged: dict[tuple, dict] = {}

    rows = conn.execute(
        """SELECT p.call_id, p.who, p.what, p.due AS deadline, p.contact_id,
                  COALESCE(c.call_datetime, c.created_at) AS call_date
             FROM promises p JOIN calls c ON c.call_id = p.call_id
            WHERE p.user_id = ?""",
        (user_id,),
    ).fetchall()
    for r in rows:
        side = _side(r["who"])
        if side is None:
            continue
        merged[_dedup_key(r["call_id"], r["what"])] = {
            "call_id": r["call_id"], "who": r["who"], "side": side, "what": r["what"],
            "quote": None, "deadline": r["deadline"], "contact_id": r["contact_id"],
            "call_date": r["call_date"],
        }

    rows = conn.execute(
        """SELECT e.call_id, e.who, e.payload AS what, e.source_quote AS quote,
                  e.deadline, e.contact_id,
                  COALESCE(c.call_datetime, c.created_at) AS call_date
             FROM events e JOIN calls c ON c.call_id = e.call_id
            WHERE e.user_id = ? AND e.event_type IN ('promise', 'debt')""",
        (user_id,),
    ).fetchall()
    for r in rows:
        side = _side(r["who"])
        if side is None:
            continue
        merged[_dedup_key(r["call_id"], r["what"])] = {
            "call_id": r["call_id"], "who": r["who"], "side": side, "what": r["what"],
            "quote": r["quote"], "deadline": r["deadline"], "contact_id": r["contact_id"],
            "call_date": r["call_date"],
        }

    out = []
    for item in merged.values():
        key_src = f"{item['call_id']}|{item['who']}|{(item['what'] or '').strip().lower()[:80]}"
        item["promise_key"] = hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:16]
        out.append(item)
    return out


def _evidence_window(conn: sqlite3.Connection, user_id: str, contact_id, speaker: str,
                     anchor_date) -> list:
    if contact_id is None or not anchor_date:
        return []
    return conn.execute(
        """SELECT t.text, c.call_datetime, c.call_id
             FROM transcripts t JOIN calls c ON c.call_id = t.call_id
            WHERE c.user_id = ? AND c.contact_id = ? AND t.speaker = ?
              AND c.call_datetime IS NOT NULL
              AND date(c.call_datetime) > date(?)
              AND date(c.call_datetime) <= date(?, ?)
            ORDER BY c.call_datetime, t.start_ms""",
        (user_id, contact_id, speaker, anchor_date, anchor_date, f"+{_WINDOW_DAYS} days"),
    ).fetchall()


def _resolve_det(what: str, evidence_rows: list, due: str | None) -> dict | None:
    """Первый резолвящий сегмент в хронологии → kept/late/broken. Нет матча → None (unknown)."""
    want = _content_words(what)
    if not want:
        return None
    for row in evidence_rows:
        text, call_dt, call_id = row["text"], row["call_datetime"], row["call_id"]
        overlap = want & _content_words(text)
        if not overlap:
            continue
        # ё/е ASR-дрейф (vozrast.md §11.4): регекс матчится по нормализованному тексту,
        # цитата в evidence хранится как есть (verbatim, не искажаем сохранённую речь).
        norm_text = normalize_lemma(text or "")
        done = bool(_RE_DONE.search(norm_text))
        fail = bool(_RE_FAIL.search(norm_text))
        if not done and not fail:
            continue
        confidence = _CONF_TWO_WORDS if len(overlap) >= 2 else _CONF_ONE_WORD
        evidence_date = (call_dt or "")[:10]
        quote = _truncate(text, _QUOTE_CLIP)
        if done:  # kept-матч побеждает broken при обоих (spec)
            status, days_late = "kept", None
            d_due, d_ev = _parse_date(due), _parse_date(evidence_date)
            if d_due and d_ev and d_ev > d_due + timedelta(days=_LATE_GRACE_DAYS):
                status, days_late = "late", (d_ev - d_due).days
            return {"status": status, "evidence_call_id": call_id, "evidence_date": evidence_date,
                    "evidence_quote": quote, "days_late": days_late, "confidence": confidence}
        return {"status": "broken", "evidence_call_id": call_id, "evidence_date": evidence_date,
                "evidence_quote": quote, "days_late": None, "confidence": confidence}
    return None


def _load_prompt_template() -> str | None:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("promise_outcome-промпт не найден (%s) — LLM-пасс пропущен", exc)
        return None


def _llm_candidates(what: str, evidence_rows: list) -> list[tuple]:
    want = _content_words(what)
    scored = sorted(
        ((len(want & _content_words(r["text"])), r["text"], r["call_datetime"]) for r in evidence_rows),
        key=lambda x: -x[0],
    )
    return [(t, dt) for _, t, dt in scored[:_LLM_CANDIDATES]]


def _build_llm_prompt(template: str, what: str, quote: str | None, due: str | None,
                      promise_date, evidence_rows: list) -> tuple[str, str] | None:
    cands = _llm_candidates(what, evidence_rows)
    if not cands:
        return None
    lines, total = [], 0
    for text, dt in cands:
        line = f"[{(dt or '')[:10]}] {' '.join((text or '').split())}"
        if total + len(line) > _LLM_CLIP_CHARS:
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return None
    block = "\n".join(lines)
    prompt = (template
              .replace("{date}", (promise_date or "")[:10])
              .replace("{quote_or_what}", quote or what or "")
              .replace("{due}", due or "не назван")
              .replace("{candidates}", block))
    return prompt, _norm(block)


def _call_llm(prompt: str, llm_url: str) -> str | None:
    try:
        import requests
        resp = requests.post(
            llm_url,
            json={"model": "local", "messages": [{"role": "user", "content": prompt}],
                  "temperature": _LLM_TEMPERATURE, "max_tokens": _LLM_MAX_TOKENS},
            timeout=_LLM_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 — pipeline.md Fallback: log+skip+continue
        log.warning("promise_outcome-LLM недоступен (запись остаётся unknown): %s", exc)
        return None


def _validate_llm(content: str | None, candidates_norm: str) -> dict:
    """Verbatim-гейт: невербатимная цитата → quote='', confidence -0.15 (паттерн age_estimate).

    Всегда возвращает dict (даже на провал парсинга) — мусорный ответ тоже кэшируется,
    не платим дважды за один и тот же нечитаемый ответ (age_estimate.py прецедент).
    """
    out = {"status": "unknown", "quote": "", "days_late": None, "confidence": 0.0}
    parsed = _parse_llm_json(content or "")
    if not parsed:
        return out
    status = parsed.get("status")
    if status not in ("kept", "late", "broken", "unknown"):
        return out
    quote = str(parsed.get("quote") or "").strip()
    try:
        days_late = int(parsed["days_late"]) if parsed.get("days_late") is not None else None
    except (TypeError, ValueError):
        days_late = None
    confidence = _LLM_CONF_LATE if status == "late" else (
        _LLM_CONF_RESOLVED if status in ("kept", "broken") else 0.2)
    if quote and _norm(quote) not in candidates_norm:
        quote = ""
        confidence = max(0.05, confidence - _HALLUCINATION_PENALTY)
    out.update(status=status, quote=quote[:_QUOTE_CLIP], days_late=days_late,
               confidence=round(confidence, 2))
    return out


def run_promise_outcomes(conn: sqlite3.Connection, user_id: str, *, use_llm: bool = False,
                         llm_url: str | None = None, llm_limit: int = 200) -> dict:
    """Идемпотентно (UPSERT по promise_key). LLM только для unknown, только --llm."""
    repo_mod.apply_insight_schema(conn)
    llm_url = llm_url or _DEFAULT_LLM_URL
    promises = _gather_promises(conn, user_id)
    stats = {"promises": len(promises), "kept": 0, "late": 0, "broken": 0,
             "unknown": 0, "llm_called": 0, "llm_cached": 0}

    template = _load_prompt_template() if use_llm else None

    for p in promises:
        speaker = "OWNER" if p["side"] == "owner" else "OTHER"
        evidence_rows = _evidence_window(conn, user_id, p["contact_id"], speaker, p["call_date"])

        det = _resolve_det(p["what"], evidence_rows, p["deadline"])
        if det is None:
            status, evidence_call_id, evidence_date, evidence_quote, days_late, confidence = (
                "unknown", None, None, None, None, 0.0)
        else:
            status = det["status"]
            evidence_call_id, evidence_date = det["evidence_call_id"], det["evidence_date"]
            evidence_quote, days_late, confidence = (
                det["evidence_quote"], det["days_late"], det["confidence"])
        method = "det"

        existing = conn.execute(
            "SELECT status, method, llm_prompt_hash, llm_result FROM promise_outcomes "
            "WHERE user_id = ? AND promise_key = ?",
            (user_id, p["promise_key"])).fetchone()

        llm_hash = existing["llm_prompt_hash"] if existing else None
        llm_result_store = existing["llm_result"] if existing else None
        prompt_version = PROMPT_VERSION_PROMISE if llm_result_store else None

        if status == "unknown" and use_llm and template:
            built = _build_llm_prompt(template, p["what"], p["quote"], p["deadline"],
                                      p["call_date"], evidence_rows)
            if built is not None:
                prompt, cands_norm = built
                new_hash = hashlib.sha1(
                    (prompt + PROMPT_VERSION_PROMISE).encode("utf-8")).hexdigest()
                if existing and existing["llm_prompt_hash"] == new_hash and existing["llm_result"]:
                    llm_result_store, llm_hash = existing["llm_result"], new_hash
                    stats["llm_cached"] += 1
                elif stats["llm_called"] < llm_limit:
                    content = _call_llm(prompt, llm_url)
                    if content is not None:
                        stats["llm_called"] += 1
                        validated = _validate_llm(content, cands_norm)
                        llm_result_store = json.dumps(validated, ensure_ascii=False)
                        llm_hash = new_hash

        if status == "unknown" and llm_result_store:
            try:
                parsed = json.loads(llm_result_store)
            except json.JSONDecodeError:
                parsed = None
            if parsed and parsed.get("status") != "unknown":
                status = parsed["status"]
                evidence_quote = parsed.get("quote") or None
                days_late = parsed.get("days_late")
                confidence = parsed.get("confidence", 0.5)
                method = "llm"
                prompt_version = PROMPT_VERSION_PROMISE

        stats[status] += 1
        repo_mod.save_promise_outcome(
            conn, user_id, promise_key=p["promise_key"], contact_id=p["contact_id"],
            call_id=p["call_id"], side=p["side"], what=p["what"], due=p["deadline"],
            status=status, evidence_call_id=evidence_call_id, evidence_date=evidence_date,
            evidence_quote=evidence_quote, days_late=days_late, method=method,
            confidence=confidence, llm_prompt_hash=llm_hash, llm_result=llm_result_store,
            prompt_version=prompt_version)

    conn.commit()
    return stats


def _day_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def _delay_phrase(median_days: float) -> str | None:
    n = round(median_days)
    if n <= _DELAY_THRESHOLD_DAYS:
        return None
    if 5 <= n <= 9:
        return "обычно с опозданием около недели"
    if 10 <= n <= 18:
        return "обычно с опозданием около двух недель"
    return f"обычно с опозданием около {n} {_day_word(n)}"


def contact_reliability(conn: sqlite3.Connection, user_id: str, contact_id: int) -> dict | None:
    """{kept_ratio, n, median_delay_days, phrase} по стороне 'contact' (обещания контакта
    владельцу — источник, чья надёжность оценивается). n<3 -> None (не показываем)."""
    rows = conn.execute(
        """SELECT status, days_late FROM promise_outcomes
            WHERE user_id = ? AND contact_id = ? AND side = 'contact'
              AND status IN ('kept', 'late', 'broken')""",
        (user_id, contact_id)).fetchall()
    n = len(rows)
    if n < _MIN_RELIABILITY_N:
        return None
    kept = sum(1 for r in rows if r["status"] == "kept")
    kept_ratio = kept / n
    late_days = [r["days_late"] for r in rows if r["status"] == "late" and r["days_late"] is not None]
    median_delay = statistics.median(late_days) if late_days else None

    if kept_ratio >= _KEPT_RATIO_HIGH:
        phrase = "держит слово"
    elif kept_ratio >= _KEPT_RATIO_MID:
        phrase = "держит слово через раз"
    else:
        phrase = "чаще не выполняет обещанное"

    delay_note = _delay_phrase(median_delay) if median_delay is not None else None
    if delay_note:
        phrase = f"{phrase}; {delay_note}"

    return {"kept_ratio": round(kept_ratio, 2), "n": n,
            "median_delay_days": median_delay, "phrase": phrase}
