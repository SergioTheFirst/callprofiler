# -*- coding: utf-8 -*-
"""
p6_chapters.py — Pass 6: Chapter Writer.

Groups scenes into monthly chapters and generates prose. Each month
becomes one chapter. Long chapters (huge months) are capped to the top
TOP_SCENES_PER_CHAPTER by importance to fit the model context.

Theme inference: simple majority from scene_types/themes in the month.
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict

from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import build_chapter_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p6_chapters"
TOP_SCENES_PER_CHAPTER = 40
TOP_PORTRAITS_PER_CHAPTER = 10
MIN_SCENES_PER_CHAPTER = 3
MIN_SCENE_IMPORTANCE = 15


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
) -> dict:
    all_scenes = [
        s for s in bio.get_scenes_for_user(user_id, min_importance=MIN_SCENE_IMPORTANCE)
        if s.get("status") == "ok" and s.get("call_datetime")
    ]
    if not all_scenes:
        log.warning("[p6_chapters] no scenes to write chapters from")
        bio.start_checkpoint(user_id, PASS_NAME, 0)
        bio.finish_checkpoint(user_id, PASS_NAME, "done")
        return {"chapters": 0}

    # Bucket scenes by YYYY-MM.
    buckets: dict[str, list[dict]] = defaultdict(list)
    for s in all_scenes:
        dt = s["call_datetime"]
        ym = dt[:7] if len(dt) >= 7 else "unknown"
        buckets[ym].append(s)

    all_arcs = bio.get_arcs_for_user(user_id)
    all_portraits = bio.get_portraits_for_user(user_id)
    portraits_by_entity = {int(p["entity_id"]): p for p in all_portraits}

    # Index scenes -> entities via bio_scene_entities for arc/portrait lookup.
    conn = bio.conn
    scene_entities: dict[int, list[int]] = defaultdict(list)
    rows = conn.execute(
        """SELECT se.scene_id, se.entity_id
             FROM bio_scene_entities se
             JOIN bio_scenes s ON s.scene_id = se.scene_id
            WHERE s.user_id = ?""",
        (user_id,),
    ).fetchall()
    for r in rows:
        scene_entities[int(r["scene_id"])].append(int(r["entity_id"]))

    months = sorted(buckets.keys())
    valid_months = [m for m in months if len(buckets[m]) >= MIN_SCENES_PER_CHAPTER]
    bio.start_checkpoint(user_id, PASS_NAME, len(valid_months) or 1)
    began = time.monotonic()
    written = 0
    failed = 0

    for idx, ym in enumerate(valid_months, start=1):
        scenes = buckets[ym]
        # Keep top by importance.
        scenes = sorted(scenes, key=lambda s: int(s.get("importance") or 0),
                        reverse=True)[:TOP_SCENES_PER_CHAPTER]
        scenes.sort(key=lambda s: s.get("call_datetime") or "")

        period_start = scenes[0].get("call_datetime")
        period_end = scenes[-1].get("call_datetime")

        # Entities in this month (via scene -> entity map).
        month_entity_ids: Counter = Counter()
        for s in scenes:
            for eid in scene_entities.get(int(s["scene_id"]), []):
                month_entity_ids[eid] += 1
        top_portraits = [
            portraits_by_entity[eid]
            for eid, _ in month_entity_ids.most_common(TOP_PORTRAITS_PER_CHAPTER)
            if eid in portraits_by_entity
        ]

        # Arcs overlapping this month.
        month_arcs = [
            a for a in all_arcs
            if _arc_overlaps_month(a, ym)
        ]
        month_arcs = sorted(month_arcs,
                            key=lambda a: int(a.get("importance") or 0),
                            reverse=True)[:8]

        # Theme = most common scene_type + top themes.
        scene_types = Counter(s.get("scene_type") or "routine" for s in scenes)
        top_type = scene_types.most_common(1)[0][0]
        theme_counter: Counter = Counter()
        for s in scenes:
            for t in s.get("themes") or []:
                if isinstance(t, str):
                    theme_counter[t.lower()] += 1
        top_themes = [t for t, _ in theme_counter.most_common(4)]
        theme_line = top_type + (": " + ", ".join(top_themes) if top_themes else "")

        title = f"{_month_title(ym)}"

        messages = build_chapter_prompt(
            chapter_num=idx,
            title=title,
            period_start=period_start,
            period_end=period_end,
            theme=theme_line,
            scenes=scenes,
            arcs=month_arcs,
            portraits=top_portraits,
        )
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"chapter:{ym}",
            messages=messages,
            temperature=0.55,
            max_tokens=3200,
        )

        if not response or len(response.strip()) < 200:
            failed += 1
            bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{ym}",
                                processed_delta=1, failed_delta=1)
            continue

        # Extract title from first `# ...` line if present.
        final_title = _extract_heading(response) or title

        bio.upsert_chapter(
            user_id=user_id,
            chapter_num=idx,
            title=final_title[:200],
            period_start=period_start,
            period_end=period_end,
            theme=theme_line[:200],
            prose=response.strip(),
            scene_ids=[int(s["scene_id"]) for s in scenes],
            arc_ids=[int(a["arc_id"]) for a in month_arcs],
            entity_ids=list(month_entity_ids.keys()),
            model=llm.model_name,
        )
        written += 1
        bio.tick_checkpoint(user_id, PASS_NAME, f"chapter:{ym}")

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "months": len(months),
        "chapters_written": written,
        "failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p6_chapters] done %s", stats)
    return stats


def _arc_overlaps_month(arc: dict, ym: str) -> bool:
    s = (arc.get("start_date") or "")[:7]
    e = (arc.get("end_date") or "")[:7]
    if not s and not e:
        return False
    if s and e:
        return s <= ym <= e
    return (s or e) == ym


def _month_title(ym: str) -> str:
    months = {
        "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
        "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
        "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь",
    }
    try:
        year, month = ym.split("-", 1)
        return f"{months.get(month, month)} {year}"
    except ValueError:
        return ym


def _extract_heading(md: str) -> str:
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""
