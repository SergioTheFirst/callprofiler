# -*- coding: utf-8 -*-
"""
prompts.py — prompt templates for all 8 biography passes.

All prompts target a local llama-server (Qwen-class model) and are written in
Russian because the source material (call transcripts) is Russian. Each
builder returns a list[dict] in OpenAI chat format.

Prompt contract (all passes):
  * System message = role + strict JSON/format rules.
  * User message  = narrative data blob with explicit field names.
  * Output        = strict JSON (single object) OR markdown (chapter/book).
                    Never prose mixed with JSON.

Version bumping: if you change a prompt, bump PROMPT_VERSION so the memoization
key breaks and new results get written (old rows remain in bio_llm_calls for
audit but won't be returned by get_cached_llm for the new hash).
"""

from __future__ import annotations

import json

PROMPT_VERSION = "bio-v1"


# ---------------------------------------------------------------------------
# Pass 1 — Scene Extractor
# ---------------------------------------------------------------------------

_SCENE_SYS = """Ты литературный редактор-биограф. Тебе присылают запись одного
телефонного разговора. Твоя задача — превратить её в одну "сцену" для
биографической книги.

Строго верни ОДИН JSON-объект в таком виде, без markdown-оберток, без
пояснений:
{
  "importance": 0-100,            // насколько сцена значима для книги
  "scene_type": "business|personal|conflict|joy|routine|transition",
  "setting": "короткая фраза об обстановке или контексте",
  "synopsis": "1-3 предложения, нарративно, как из книги",
  "key_quote": "одна цитата до 200 символов, если есть",
  "emotional_tone": "tense|warm|neutral|worried|celebratory|angry",
  "named_entities": [
      {"name":"...", "type":"PERSON|PLACE|COMPANY|PROJECT|EVENT",
       "mention":"как именно упомянут"}
  ],
  "themes": ["до 3 тем одним словом-двумя"]
}

Правила:
- Не выдумывай ничего, чего нет в транскрипте.
- Имена людей пиши в канонической русской форме (Василий, а не Вася), но в
  aliases/mention сохраняй оригинал.
- importance>=70 — только если сцена реально про решение, конфликт или
  событие. Обычный созвон по статусу = 10-30.
- Если транскрипт пуст или мусор — верни importance=0, scene_type="routine",
  synopsis="".
"""


