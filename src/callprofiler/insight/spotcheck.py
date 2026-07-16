# -*- coding: utf-8 -*-
"""
spotcheck.py — задача 0.3 (ozalupennieStrategic5.md §Ф0): стратифицированная
выборка звонков для РУЧНОЙ проверки владельцем (WER/роли/обещания).

Прослушать выбранный звонок можно из дашборда (M2 audio player).
"""
from __future__ import annotations

import random

_SPEAKER_LABEL = {"OWNER": "[me]", "OTHER": "[s2]"}


def _label(speaker: str | None) -> str:
    return _SPEAKER_LABEL.get(speaker or "", "[?]")


def build_spotcheck(conn, user_id: str, n: int = 25, seed: int = 0) -> str:
    """Markdown: n случайных done-звонков, стратифицированных по длительности
    (короткие <60s / средние / длинные >600s — поровну). Для каждого: call_id,
    дата, контакт, audio_path, транскрипт с ролями, summary/risk/promises,
    и чек-лист: - [ ] текст верен  - [ ] роли верны  - [ ] обещания верны.
    """
    rows = conn.execute(
        """SELECT c.call_id, c.call_datetime, c.duration_sec, c.audio_path,
                  COALESCE(ct.display_name, ct.guessed_name, ct.phone_e164, '?') AS contact_name
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

    lines = [
        "# Спот-чек выборка\n",
        "Прослушать — дашборд → звонок → ▶ (M2), клик по строке транскрипта мотает к ней.\n",
    ]
    for r in picked:
        call_id = r["call_id"]
        analysis = conn.execute(
            "SELECT summary, risk_score FROM analyses WHERE call_id = ?", (call_id,)
        ).fetchone()
        segs = conn.execute(
            "SELECT speaker, text FROM transcripts WHERE call_id = ? ORDER BY start_ms",
            (call_id,),
        ).fetchall()
        proms = conn.execute(
            "SELECT who, what, due, status FROM promises WHERE call_id = ? AND user_id = ?",
            (call_id, user_id),
        ).fetchall()

        lines.append(f"## call_id={call_id} — {r['contact_name']} — {r['call_datetime'] or '?'}")
        lines.append(f"audio: {r['audio_path'] or '—'}")
        if analysis:
            lines.append(f"summary: {analysis['summary'] or ''}")
            lines.append(f"risk: {analysis['risk_score']}")
        if proms:
            lines.append("promises:")
            for p in proms:
                lines.append(
                    f"  - [{p['who']}] {p['what']} (срок: {p['due'] or '—'}, статус: {p['status']})"
                )
        lines.append("")
        lines.append("транскрипт:")
        for seg in segs:
            lines.append(f"{_label(seg['speaker'])}: {seg['text']}")
        lines.append("")
        lines.append("- [ ] текст верен")
        lines.append("- [ ] роли верны")
        lines.append("- [ ] обещания верны")
        lines.append("")

    return "\n".join(lines)
