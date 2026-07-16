# -*- coding: utf-8 -*-
"""
canary.py — M4 (ozalup2.md §3.4): сравнение json_mode=False vs True на одних
и тех же звонках/промптах. Строит messages ТЕМ ЖЕ PromptBuilder, что и
AnalysisService (analyze_v001.txt не меняется — T3-зона), прогоняет через
LLM дважды на звонок и парсит существующим parse_llm_response.
НИЧЕГО не пишет в БД (ни analyses, ни llm_calls — client без cache_conn).
"""

from __future__ import annotations

import json
import random
from typing import Callable

from callprofiler.analyze.llm_client import LLMClient
from callprofiler.analyze.output_budget import output_budget
from callprofiler.analyze.prompt_budget import estimate_tokens
from callprofiler.analyze.prompt_builder import PromptBuilder
from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.analyze.service import PROMPT_VERSION_ANALYZE
from callprofiler.config import Config


def _format_transcript(segments) -> str:
    parts = []
    for s in segments:
        speaker = (s["speaker"] or "UNKNOWN").upper()
        role = "[me]" if speaker == "OWNER" else ("[s2]" if speaker == "OTHER" else "[?]")
        text = (s["text"] or "").strip()
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def _sample_calls(conn, user_id: str, n: int, seed: int) -> list:
    """Стратифицированная выборка по длительности — реюз подхода spotcheck.py."""
    rows = conn.execute(
        """SELECT c.call_id, c.call_datetime, c.direction, c.duration_sec,
                  ct.display_name, ct.phone_e164
             FROM calls c
             LEFT JOIN contacts ct ON ct.contact_id = c.contact_id
            WHERE c.user_id = ? AND c.status IN ('done', 'transcribed')
            ORDER BY c.call_id""",
        (user_id,),
    ).fetchall()

    short = [r for r in rows if (r["duration_sec"] or 0) < 60]
    medium = [r for r in rows if 60 <= (r["duration_sec"] or 0) <= 600]
    long_ = [r for r in rows if (r["duration_sec"] or 0) > 600]

    rng = random.Random(seed)
    per_bucket = max(1, n // 3)
    picked: list = []
    for bucket in (short, medium, long_):
        k = min(per_bucket, len(bucket))
        if k:
            picked.extend(rng.sample(bucket, k))

    picked_ids = {r["call_id"] for r in picked}
    if len(picked) < n:
        remaining = [r for r in rows if r["call_id"] not in picked_ids]
        need = min(n - len(picked), len(remaining))
        if need:
            picked.extend(rng.sample(remaining, need))

    picked.sort(key=lambda r: r["call_id"])
    return picked


def _new_branch_stats() -> dict:
    return {
        "parsed_ok": 0, "parsed_partial": 0, "parse_failed": 0, "output_truncated": 0,
        "empty_promises": 0, "empty_entities": 0, "resp_lens": [],
    }


def run_canary(
    conn,
    user_id: str,
    llm_client_factory: Callable[[], LLMClient],
    config: Config,
    n: int = 50,
    seed: int = 0,
) -> str:
    """Markdown-отчёт: parse_status по веткам json_mode False/True, доля пустых
    promises/entities, truncated%, средняя длина ответа. Ничего не пишет в БД.

    ``config`` даёт prompts_dir/llm_n_ctx/llm_model — те же настройки, что и
    реальный AnalysisService, иначе сравнение truncated%/бюджета нерепрезентативно.
    """
    client = llm_client_factory()
    builder = PromptBuilder(config.prompts_dir)
    picked = _sample_calls(conn, user_id, n, seed)

    stats = {False: _new_branch_stats(), True: _new_branch_stats()}
    n_calls = 0

    for row in picked:
        segs = conn.execute(
            "SELECT speaker, text FROM transcripts WHERE call_id = ? ORDER BY start_ms",
            (row["call_id"],),
        ).fetchall()
        transcript_text = _format_transcript(segs)
        if not transcript_text.strip():
            continue
        n_calls += 1

        metadata = {
            "contact_name": row["display_name"],
            "phone": row["phone_e164"],
            "call_datetime": row["call_datetime"],
            "direction": row["direction"] or "UNKNOWN",
        }
        # previous_summaries пусто: canary меряет эффект json_mode на формат
        # ответа, не точность подобранного контекста (ponytail: сознательно).
        prompt = builder.build(transcript_text, metadata, [], version=PROMPT_VERSION_ANALYZE)
        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ]
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in messages)
        budget = output_budget(
            transcript_chars=len(transcript_text),
            prompt_tokens=prompt_tokens,
            n_ctx=config.models.llm_n_ctx,
        )

        for json_mode in (False, True):
            result = client.complete(
                messages=messages, temperature=0.3, max_tokens=budget, json_mode=json_mode,
            )
            raw = result.text or ""
            analysis = parse_llm_response(
                raw, model=config.models.llm_model, prompt_version=PROMPT_VERSION_ANALYZE,
            )
            st = stats[json_mode]
            st[analysis.parse_status] = st.get(analysis.parse_status, 0) + 1
            if not analysis.promises:
                st["empty_promises"] += 1
            try:
                entities = json.loads(analysis.canonical_json or "{}").get("entities", [])
            except (json.JSONDecodeError, AttributeError):
                entities = []
            if not entities:
                st["empty_entities"] += 1
            st["resp_lens"].append(len(raw))

    return _format_report(n_calls, stats)


def _format_report(n_calls: int, stats: dict) -> str:
    lines = [
        "# Canary: json_mode=False vs True\n",
        f"Звонков сравнено: {n_calls}\n",
        "| метрика | False | True |",
        "|---|---|---|",
    ]
    for key, label in (
        ("parsed_ok", "parsed_ok"),
        ("parsed_partial", "parsed_partial"),
        ("parse_failed", "parse_failed"),
        ("output_truncated", "output_truncated"),
    ):
        lines.append(f"| {label} | {stats[False][key]} | {stats[True][key]} |")

    for json_mode in (False, True):
        st = stats[json_mode]
        total = max(n_calls, 1)
        lens = st["resp_lens"]
        avg_len = sum(lens) / len(lens) if lens else 0.0
        st["_empty_promises_pct"] = 100.0 * st["empty_promises"] / total
        st["_empty_entities_pct"] = 100.0 * st["empty_entities"] / total
        st["_truncated_pct"] = 100.0 * st["output_truncated"] / total
        st["_avg_len"] = avg_len

    lines.append("")
    lines.append("| метрика | False | True |")
    lines.append("|---|---|---|")
    lines.append(f"| пустые promises % | {stats[False]['_empty_promises_pct']:.0f} | {stats[True]['_empty_promises_pct']:.0f} |")
    lines.append(f"| пустые entities % | {stats[False]['_empty_entities_pct']:.0f} | {stats[True]['_empty_entities_pct']:.0f} |")
    lines.append(f"| truncated % | {stats[False]['_truncated_pct']:.0f} | {stats[True]['_truncated_pct']:.0f} |")
    lines.append(f"| средняя длина ответа | {stats[False]['_avg_len']:.0f} | {stats[True]['_avg_len']:.0f} |")

    return "\n".join(lines)
