# -*- coding: utf-8 -*-
"""
p1_scene.py — Pass 1: Scene Extractor.

For each call belonging to the user, produce one "scene" row in bio_scenes.
Skips calls that already have a non-failed scene (idempotent re-runs).

The LLM receives the transcript + the previously-computed analysis snapshot
(summary, call_type, risk_score, key_topics) as context — this both reduces
hallucination and lets small models punch above their weight.

Resume protocol:
  - start_checkpoint('p1_scene', total)
  - tick_checkpoint after every call, storing last_item_key = "call_id:{id}"
  - finish_checkpoint('done') when loop ends normally
"""

from __future__ import annotations

import logging
import time
from typing import Any

from callprofiler.biography.json_utils import extract_json
from callprofiler.biography.llm_client import ResilientLLMClient
from callprofiler.biography.prompts import PROMPT_VERSION, build_scene_prompt
from callprofiler.biography.repo import BiographyRepo

log = logging.getLogger(__name__)

PASS_NAME = "p1_scene"


def run(
    user_id: str,
    bio: BiographyRepo,
    llm: ResilientLLMClient,
    limit: int | None = None,
    skip_existing: bool = True,
    progress_every: int = 20,
) -> dict:
    """Run Pass 1. Returns stats dict."""
    calls = bio.iter_calls_for_user(user_id)
    if limit:
        calls = calls[: int(limit)]
    total = len(calls)
    log.info("[p1_scene] user=%s total_calls=%d", user_id, total)

    bio.start_checkpoint(user_id, PASS_NAME, total)

    # Load already-completed items for fast resume (avoids per-call DB queries).
    done_ids = bio.get_completed_items(user_id, PASS_NAME)

    processed = 0
    skipped = 0
    failed = 0
    began = time.monotonic()

    for idx, call in enumerate(calls, start=1):
        call_id = int(call["call_id"])
        item_key = f"call_id:{call_id}"

        if item_key in done_ids:
            skipped += 1
            bio.tick_checkpoint(
                user_id, PASS_NAME, item_key,
                processed_delta=1, failed_delta=0,
                notes=f"resumed:{skipped}",
            )
            continue

        if skip_existing and bio.scene_exists(call_id):
            skipped += 1
            bio.tick_checkpoint(
                user_id, PASS_NAME, item_key,
                processed_delta=1, failed_delta=0,
                notes=f"skipped:{skipped}",
            )
            continue

        try:
            transcript = bio.get_transcript_text(call_id, user_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("p1 transcript read failed call=%s err=%s", call_id, exc)
            transcript = ""

        if len((transcript or "").strip()) < 50:
            # too short to extract a scene — record a stub so we don't retry
            bio.upsert_scene(
                user_id=user_id,
                call_id=call_id,
                data={
                    "call_datetime": call.get("call_datetime"),
                    "importance": 0,
                    "scene_type": "routine",
                    "setting": "",
                    "synopsis": "",
                    "key_quote": "",
                    "emotional_tone": "neutral",
                    "named_entities": [],
                    "themes": [],
                    "raw_llm": "",
                    "model": llm.model_name,
                    "prompt_version": PROMPT_VERSION,
                    "status": "skipped",
                },
            )
            skipped += 1
            bio.tick_checkpoint(
                user_id, PASS_NAME, item_key, processed_delta=1,
            )
            continue

        analysis = bio.get_analysis_snapshot(call_id, user_id)
        contact_label = bio.get_contact_label(call.get("contact_id"))

        cleaned_transcript = _clean_transcript(transcript)

        messages = build_scene_prompt(
            call_datetime=call.get("call_datetime"),
            contact_label=contact_label,
            direction=call.get("direction"),
            duration_sec=call.get("duration_sec"),
            prior_analysis=analysis,
            transcript=cleaned_transcript,
        )
        response = llm.call(
            user_id=user_id,
            pass_name=PASS_NAME,
            context_key=f"scene:{call_id}",
            messages=messages,
            temperature=0.3,
            max_tokens=1800,
        )

        data = extract_json(response) if response else None
        if not isinstance(data, dict):
            failed += 1
            bio.upsert_scene(
                user_id=user_id,
                call_id=call_id,
                data={
                    "call_datetime": call.get("call_datetime"),
                    "importance": 0,
                    "scene_type": "routine",
                    "setting": "",
                    "synopsis": "",
                    "key_quote": "",
                    "emotional_tone": "neutral",
                    "named_entities": [],
                    "themes": [],
                    "raw_llm": response or "",
                    "model": llm.model_name,
                    "prompt_version": PROMPT_VERSION,
                    "status": "failed",
                },
            )
            bio.tick_checkpoint(
                user_id, PASS_NAME, item_key,
                processed_delta=1, failed_delta=1,
                notes=f"failed:{failed}",
            )
            _progress(idx, total, began, processed, skipped, failed, progress_every)
            continue

        data.setdefault("call_datetime", call.get("call_datetime"))
        data["raw_llm"] = response
        data["model"] = llm.model_name
        data["prompt_version"] = PROMPT_VERSION
        data.setdefault("status", "ok")
        # Clean ASR artifacts from key_quote
        if data.get("key_quote"):
            data["key_quote"] = _clean_quote(data["key_quote"])
        try:
            bio.upsert_scene(user_id=user_id, call_id=call_id, data=data)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("p1 upsert failed call=%s: %s", call_id, exc)
            failed += 1
            bio.tick_checkpoint(
                user_id, PASS_NAME, item_key,
                processed_delta=1, failed_delta=1,
                notes=f"upsert_error:{exc}",
            )
            continue

        bio.tick_checkpoint(
            user_id, PASS_NAME, item_key, processed_delta=1,
        )
        _progress(idx, total, began, processed, skipped, failed, progress_every)

    bio.finish_checkpoint(user_id, PASS_NAME, "done")
    stats = {
        "total": total,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "elapsed_sec": round(time.monotonic() - began, 1),
    }
    log.info("[p1_scene] done %s", stats)
    return stats


def _progress(idx, total, began, processed, skipped, failed, every):
    if idx % every != 0 and idx != total:
        return
    elapsed = time.monotonic() - began
    rate = idx / elapsed if elapsed > 0 else 0
    remaining = (total - idx) / rate if rate else 0
    log.info(
        "[p1_scene] %d/%d  ok=%d skipped=%d failed=%d  "
        "%.1fc/s  ETA=%.0fmin",
        idx, total, processed, skipped, failed, rate, remaining / 60,
    )


def _clean_quote(quote: str) -> str:
    """Remove common ASR artifacts: filled pauses, repeated words, normalise spacing."""
    import re
    # Remove long vowel stretches (эээ, ммм, ааа — typical Russian filled pauses)
    quote = re.sub(r'\b[эыаоеиуяю]{3,}\b', '', quote, flags=re.IGNORECASE)
    # Remove isolated single-vowel fragments (Whisper hallucination)
    quote = re.sub(r'\s+[эыаоеиуяю]{1,2}\s+', ' ', quote, flags=re.IGNORECASE)
    # Remove repeated consecutive words (Whisper loop artifact)
    quote = re.sub(r'\b(\w+)\s+\1\b', r'\1', quote)
    # Collapse multiple spaces
    quote = ' '.join(quote.split())
    return quote[:240]


def _clean_transcript(transcript: str) -> str:
    """Light ASR cleanup of full transcript — removes filled pauses, repeated words.
    
    Preserves [me]: / [s2]: speaker labels. Does NOT remove words or meaning.
    """
    import re
    lines = transcript.split('\n')
    cleaned = []
    for line in lines:
        # Split speaker label from text
        if line.startswith('[me]:') or line.startswith('[s2]:') or line.startswith('[?]:'):
            label, text = line.split(':', 1)
            text = text.strip()
            # Remove filled pauses (3+ vowels in a row, standalone)
            text = re.sub(r'\b[эыаоеиуяю]{3,}\b', '', text, flags=re.IGNORECASE)
            # Remove single isolated vowel "words" (Whisper hallucination fragments)
            text = re.sub(r'\s+[эыаоеиуяю]{1,2}\s+', ' ', text, flags=re.IGNORECASE)
            # Remove 3+ consecutive repeated words (Whisper loop)
            text = re.sub(r'\b(\w+)\s+\1\s+\1\b', r'\1', text)
            # Remove 2-word repeats
            text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text)
            text = ' '.join(text.split())
            if text:
                cleaned.append(f'{label}: {text}')
        else:
            if line.strip():
                cleaned.append(line.strip())
    return '\n'.join(cleaned)
