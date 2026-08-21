"""Regression: biography prompt builders must be callable (BUDGETS exists).

5c0cb79 deleted the ``BUDGETS`` dict as "legacy" while every ``build_*_prompt``
kept indexing it → ``NameError`` on every biography pass. No test imported the
module, so the suite stayed green; CI flake8 F821 caught it (2026-08-21).
"""

from __future__ import annotations

from callprofiler.biography import prompts


def test_budgets_cover_every_pass():
    assert set(prompts.BUDGETS) == set(prompts.PASS_OUTPUT_RESERVES)


def test_scene_prompt_builds_and_clips():
    long_transcript = "[me] слово " * 20_000
    msgs = prompts.build_scene_prompt(
        call_datetime="2026-01-01 10:00",
        contact_label="Вася",
        direction="in",
        duration_sec=120,
        prior_analysis={"call_type": "business", "risk_score": 10, "summary": "", "key_topics": []},
        transcript=long_transcript,
    )
    assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "user"
    assert len(msgs[-1]["content"]) < len(long_transcript)


def test_remaining_simple_builders_do_not_raise():
    prompts.build_entity_prompt("PERSON", [{"name": "Вася", "context": "звонил"}])
    prompts.build_arc_prompt([{"date": "2026-01-01", "synopsis": "x"}])
    prompts.build_editorial_prompt("# Глава\n\nТекст.")