def build_scene_prompt(
    call_datetime: str | None,
    contact_label: str,
    direction: str | None,
    duration_sec: int | None,
    prior_analysis: dict | None,
    transcript: str,
) -> list[dict]:
    prior = ""
    if prior_analysis:
        prior = (
            f"Предыдущий автоанализ (для контекста, не копируй дословно):\n"
            f"  тип={prior_analysis.get('call_type')}\n"
            f"  риск={prior_analysis.get('risk_score')}\n"
            f"  резюме={prior_analysis.get('summary')}\n"
            f"  темы={prior_analysis.get('key_topics')}\n"
        )
    user = (
        f"Дата: {call_datetime or 'неизвестна'}\n"
        f"Контакт: {contact_label}\n"
        f"Направление: {direction or '?'}\n"
        f"Длительность: {duration_sec or 0} сек\n\n"
        f"{prior}\n"
        f"Транскрипт (usually [me]=Сергей, [s2]=собеседник):\n"
        f"------\n{_clip(transcript, 6000)}\n------\n\n"
        f"Верни только JSON-сцену."
    )
    return [
        {"role": "system", "content": _SCENE_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 2 — Entity Resolver (cluster names into canonical people/places)
# ---------------------------------------------------------------------------

_ENTITY_SYS = """Ты лингвист-аналитик. Тебе дан список упоминаний (surface
forms) одного типа — PERSON / PLACE / COMPANY / PROJECT / EVENT. Нужно
объединить их в канонические сущности.

Верни строго ОДИН JSON:
{
  "entities": [
    {
      "canonical": "каноническое имя",
      "aliases": ["все варианты, включая каноническое"],
      "role":     "colleague|client|supplier|friend|family|null",
      "description": "1-2 предложения кто это / что это, на основании контекста"
    }
  ]
}

Правила:
- Вася/Василий/В.П./Василий Петрович = одно. canonical = самая полная форма.
- Разные люди с одинаковым именем = разные сущности (используй подсказки роли
  или компании из контекста).
- Если сомневаешься — не объединяй.
- Если имя явно мусор (один слог, служебное слово) — не включай в вывод.
"""


def build_entity_prompt(entity_type: str, mentions: list[dict]) -> list[dict]:
    payload = {
        "entity_type": entity_type,
        "mentions": mentions,  # [{"name":..., "context":...}, ...]
    }
    user = (
        f"Тип: {entity_type}\n"
        f"Упоминания (surface form + короткий контекст):\n"
        f"{json.dumps(payload['mentions'], ensure_ascii=False, indent=2)[:10000]}\n\n"
        f"Верни JSON."
    )
    return [
        {"role": "system", "content": _ENTITY_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 3 — Thread Builder (narrative arc for one entity across scenes)
# ---------------------------------------------------------------------------

_THREAD_SYS = """Ты биограф. Дан список сцен о ОДНОМ персонаже/месте/
компании в хронологическом порядке. Напиши краткую сюжетную линию.

Строго JSON:
{
  "title": "короткий заголовок линии (до 80 символов)",
  "summary": "2-4 абзаца: как развивалась тема/отношения. Фактически, без воды.",
  "tension_curve": [<int 0-100 для каждой сцены по её роли в линии>]
}

Правила:
- Длина tension_curve == числу поданных сцен.
- Используй только факты из сцен.
- Пиши от третьего лица, нейтрально.
"""


def build_thread_prompt(entity_name: str, entity_type: str, scenes: list[dict]) -> list[dict]:
    condensed = [
        {
            "date": s.get("call_datetime"),
            "importance": s.get("importance"),
            "tone": s.get("emotional_tone"),
            "synopsis": s.get("synopsis"),
            "key_quote": s.get("key_quote"),
        }
        for s in scenes
    ]
    user = (
        f"Сущность: {entity_name} ({entity_type})\n"
        f"Всего сцен: {len(scenes)}\n\n"
        f"{json.dumps(condensed, ensure_ascii=False, indent=2)[:12000]}\n\n"
        f"Верни JSON."
    )
    return [
        {"role": "system", "content": _THREAD_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 4 — Arc Detector (problem/project arcs across scenes+entities)
# ---------------------------------------------------------------------------

_ARC_SYS = """Ты сценарист. Дан хронологический журнал сцен (с участниками и
темами). Найди МНОГОСЕРИЙНЫЕ арки: проблемы, которые тянулись несколько звонков;
проекты; жизненные события; длинные отношения.

Строго JSON:
{
  "arcs": [
    {
      "title": "короткий заголовок",
      "arc_type": "problem|project|relationship|life_event",
      "status": "ongoing|resolved|abandoned",
      "synopsis": "1 абзац: завязка → развитие → итог (или текущее состояние)",
      "scene_indices": [<индексы сцен из входа, начиная с 0>],
      "entity_names": ["канонические имена ключевых участников"],
      "outcome": "чем закончилось или открытый вопрос",
      "importance": 0-100,
      "start_date": "YYYY-MM-DD или null",
      "end_date":   "YYYY-MM-DD или null"
    }
  ]
}

Правила:
- Минимум 2 сцены на арку. Одиночные сцены не выделяем.
- Максимум 20 арок.
- Сортируй по importance убыванию.
"""


def build_arc_prompt(scenes: list[dict]) -> list[dict]:
    condensed = [
        {
            "i": i,
            "date": s.get("call_datetime"),
            "importance": s.get("importance"),
            "scene_type": s.get("scene_type"),
            "themes": s.get("themes"),
            "entities": [e.get("name") for e in (s.get("named_entities") or []) if isinstance(e, dict)],
            "synopsis": s.get("synopsis"),
        }
        for i, s in enumerate(scenes)
    ]
    user = (
        f"Всего сцен: {len(scenes)}\n\n"
        f"{json.dumps(condensed, ensure_ascii=False, indent=2)[:14000]}\n\n"
        f"Верни JSON со списком арок."
    )
    return [
        {"role": "system", "content": _ARC_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 5 — Portrait Writer (deep sketch for one recurring entity)
# ---------------------------------------------------------------------------

_PORTRAIT_SYS = """Ты биограф. Напиши литературный портрет персонажа (человек,
компания, место) на основе представленного досье.

Строго JSON:
{
  "prose": "1-3 абзаца. Как персонаж появляется в жизни владельца, что с ним
            связано, как меняется тон разговоров, какие ключевые эпизоды.",
  "traits": ["до 6 коротких ярлыков-характеристик"],
  "relationship": "1 фраза — тип отношений с владельцем",
  "pivotal_scene_indices": [<индексы ключевых сцен из входа>]
}

Правила:
- Только факты из досье, без психологических выводов на пустом месте.
- Тон — журналистский, сдержанный.
"""


def build_portrait_prompt(
    entity_name: str,
    entity_type: str,
    role: str | None,
    thread_summary: str | None,
    scenes: list[dict],
) -> list[dict]:
    condensed = [
        {
            "i": i,
            "date": s.get("call_datetime"),
            "importance": s.get("importance"),
            "tone": s.get("emotional_tone"),
            "synopsis": s.get("synopsis"),
            "key_quote": s.get("key_quote"),
        }
        for i, s in enumerate(scenes)
    ]
    user = (
        f"Персонаж: {entity_name} ({entity_type})\n"
        f"Роль: {role or 'не определена'}\n"
        f"Сюжетная линия: {thread_summary or '-'}\n\n"
        f"Сцены (всего {len(scenes)}):\n"
        f"{json.dumps(condensed, ensure_ascii=False, indent=2)[:12000]}\n\n"
        f"Верни JSON."
    )
    return [
        {"role": "system", "content": _PORTRAIT_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 6 — Chapter Writer (thematic prose chapter)
# ---------------------------------------------------------------------------

_CHAPTER_SYS = """Ты пишешь главу биографической книги. Жанр — документальная
проза: факты переданы литературно, без статистики, без упоминаний количества
звонков или секунд.

Верни ТОЛЬКО markdown-главу (без JSON) в таком виде:

# <Название главы>

<3-8 абзацев связного текста. Можно выделять подзаголовки `## ...` по смыслу.>

Правила:
- НЕ используй слова "звонок", "разговор по телефону" — вместо них:
  "встреча", "беседа", "тогда Василий сказал...".
- НЕ цитируй процент, число, счётчики. Никаких "47 раз", "2 часа 30 минут".
- Русский язык. Третье лицо, нейтрально-литературный тон.
- Длина главы 500-1200 слов.
- Вплетай имена канонически (Василий, а не Вася).
- Только факты из поданных материалов.
"""


def build_chapter_prompt(
    chapter_num: int,
    title: str,
    period_start: str | None,
    period_end: str | None,
    theme: str,
    scenes: list[dict],
    arcs: list[dict],
    portraits: list[dict],
) -> list[dict]:
    # Be brutal with size — model context is 16K tokens.
    scenes_slim = [
        {
            "date": s.get("call_datetime"),
            "with": [e.get("name") for e in (s.get("named_entities") or []) if isinstance(e, dict)],
            "tone": s.get("emotional_tone"),
            "synopsis": s.get("synopsis"),
            "key_quote": s.get("key_quote"),
        }
        for s in scenes
    ]
    arcs_slim = [
        {
            "title": a.get("title"),
            "type": a.get("arc_type"),
            "status": a.get("status"),
            "synopsis": a.get("synopsis"),
            "outcome": a.get("outcome"),
        }
        for a in arcs
    ]
    portraits_slim = [
        {
            "name": p.get("canonical_name"),
            "relationship": p.get("relationship"),
            "traits": p.get("traits"),
            "prose": (p.get("prose") or "")[:500],
        }
        for p in portraits
    ]
    user = (
        f"Глава {chapter_num}. Рабочее название: «{title}»\n"
        f"Период: {period_start or '?'} — {period_end or '?'}\n"
        f"Тема главы: {theme}\n\n"
        f"Портреты ключевых участников:\n"
        f"{json.dumps(portraits_slim, ensure_ascii=False, indent=2)[:4000]}\n\n"
        f"Арки в этом периоде:\n"
        f"{json.dumps(arcs_slim, ensure_ascii=False, indent=2)[:3000]}\n\n"
        f"Сцены ({len(scenes)} шт.):\n"
        f"{json.dumps(scenes_slim, ensure_ascii=False, indent=2)[:6000]}\n\n"
        f"Напиши главу."
    )
    return [
        {"role": "system", "content": _CHAPTER_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 7 — Book Assembler (prologue + TOC + epilogue synthesis)
# ---------------------------------------------------------------------------

_BOOK_FRAME_SYS = """Ты пишешь каркас биографической книги: название,
подзаголовок, эпиграф, пролог и эпилог. Используешь список глав (их заголовки
и темы) и сводку ключевых арок.

Верни строго JSON:
{
  "title": "название книги (до 80 символов)",
  "subtitle": "подзаголовок (до 120 символов)",
  "epigraph": "одна цитата из материала или короткое авторское эпиграфическое
               предложение; можно оставить пустой строкой",
  "prologue": "1-3 абзаца: как устроена книга, кто её герой, откуда материал",
  "epilogue": "1-3 абзаца: сквозные мотивы, открытые сюжетные линии",
  "toc": [
    {"chapter_num": <int>, "title": "...", "one_liner": "фраза"}
  ]
}

Правила:
- Никаких статистик, процентов и упоминаний "телефонных разговоров".
- Русский язык.
- Имя владельца: Сергей Медведев.
"""


def build_book_frame_prompt(
    chapters: list[dict],
    top_arcs: list[dict],
    top_entities: list[dict],
    period_start: str | None,
    period_end: str | None,
) -> list[dict]:
    chapters_slim = [
        {
            "n": c.get("chapter_num"),
            "title": c.get("title"),
            "theme": c.get("theme"),
            "period": f"{c.get('period_start')} — {c.get('period_end')}",
        }
        for c in chapters
    ]
    arcs_slim = [
        {"title": a.get("title"), "type": a.get("arc_type"),
         "status": a.get("status"), "synopsis": a.get("synopsis")}
        for a in top_arcs[:15]
    ]
    ents_slim = [
        {"name": e.get("canonical_name"), "type": e.get("entity_type"),
         "role": e.get("role"), "mentions": e.get("mention_count")}
        for e in top_entities[:20]
    ]
    user = (
        f"Период: {period_start or '?'} — {period_end or '?'}\n\n"
        f"Оглавление (черновое):\n"
        f"{json.dumps(chapters_slim, ensure_ascii=False, indent=2)[:4000]}\n\n"
        f"Главные арки:\n"
        f"{json.dumps(arcs_slim, ensure_ascii=False, indent=2)[:3000]}\n\n"
        f"Главные персонажи/места:\n"
        f"{json.dumps(ents_slim, ensure_ascii=False, indent=2)[:2000]}\n\n"
        f"Верни JSON-каркас."
    )
    return [
        {"role": "system", "content": _BOOK_FRAME_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 8 — Editorial Pass (polish one chapter)
# ---------------------------------------------------------------------------

_EDITORIAL_SYS = """Ты редактор. Тебе дан черновик главы. Отредактируй его:
убери повторы, срасти абзацы, выровняй тон, убери канцеляриты и любые
упоминания числа/длительности звонков. Сохрани все фактические имена и
события.

Верни ТОЛЬКО отредактированный markdown-текст главы (с # заголовком).
"""


def build_editorial_prompt(chapter_prose: str) -> list[dict]:
    user = (
        "Отредактируй главу ниже. Объём сохрани примерно таким же.\n\n"
        f"{chapter_prose[:12000]}"
    )
    return [
        {"role": "system", "content": _EDITORIAL_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip(s: str, limit: int) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    half = limit // 2
    return s[:half] + "\n\n[... SKIPPED ...]\n\n" + s[-half:]
