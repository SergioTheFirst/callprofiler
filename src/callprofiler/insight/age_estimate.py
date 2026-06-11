# -*- coding: utf-8 -*-
"""Агрегатор оценки возраста контакта (план 2026-06-11-age-estimation).

Трёхступенчато по убыванию точности: маркеры → реляционные якоря → LLM-пасс
(только по флагу use_llm, в LLM-окне). Агрегация в пространстве ГОДА РОЖДЕНИЯ:
возраст выводится к reference-дате, оценка не протухает между ежедневными
пересчётами (динамика данных). Конфликт: высший класс точности побеждает,
confidence падает (min+10); LLM никогда не двигает детерминированный интервал.

LLM-результат memoized per-contact (llm_prompt_hash в строке — паттерн сигнатуры
психопрофайлера): det-пересчёт (autofit/CLI без --llm) переиспользует оплаченный
LLM-сигнал, не дёргая сервер. Дашборд эту таблицу только читает.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path

from .age_markers import AgeSignal, extract_marker_signals, extract_relation_signals

log = logging.getLogger(__name__)

PROMPT_VERSION_AGE = "age-v1"  # bump → инвалидация llm-кэша (llm.md/biography-паттерн)

_DEFAULT_LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
_LLM_TIMEOUT_SEC = 120          # llm.md
_LLM_MAX_TOKENS = 800           # JSON-ответ маленький; Qwen3.5 16k ctx
_LLM_TEMPERATURE = 0.1          # извлечение, не творчество
_LLM_LEX_CONF_CAP = 50          # лексика/реалии — слабый сигнал (план: conf 25-50)
_LLM_CONFLICT_PENALTY = 15      # LLM противоречит детерминированному → conf падает
_HALLUCINATION_PENALTY = 15     # за каждую невербатимную цитату (план Ф2)
_REPLICA_LIMIT = 40             # топ самых длинных реплик контакта в промпт
_REPLICA_CLIP = 6000            # символов реплик в промпт (вписывается в 16k ctx)
_OWNER_ADDR_LIMIT = 10
_EVIDENCE_CAP = 8
_CONF_CAP = 95                  # потолок итоговой уверенности (план)

# Класс точности сигнала: конфликт решается в пользу высшего класса
_PRIORITY = {
    "direct_age": 3, "birth_year": 3, "jubilee": 3,
    "pension": 2, "grandkids": 2, "army_done": 2, "student": 2,
    "school_exam": 2, "school_finish": 2,
}

# Возрастно-информативные обращения владельца (идут в LLM-контекст)
_RE_ADDR = re.compile(
    r"молодой\s+человек|девушк|бабул|дедул|\bмам\b|\bпап\b|сынок|доч[ка]|"
    r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна)\b")


def _prio(s: AgeSignal) -> int:
    if s.method == "llm":
        return 0
    return _PRIORITY.get(s.signal, 1)  # relation-якоря → класс 1


def _overlap(bl, bh, s: AgeSignal) -> bool:
    return s.birth_low <= bh and s.birth_high >= bl


def _aggregate(signals: list[AgeSignal]) -> dict | None:
    """Сигналы → итоговый интервал года рождения + confidence + evidence.

    Правила плана: max conf + 10 за каждый согласный независимый сигнал (cap 95);
    конфликт внутри класса → конверт диапазонов и conf=min+10; конфликт ниже
    классом → высший побеждает, conf=min+10; LLM при конфликте отбрасывается
    из интервала с −15 к conf.
    """
    dets = [s for s in signals if s.method != "llm"]
    llms = [s for s in signals if s.method == "llm"]
    if not dets and not llms:
        return None

    contributing: list[AgeSignal] = []
    methods: set[str] = set()
    bl = bh = None
    conf = 0

    if dets:
        top = max(_prio(s) for s in dets)
        core = [s for s in dets if _prio(s) == top]
        rest = [s for s in dets if _prio(s) < top]
        # стабильный tie-break → идемпотентность при равных confidence
        base = max(core, key=lambda s: (s.confidence, s.signal, s.quote))
        bl, bh = base.birth_low, base.birth_high
        agreed = {base.signal}
        contributing.append(base)
        conflict = False
        for s in sorted(core, key=lambda s: -s.confidence):
            if s is base:
                continue
            contributing.append(s)
            if _overlap(bl, bh, s):
                bl, bh = max(bl, s.birth_low), min(bh, s.birth_high)
                agreed.add(s.signal)
            else:
                conflict = True
        if conflict:  # противоречие равных по классу → расширение диапазона
            bl = min(s.birth_low for s in core)
            bh = max(s.birth_high for s in core)
        conf = base.confidence + 10 * (len(agreed) - 1)
        for s in sorted(rest, key=lambda s: -s.confidence):
            contributing.append(s)
            if _overlap(bl, bh, s):
                if s.signal not in agreed:
                    agreed.add(s.signal)
                    conf += 10
            else:
                conflict = True  # низший класс спорит → высший побеждает, conf вниз
        if conflict:
            conf = min(s.confidence for s in contributing) + 10
        methods = {s.method for s in contributing}

    for s in llms:
        if bl is None:  # только LLM — берём как есть (cap слабого сигнала)
            bl, bh = s.birth_low, s.birth_high
            conf = min(s.confidence, _LLM_LEX_CONF_CAP)
            contributing.append(s)
            methods.add("llm")
        elif _overlap(bl, bh, s):
            bl, bh = max(bl, s.birth_low), min(bh, s.birth_high)
            conf += 10
            contributing.append(s)
            methods.add("llm")
        else:  # детерминированное побеждает LLM, confidence падает (decisions.md)
            conf -= _LLM_CONFLICT_PENALTY
            contributing.append(s)
            methods.add("llm")

    conf = max(1, min(int(round(conf)), _CONF_CAP))
    seen: set[str] = set()
    evidence = []
    for s in sorted(contributing, key=lambda s: -s.confidence):
        if s.quote in seen or not s.quote:
            continue
        seen.add(s.quote)
        evidence.append({"quote": s.quote, "signal": s.signal,
                         "weight": s.confidence, "dt": (s.dt or "")[:10]})
        if len(evidence) >= _EVIDENCE_CAP:
            break
    method = methods.pop() if len(methods) == 1 else "combined"
    return {"birth_low": int(bl), "birth_high": int(bh),
            "birth_point": int(round((bl + bh) / 2)),
            "confidence": conf, "method": method, "evidence": evidence}


# ── LLM-пасс (Ф2): промпт, вызов, verbatim-гейт, парсинг под Qwen3.5 ────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _parse_llm_json(raw: str) -> dict | None:
    """llm.md: strip fences → extract {...} → fix truncated. + <think> Qwen3.5."""
    s = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    s = re.sub(r"```[a-zA-Z]*", "", s).replace("```", "")
    i, j = s.find("{"), s.rfind("}")
    if i < 0:
        return None
    frag = s[i:j + 1] if j > i else s[i:]
    for cand in (frag, frag + "}", frag + "}]}", frag + '"}]}'):
        try:
            d = json.loads(cand)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            continue
    return None


def _validate_llm(content: str | None, corpus_norm: str, anchor_year: int) -> dict:
    """Verbatim-гейт: каждая evidence-цитата — substring поданного текста.

    Галлюцинация → выброс цитаты и −15 к confidence; 0 валидных → результат
    отброшен целиком (valid=False), но сохраняется для кэша/аудита.
    """
    out = {"raw": (content or "")[:2000], "valid": False, "dropped": 0,
           "confidence": 0, "evidence": [], "age": None, "anchor_year": anchor_year}
    parsed = _parse_llm_json(content or "")
    if not parsed:
        return out
    try:
        conf = int(parsed.get("confidence") or 0)
        lo = int(parsed.get("age_low"))
        hi = int(parsed.get("age_high"))
    except (TypeError, ValueError):
        return out
    if lo > hi:
        lo, hi = hi, lo
    if not (5 <= lo <= 100 and 5 <= hi <= 100):
        return out
    conf = max(1, min(conf, _LLM_LEX_CONF_CAP))
    kept, dropped = [], 0
    for e in parsed.get("evidence") or []:
        q = str((e or {}).get("quote") or "").strip()
        if q and _norm(q) in corpus_norm:
            kept.append({"quote": q[:120], "signal": str((e or {}).get("signal") or "лексика")})
        else:
            dropped += 1
    conf -= dropped * _HALLUCINATION_PENALTY
    out["dropped"] = dropped
    if not kept:
        return out
    out.update(valid=True, confidence=max(1, conf), evidence=kept,
               age={"low": lo, "high": hi, "point": parsed.get("age_point")})
    return out


def _load_prompt_template(prompts_dir: str | None) -> str | None:
    base = Path(prompts_dir) if prompts_dir else (
        Path(__file__).resolve().parents[3] / "configs" / "prompts")
    try:
        return (base / "age_v001.txt").read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("age-промпт не найден (%s) — LLM-пасс пропущен", exc)
        return None


def _build_llm_prompt(contact_lines, owner_lines, det_signals,
                      prompts_dir) -> tuple[str, str, int] | None:
    """→ (prompt, corpus_norm, anchor_year) либо None (нет шаблона/реплик)."""
    template = _load_prompt_template(prompts_dir)
    if template is None or not contact_lines:
        return None
    top = sorted(contact_lines, key=lambda p: -len(p[0] or ""))[:_REPLICA_LIMIT]
    top.sort(key=lambda p: str(p[1] or ""))  # хронология
    buf, total, corpus = [], 0, []
    for text, dt in top:
        t = " ".join((text or "").split())
        line = f"[{str(dt or '')[:10]}] {t}"
        if total + len(line) > _REPLICA_CLIP:
            break
        buf.append(line)
        corpus.append(t)
        total += len(line) + 1
    if not buf:
        return None
    addr = [" ".join((t or "").split()) for t, _ in owner_lines if _RE_ADDR.search(t or "")]
    addr = addr[:_OWNER_ADDR_LIMIT]
    corpus.extend(addr)
    det_block = "\n".join(
        f"- {s.signal}: год рождения {s.birth_low}-{s.birth_high} (conf {s.confidence})"
        for s in det_signals[:6]) or "(нет)"
    last_date = ""
    for _, dt in reversed(top):
        if str(dt or "")[:4].isdigit():
            last_date = str(dt)[:10]
            break
    anchor_year = int(last_date[:4]) if last_date else date.today().year
    prompt = (template
              .replace("{replicas}", "\n".join(buf))
              .replace("{owner_addresses}", "\n".join(addr) or "(нет)")
              .replace("{det_context}", det_block)
              .replace("{anchor_date}", last_date or "сегодня"))
    return prompt, _norm(" \n ".join(corpus)), anchor_year


def _call_llm(prompt: str, llm_url: str) -> str | None:
    try:
        import requests
        resp = requests.post(
            llm_url,
            json={"model": "local",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": _LLM_TEMPERATURE,
                  "max_tokens": _LLM_MAX_TOKENS},
            timeout=_LLM_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 — pipeline.md Fallback: log+skip+continue
        log.warning("age-LLM недоступен (контакт продолжен без LLM): %s", exc)
        return None


def _llm_signal(wrapped: dict, fallback_year: int) -> AgeSignal | None:
    if not wrapped.get("valid") or not wrapped.get("age"):
        return None
    a = wrapped["age"]
    year = int(wrapped.get("anchor_year") or fallback_year)
    quote = (wrapped["evidence"][0]["quote"] if wrapped.get("evidence") else "")
    return AgeSignal(year - int(a["high"]), year - int(a["low"]),
                     int(wrapped.get("confidence") or 1), quote,
                     "llm_lexicon", str(year), method="llm")


# ── Главный вход ─────────────────────────────────────────────────────────────

def run_age_estimate(conn, user_id: str, *, use_llm: bool = False,
                     contact_id: int | None = None, owner_birth_year: int = 0,
                     reference_now=None, llm_url: str = _DEFAULT_LLM_URL,
                     prompts_dir: str | None = None,
                     stale_only: bool = False) -> dict:
    """Оценить возраст контактов пользователя. Идемпотентно (UPSERT).

    stale_only=True — только контакты с новыми звонками после computed_at
    (инкрементальный режим для watcher-autofit: ежедневные новые звонки
    уточняют оценку, нетронутые контакты не пересчитываются).
    """
    from . import repository as repo_mod
    repo_mod.apply_insight_schema(conn)

    ref_year = getattr(reference_now, "year", None)
    if ref_year is None:
        ref_year = int(reference_now) if reference_now else date.today().year

    sql = ("SELECT c.contact_id, MAX(COALESCE(c.call_datetime, c.created_at, '')) "
           "FROM calls c WHERE c.user_id = ? AND c.contact_id IS NOT NULL")
    params: list = [user_id]
    if contact_id is not None:
        sql += " AND c.contact_id = ?"
        params.append(contact_id)
    sql += " GROUP BY c.contact_id"
    contacts = conn.execute(sql, params).fetchall()

    computed = {
        r[0]: r[1] for r in conn.execute(
            "SELECT contact_id, computed_at FROM contact_age_estimates "
            "WHERE user_id = ?", (user_id,)).fetchall()
    }

    stats = {"contacts": 0, "estimated": 0, "llm_called": 0,
             "llm_cached": 0, "skipped_fresh": 0}

    for cid, last_dt in contacts:
        if stale_only and cid in computed:
            # ISO-сравнение; 'T' vs ' ' нормализуем. Пустая дата → НЕ skip
            # (битые таймштампы не должны замораживать контакт навсегда).
            last_norm = str(last_dt or "").replace("T", " ")
            if last_norm and last_norm <= str(computed[cid]).replace("T", " "):
                stats["skipped_fresh"] += 1
                continue
        stats["contacts"] += 1

        rows = conn.execute(
            "SELECT t.text, COALESCE(c.call_datetime, '') AS dt, t.speaker "
            "FROM transcripts t JOIN calls c ON c.call_id = t.call_id "
            "WHERE c.user_id = ? AND c.contact_id = ? "
            "AND t.speaker IN ('OWNER', 'OTHER') "
            "ORDER BY COALESCE(c.call_datetime, ''), t.start_ms",
            (user_id, cid)).fetchall()
        contact_lines = [(r[0], r[1]) for r in rows if r[2] == "OTHER"]
        owner_lines = [(r[0], r[1]) for r in rows if r[2] == "OWNER"]

        signals: list[AgeSignal] = []
        for text, dt in contact_lines:
            signals.extend(extract_marker_signals(text, dt))
        signals.extend(extract_relation_signals(owner_lines, contact_lines,
                                                owner_birth_year))

        prev = conn.execute(
            "SELECT llm_prompt_hash, llm_result, prompt_version "
            "FROM contact_age_estimates WHERE contact_id = ? AND user_id = ?",
            (cid, user_id)).fetchone()

        llm_hash = llm_store = None
        wrapped = None
        if use_llm:
            built = _build_llm_prompt(contact_lines, owner_lines, signals, prompts_dir)
            if built is not None:
                prompt, corpus_norm, anchor_year = built
                llm_hash = hashlib.sha1(
                    (prompt + PROMPT_VERSION_AGE).encode("utf-8")).hexdigest()
                if prev and prev[0] == llm_hash and prev[1]:
                    llm_store = prev[1]  # memoization: повторный run не платит
                    stats["llm_cached"] += 1
                else:
                    content = _call_llm(prompt, llm_url)
                    if content is not None:
                        stats["llm_called"] += 1
                        wrapped = _validate_llm(content, corpus_norm, anchor_year)
                        llm_store = json.dumps(wrapped, ensure_ascii=False)
        elif prev and prev[1] and prev[2] == PROMPT_VERSION_AGE:
            # det-пересчёт переиспользует оплаченный LLM-результат (динамика)
            llm_store, llm_hash = prev[1], prev[0]

        if wrapped is None and llm_store:
            try:
                wrapped = json.loads(llm_store)
            except json.JSONDecodeError:
                wrapped = None
        if wrapped:
            sig = _llm_signal(wrapped, ref_year)
            if sig is not None:
                signals.append(sig)

        est = _aggregate(signals)
        if est is None:
            if llm_store:  # мусорный LLM-ответ всё равно кэшируем (не платить дважды)
                repo_mod.save_contact_age_estimate(
                    conn, user_id, contact_id=cid, age_low=None, age_high=None,
                    age_point=None, birth_year_low=None, birth_year_high=None,
                    birth_year_point=None, confidence=1, method="llm",
                    evidence=[], prompt_version=PROMPT_VERSION_AGE,
                    llm_prompt_hash=llm_hash, llm_result=llm_store)
            continue

        if wrapped and wrapped.get("valid") and wrapped.get("evidence"):
            seen = {_norm(e["quote"]) for e in est["evidence"]}
            for e in wrapped["evidence"]:
                if _norm(e["quote"]) not in seen and len(est["evidence"]) < _EVIDENCE_CAP:
                    est["evidence"].append({"quote": e["quote"], "signal": e["signal"],
                                            "weight": wrapped["confidence"], "dt": ""})

        age_low = max(0, min(ref_year - est["birth_high"], 105))
        age_high = max(0, min(ref_year - est["birth_low"], 105))
        age_point = max(0, min(ref_year - est["birth_point"], 105))
        repo_mod.save_contact_age_estimate(
            conn, user_id, contact_id=cid, age_low=age_low, age_high=age_high,
            age_point=age_point, birth_year_low=est["birth_low"],
            birth_year_high=est["birth_high"], birth_year_point=est["birth_point"],
            confidence=est["confidence"], method=est["method"],
            evidence=est["evidence"],
            prompt_version=PROMPT_VERSION_AGE if llm_store else None,
            llm_prompt_hash=llm_hash, llm_result=llm_store)
        stats["estimated"] += 1

    conn.commit()
    return stats
