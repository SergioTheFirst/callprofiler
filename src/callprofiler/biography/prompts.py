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

PROMPT_VERSION = "bio-v10"

PASS_VERSIONS = {
    "p1_scene": "p1-v3",
    "p2_entities": "p2-v2",
    "p3_threads": "p3-v2",
    "p3b_behavioral": "p3b-v1",
    "p4_arcs": "p4-v1",
    "p5_portraits": "p5-v3",
    "p6_chapters": "p6-v3",
    "p7_book": "p7-v1",
    "p8_editorial": "p8-v2",
    "p8b_doc_dedup": "p8b-v1",
    "p9_yearly": "p9-v2",
}

# ---------------------------------------------------------------------------
# Adaptive token budget — replaces hard [:NNNN] caps in every prompt builder.
# Each pass has its own budget profile. Sections within a prompt compete for
# the budget according to priority weights.
# ---------------------------------------------------------------------------

class TokenBudget:
    def __init__(self, max_chars: int, weights: dict[str, float]):
        self.max_chars = max_chars
        self.weights = weights

    def allocate(self, sections: dict[str, str]) -> dict[str, str]:
        total = sum(len(v) for v in sections.values())
        if total <= self.max_chars:
            return sections
        allocated: dict[str, int] = {}
        for key, weight in self.weights.items():
            if key not in sections:
                continue
            target = int(self.max_chars * weight)
            allocated[key] = min(target, len(sections[key]))
        used = sum(allocated.values())
        if used < self.max_chars:
            surplus = self.max_chars - used
            total_unmet = sum(
                max(0, len(sections[k]) - allocated.get(k, 0))
                for k in sections
                if k in self.weights
            )
            if total_unmet > 0:
                for k in sections:
                    if k not in self.weights:
                        continue
                    unmet = max(0, len(sections[k]) - allocated.get(k, 0))
                    extra = int(surplus * unmet / total_unmet)
                    allocated[k] = allocated.get(k, 0) + extra
        return {k: sections[k][:allocated.get(k, len(sections[k]))] for k in sections}

    def trim_one(self, text: str, key: str = "default") -> str:
        return self.allocate({key: text})[key]


# ---------------------------------------------------------------------------
# Dynamic budget system — replaces fixed BUDGETS with adaptive allocation
# ---------------------------------------------------------------------------

# Baseline budgets (used as starting point for CRS multiplier)
BASELINE_BUDGETS = {
    "p1_scene": 12000,
    "p2_entities": 10000,
    "p3_threads": 12000,
    "p4_arcs": 14000,
    "p5_portraits": 12000,
    "p6_chapters": 17000,
    "p7_book": 9000,
    "p8_editorial": 18000,  # REDUCED from 32000 (was overflowing context)
    "p9_yearly": 9500,
}

# Output token reserves per pass (for context window calculation)
PASS_OUTPUT_RESERVES = {
    "p1_scene": 1800,
    "p2_entities": 3800,
    "p3_threads": 2500,
    "p4_arcs": 4200,
    "p5_portraits": 2500,
    "p6_chapters": 5500,
    "p7_book": 3500,
    "p8_editorial": 5500,
    "p9_yearly": 4000,
}

# Expected output lengths (for quality assessment)
EXPECTED_LENGTHS = {
    "p1_scene": 800,      # JSON ~800 chars
    "p2_entities": 2000,  # JSON array
    "p3_threads": 1500,   # JSON
    "p4_arcs": 3000,      # JSON array
    "p5_portraits": 1800, # JSON
    "p6_chapters": 12000, # Markdown prose 2500-4500 words
    "p7_book": 2500,      # JSON frame
    "p8_editorial": 12000,# Markdown prose
    "p9_yearly": 2000,    # Markdown prose
}

# JSON passes (for validation in quality assessment)
JSON_PASSES = {"p1_scene", "p2_entities", "p3_threads", "p4_arcs", "p5_portraits", "p7_book"}


def calculate_dynamic_budget(
    pass_name: str,
    crs: float,
    is_long_call: bool = False,
    context_window: int = 16384
) -> int:
    """
    Calculate adaptive budget based on Content Richness Score.

    Args:
        pass_name: Pass identifier (e.g., "p1_scene")
        crs: Content Richness Score (0.0-1.0)
        is_long_call: True if call duration >600s or transcript >5000 chars
        context_window: Model context window in tokens (default 16384)

    Returns:
        Dynamic budget in characters (safe for context window)
    """
    # Safe reserves
    system_tokens = 2200
    output_tokens = PASS_OUTPUT_RESERVES.get(pass_name, 3000)
    available_tokens = context_window - system_tokens - output_tokens

    # Baseline (current values)
    baseline_chars = BASELINE_BUDGETS.get(pass_name, 10000)

    # CRS multiplier
    if is_long_call:
        multiplier = 2.0  # Long call priority: never truncate
    elif crs < 0.3:
        multiplier = 0.5  # Thin material: reduce budget
    elif crs > 0.7:
        multiplier = 1.5  # Rich material: expand budget
    else:
        multiplier = 1.0  # Normal: baseline

    dynamic_chars = int(baseline_chars * multiplier)

    # Safety cap: never exceed available tokens
    # chars_per_token ≈ 2.1 for Russian + JSON
    max_safe_chars = int(available_tokens * 2.1)
    return min(dynamic_chars, max_safe_chars)


def assess_output_quality(pass_name: str, output: str, input_crs: float) -> dict:
    """
    Assess LLM output quality for adaptive feedback loop.

    Returns dict with metrics and adjustment signal for next run.
    """
    expected = EXPECTED_LENGTHS.get(pass_name, 1000)

    metrics = {
        "output_length": len(output),
        "expected_length": expected,
        "truncation_detected": "..." in output[-100:] or output.endswith("…"),
        "crs_utilization": len(output) / max(input_crs * expected, 1),
    }

    # JSON validation for JSON passes
    if pass_name in JSON_PASSES:
        try:
            json.loads(output.strip())
            metrics["json_valid"] = True
        except json.JSONDecodeError:
            metrics["json_valid"] = False

    # Adjustment signal for next run
    if metrics["truncation_detected"]:
        adjustment = -0.1  # Budget was too high, reduce next time
    elif metrics["crs_utilization"] < 0.6:
        adjustment = +0.1  # Material thinner than predicted, expand budget
    else:
        adjustment = 0.0  # Budget was appropriate

    return {"metrics": metrics, "adjustment": adjustment}


# Legacy BUDGETS dict (for backward compatibility during migration)
# TODO: Remove after all passes migrated to calculate_dynamic_budget()
BUDGETS = {
    "p1_scene": TokenBudget(12000, {"transcript": 1.0}),
    "p2_entities": TokenBudget(10000, {"mentions": 1.0}),
    "p3_threads": TokenBudget(12000, {"scenes": 1.0}),
    "p4_arcs": TokenBudget(14000, {"scenes": 1.0}),
    "p5_portraits": TokenBudget(12000, {"scenes": 1.0}),
    "p6_chapters": TokenBudget(17000, {"portraits": 0.50, "arcs": 0.25, "scenes": 0.25}),
    "p7_book": TokenBudget(9000, {"chapters": 0.45, "arcs": 0.35, "entities": 0.20}),
    "p8_editorial": TokenBudget(18000, {"prose": 1.0}),  # REDUCED from 32000
    "p9_yearly": TokenBudget(9500, {"chapters": 0.50, "arcs": 0.30, "entities": 0.20}),
}
# ---------------------------------------------------------------------------
# Shared style guide
# ---------------------------------------------------------------------------

_STYLE_GUIDE = """Стилевой канон книги (соблюдай во ВСЕХ прозаических фрагментах):
- Жанр: документальная non-fiction проза. Не художественный роман, но и не
  корпоративный отчёт. Ближе к «запискам» Довлатова или эссеистике Гениса,
  но суше, без анекдота ради анекдота.
- Аудитория: русскоязычные взрослые 45+, с широким кругозором и привычкой к
  длинному чтению. Не нужно объяснять, кто такой «подрядчик» или «CRM».
- Тон: спокойное достоинство. Не брызжет восторгом, не ноет. Умеет признать
  ошибку без самоуничижения и порадоваться удаче без бахвальства.
- Эмпатия: к собеседникам тоже. Даже «тяжёлый» клиент показывается как
  человек со своей правдой, а не как препятствие. Избегай ярлыков
  («токсичный», «сложный») — описывай поведение, а не ставь диагноз.
- Психологическая глубина (осторожно, только через условное наклонение):
  если поведение персонажа повторяется или читается как паттерн — предложи
  наблюдение-версию: «похоже, за этим упрямством стояло не несогласие по
  существу, а нежелание уступать на виду», «возможно, молчание Екатерины
  говорило больше, чем её слова». Это не клинический диагноз — это
  авторское наблюдение, поданное читателю как гипотеза.
  Обязательные маркеры: «похоже», «возможно», «судя по всему», «по всей
  видимости», «читается как». Максимум 1-2 таких интерпретации на главу.
  Не каждый персонаж нуждается в «разборе» — только те, чьё поведение
  явно прослеживается в нескольких ситуациях.
- Самоирония: уместная, короткая, без кривляния. Владелец может по-доброму
  посмеяться над собственной наивностью или упрямством, но не превращает
  книгу в стендап. Одна самоироничная реплика на главу — верхняя граница.
- Язык: живой русский, без канцелярита, без англицизмов сверх необходимого
  («митинг» можно, но лучше «встреча»), без молодёжного сленга.
- Никаких статистик, процентов, счётчиков («47 раз», «в 83% случаев»),
  никаких слов «звонок», «телефонный разговор», «созвон», «набрал номер».
  Вместо них: «тогда заговорили о…», «Василий вернулся с ответом через
  неделю», «в тот же вечер», «встреча в эфире».
- Не придумывай факты, реплики и новых персонажей — это беллетристика.
  Психологические версии мотивов — допустимы, но только через условное
  наклонение и только если поведение явно видно в материале (см. выше).
  Лакуны — честные: «что было потом — материалы умалчивают».
"""


# ---------------------------------------------------------------------------
# Pass 1 — Scene Extractor
# ---------------------------------------------------------------------------

_SCENE_SYS = """Ты литературный редактор-биограф. Тебе присылают запись одной
беседы. Твоя задача — превратить её в одну «сцену» для биографической книги
в жанре non-fiction для аудитории 45+.

Строго верни ОДИН JSON-объект, без markdown-оберток, без пояснений:
{
  "importance": 0-100,            // значимость сцены для книги
  "scene_type": "business|personal|conflict|joy|routine|transition",
  "setting": "короткая фраза об обстановке или контексте",
  "synopsis": "2-4 предложения, нарративно, как из книги; с уважением
                к обеим сторонам, без ярлыков; допустима лёгкая ирония",
  "key_quote": "одна реплика до 240 символов (дословная цитата из речи)",
  "emotional_tone": "tense|warm|neutral|worried|celebratory|angry|reflective",
  "named_entities": [
      {"name":"...", "type":"PERSON|PLACE|COMPANY|PROJECT|EVENT",
       "mention":"как именно упомянут"}
  ],
  "themes": ["до 3 тем одним словом-двумя"],
  "insight": "1 фраза: чем эта сцена важна для книги — нарративно,
               психологически или как узел более длинной истории.
               Можно назвать динамику: «оба ждали, кто уступит первым»,
               «Сергей, похоже, недооценил, насколько это важно для
               собеседника». Пустая строка — если сцена рутинная."
}

Правила:
- Не выдумывай ничего, чего нет в материале.
- Имена в named_entities — ровно как употреблены в транскрипте; в поле mention —
  точная форма из речи. Канонизацию делает следующий проход (p2).
- importance>=70 — только если сцена реально про решение, конфликт, открытие
  или поворот. Обычная сверка статуса = 10-30.
- Время беседы: если в данных указан час до 08:00 или после 22:00 — это значимый
  контекст. Добавь 10-20 к importance (если сцена не рутинная), отрази в setting
  («ранним утром», «посреди ночи»). Ночной контакт без причины редок.
- ДЛИТЕЛЬНОСТЬ — прямой сигнал важности. Разговор на 45 минут значительнее
  трёхминутного. Если длительность > 600 сек (10 мин) — добавь +10 к importance
  за каждые 600 сек сверх, максимум +30. Длинная беседа = глубокое обсуждение.
- В synopsis: без слов «звонок», «созвон», «телефонный разговор» —
  «беседа», «встреча в эфире», «разговор», «вернулись к теме».
- Эмпатия к собеседнику: даже неудобный клиент — человек со своей логикой,
  опиши поведение, а не клей ярлык.
- Если транскрипт пуст или мусор — importance=0, scene_type="routine",
  synopsis="", insight="".
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
    time_ctx = ""
    hour = _call_hour(call_datetime)
    if hour is not None:
        if hour < 6 or hour >= 22:
            time_ctx = (
                f"ВРЕМЯ БЕСЕДЫ: {hour:02d}:xx — ночной час "
                f"(значимый сигнал: ночной контакт без причины редок).\n"
            )
        elif hour < 8:
            time_ctx = (
                f"ВРЕМЯ БЕСЕДЫ: {hour:02d}:xx — до 8 утра "
                f"(вероятно, срочно или важно для собеседника).\n"
            )
    dur_ctx = ""
    if duration_sec is not None:
        if duration_sec >= 1800:
            dur_ctx = f"ДЛИТЕЛЬНАЯ БЕСЕДА: {duration_sec} сек (~{duration_sec//60} мин) — глубокое обсуждение, высокая значимость.\n"
        elif duration_sec >= 600:
            dur_ctx = f"БЕСЕДА СРЕДНЕЙ ДЛИНЫ: {duration_sec} сек (~{duration_sec//60} мин) — вероятно, содержательный разговор.\n"
    user = (
        f"Дата и время: {call_datetime or 'неизвестны'}\n"
        f"{time_ctx}"
        f"{dur_ctx}"
        f"Контакт: {contact_label}\n"
        f"Направление: {direction or '?'}\n"
        f"Длительность: {duration_sec or 0} сек\n\n"
        f"{prior}\n"
        f"Транскрипт ([me]=Сергей, [s2]=собеседник):\n"
        f"------\n{_clip(transcript, BUDGETS['p1_scene'].max_chars)}\n------\n\n"
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
        f"{json.dumps(payload['mentions'], ensure_ascii=False, indent=2)}"
        f"\n\nВерни JSON."
    )
    raw = json.dumps(payload['mentions'], ensure_ascii=False, indent=2)
    trimmed = BUDGETS['p2_entities'].trim_one(raw, "mentions")
    user = (
        f"Тип: {entity_type}\n"
        f"Упоминания (surface form + короткий контекст):\n"
        f"{trimmed}\n\n"
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
компании в хронологическом порядке. Напиши сюжетную линию в жанре
non-fiction для взрослой аудитории 45+.

Строго JSON:
{
  "title": "короткий заголовок линии (до 80 символов)",
  "summary": "3-6 абзацев: как развивались отношения или тема — завязка,
              узловые моменты, нынешнее состояние. От третьего лица,
              факты вперёд домыслов. Допустимы лёгкая ирония и эмпатия,
              но без психологизирования вслепую.",
  "turning_points": [
      {"scene_index": <int>, "why": "одна фраза: почему это поворот"}
  ],
  "open_questions": ["1-3 незакрытых вопроса, если есть"],
  "tension_curve": [<int 0-100 для каждой поданной сцены>]
}

Правила:
- Длина tension_curve == числу поданных сцен.
- scene_index в turning_points — индекс из входа (с нуля).
- Только факты из сцен; если чего-то не знаешь — так и оставь.
- Никаких «звонков»/«созвонов» — нейтральные формулировки.
- Если сцен мало или все однотипны — короткий summary, пустые массивы.
"""


def build_thread_prompt(entity_name: str, entity_type: str, scenes: list[dict], connections: list[str] | None = None) -> list[dict]:
    condensed = [
        {
            "date": s.get("call_datetime"),
            "importance": s.get("importance"),
            "tone": s.get("emotional_tone"),
            "synopsis": s.get("synopsis"),
            "key_quote": s.get("key_quote"),
            "insight": s.get("insight") or "",
        }
        for s in scenes
    ]
    conn_text = ""
    if connections:
        conn_text = "Связи с другими персонажами:\n" + "\n".join(f"  - {c}" for c in connections) + "\n\n"
    user = (
        f"Сущность: {entity_name} ({entity_type})\n"
        f"Всего сцен: {len(scenes)}\n"
        f"{conn_text}"
        f"{BUDGETS['p3_threads'].trim_one(json.dumps(condensed, ensure_ascii=False, indent=2), 'scenes')}\n\n"
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
темами). Найди МНОГОСЕРИЙНЫЕ арки: проблемы, которые тянулись несколько бесед;
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
        f"{BUDGETS['p4_arcs'].trim_one(json.dumps(condensed, ensure_ascii=False, indent=2), 'scenes')}\n\n"
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
компания, место) на основе досье. Жанр — non-fiction, аудитория 45+.

Строго JSON:
{
  "prose": "3-5 абзацев. Как персонаж появляется в жизни владельца, что их
            связывает, как менялся тон общения, какие эпизоды задержались в
            памяти. Тёплая сдержанность, уважение к человеку, допустима
            лёгкая самоирония владельца, если факты это поддерживают.
            Если поведение персонажа читается как устойчивый паттерн —
            дай одну осторожную интерпретацию: «похоже, за этой жёсткостью
            в переговорах стояло не высокомерие, а привычный способ держать
            дистанцию», «по всей видимости, Екатерина избегала прямых ответов
            именно тогда, когда решение ещё не было принято». Обязательно
            условное наклонение. Это делает портрет объёмным, не плоским.",
  "traits": ["до 6 коротких ярлыков-характеристик, основанных на поведении"],
  "relationship": "1 фраза — тип отношений с владельцем",
  "what_owner_learned": "1-2 предложения: чему владелец, похоже, научился от
                         этого человека или в ходе отношений. Только если это
                         читается в материале — иначе пустая строка.",
  "pivotal_scene_indices": [<индексы ключевых сцен из входа>]
}

Правила:
- Факты — из досье. Психологические версии мотивов — через условное наклонение,
  только если поведение явно повторяется. Если материала мало — короткий prose.
- Тон — журналистский, сдержанный, эмпатичный.
- Никаких ярлыков «токсичный/сложный/странный». Описание поведения — да;
  осторожная версия мотива («похоже») — да; клинический диагноз — нет.
- Имена — живое письмо, как звучат в материале (не форсируй «Василий»
  если в беседах «Вася»).
"""


def build_portrait_prompt(
    entity_name: str,
    entity_type: str,
    role: str | None,
    thread_summary: str | None,
    scenes: list[dict],
    behavior: dict | None = None,
    temperament: dict | None = None,
    big_five: dict | None = None,
    motivation: dict | None = None,
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
    behavior_section = ""
    if behavior:
        behavior_section = (
            f"\nПоведенческие сигналы (вычислены по {behavior.get('call_count', 0)} беседам):\n"
            f"  trust_score={behavior.get('trust_score', 50.0):.0f}/100"
            f" | конфликтов={behavior.get('conflict_count', 0)}"
            f" | роль={behavior.get('role_type', '?')}"
            f" | волатильность={behavior.get('volatility', 0.0):.1f}\n"
        )
    psych_section = ""
    if temperament or big_five or motivation:
        parts = []
        if temperament:
            parts.append(
                f"Темперамент: {temperament.get('type', '?')} "
                f"(энергия={temperament.get('energy')}, реактивность={temperament.get('reactivity')}, "
                f"~{temperament.get('calls_per_week', 0)} бесед/нед)"
            )
        if big_five:
            bf = big_five
            parts.append(
                f"Big Five: O={bf.get('openness',0):.1f} C={bf.get('conscientiousness',0):.1f} "
                f"E={bf.get('extraversion',0):.1f} A={bf.get('agreeableness',0):.1f} "
                f"N={bf.get('neuroticism',0):.1f}"
            )
        if motivation:
            prim = motivation.get("primary", "?")
            all_d = [d["driver"] for d in motivation.get("drivers", [])]
            parts.append(f"Мотивация: доминанта={prim}, драйверы={all_d}")
        psych_section = "\nПсихологический профиль (вычислен детерминированно, используй как основу для 'похоже/возможно'):\n" + "\n".join(f"  {p}" for p in parts) + "\n"
    user = (
        f"Персонаж: {entity_name} ({entity_type})\n"
        f"Роль: {role or 'не определена'}\n"
        f"Сюжетная линия: {thread_summary or '-'}\n"
        f"{behavior_section}"
        f"{psych_section}\n"
        f"Сцены (всего {len(scenes)}):\n"
        f"{BUDGETS['p5_portraits'].trim_one(json.dumps(condensed, ensure_ascii=False, indent=2), 'scenes')}\n\n"
        f"Верни JSON."
    )
    return [
        {"role": "system", "content": _PORTRAIT_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 6 — Chapter Writer (thematic prose chapter)
# ---------------------------------------------------------------------------

_CHAPTER_SYS = """Ты пишешь главу биографической книги в жанре non-fiction
для русскоязычной аудитории 45+ (технически прогрессивные читатели с широким
кругозором). Это не роман и не отчёт — скорее авторская проза на основе
документального материала.

""" + _STYLE_GUIDE + """

Структура главы:
# <Название главы — ёмкое, без дат, без слова «глава»>

<Вводный абзац: что это за отрезок жизни, какой у него вкус>

## <Подзаголовок смыслового блока>
<2-4 абзаца прозы>

## <Следующий блок>
<2-4 абзаца>

...

<Завершающий абзац: что осталось висеть в воздухе, какой вывод напрашивается
— но без морализаторства>

Дополнительные требования:
- Длина: в норме 2500-4500 слов; если материала мало — пиши честно и кратко.
  Короткая плотная глава лучше раздутой пустой.
- Подзаголовки `## ...`: 2-4 для полноценных глав; если глава короткая
  (мало материала) — достаточно 1-2 или без подзаголовков.
- Цитаты: 1-3 прямых из бесед, не больше. Формат: «…», — сказал Василий.
  Или: как потом пошутил Пётр Иванович, «…».
- Минимум одна сцена с эмпатией к собеседнику — даже если ситуация была
  конфликтной.
- Психологическое измерение: применяй правило стилевого канона (1-2 версии
  на главу, только «похоже»/«возможно», только если паттерн явно в материале).
- Имена — живое письмо. Только «Медведев Сергей» (полная ФИ) = владелец;
  просто «Сергей» в диалоге уточняй по контексту с упоминанием роли.
- Время суток: если в материале есть беседа в нестандартный час (ночь или до 8 утра) —
  упомяни это в прозе как деталь, подчёркивающую срочность или характер отношений.
  Цифры-времена суток допустимы («в два часа ночи»); запрещены только счётные цифры.
- Факты — только из поданных материалов. Лакуны честные: «материалы умалчивают».
- Верни ТОЛЬКО markdown главы. Без JSON, без пояснений.
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
    prev_chapter_context: str | None = None,
    yearly_context: str | None = None,
    entity_network: str | None = None,
) -> list[dict]:
    # Adaptive budget: portraits 50%, arcs 25%, scenes 25% of 17000 chars.
    scenes_slim = [
        {
            "date": s.get("call_datetime"),
            "with": [e.get("name") for e in (s.get("named_entities") or []) if isinstance(e, dict)],
            "tone": s.get("emotional_tone"),
            "synopsis": s.get("synopsis"),
            "key_quote": s.get("key_quote"),
            "insight": s.get("insight") or "",
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
    def _slim_fact(item: dict) -> dict:
        return {
            "date": item.get("date"),
            "type": item.get("type"),
            "quote": (item.get("quote") or "")[:180],
            "value": (item.get("value") or "")[:120],
            "status": item.get("status"),
            "confidence": item.get("confidence"),
        }

    portraits_slim = []
    for p in portraits:
        entry: dict = {
            "name": p.get("canonical_name"),
            "relationship": p.get("relationship"),
            "traits": p.get("traits"),
            "prose": (p.get("prose") or "")[:1200],
        }
        behavior = {}
        if p.get("trust_score") is not None:
            behavior["trust"] = f"{p['trust_score']:.0f}/100"
        if p.get("role_type"):
            behavior["role"] = p["role_type"]
        if p.get("call_count") is not None:
            behavior["calls"] = int(p["call_count"])
        if p.get("conflict_count") is not None:
            behavior["conflicts"] = int(p["conflict_count"])
        if p.get("volatility") is not None:
            behavior["volatility"] = round(float(p["volatility"]), 2)
        if p.get("dependency") is not None:
            behavior["dependency"] = round(float(p["dependency"]), 2)
        if p.get("initiator_out_ratio") is not None:
            behavior["owner_initiated_ratio"] = round(float(p["initiator_out_ratio"]), 2)
        if behavior:
            entry["behavior"] = behavior

        graph_profile = p.get("graph_profile") or {}
        if graph_profile:
            metrics = graph_profile.get("metrics") or {}
            entry["graph"] = {
                "entity_type": graph_profile.get("entity_type"),
                "metrics": {
                    "bs_index": metrics.get("bs_index"),
                    "avg_risk": metrics.get("avg_risk"),
                    "total_calls": metrics.get("total_calls"),
                    "broken_promises": metrics.get("broken_promises"),
                    "contradictions": metrics.get("contradictions"),
                },
                "temporal": graph_profile.get("temporal") or {},
                "social": graph_profile.get("social") or {},
                "patterns": (
                    graph_profile.get("psychology_patterns")
                    or (p.get("behavioral_patterns") or {}).get("patterns")
                    or []
                )[:6],
                "facts": [_slim_fact(f) for f in (graph_profile.get("top_facts") or [])[:3]],
                "conflicts": [_slim_fact(f) for f in (graph_profile.get("conflicts") or [])[:2]],
                "promises": [_slim_fact(f) for f in (graph_profile.get("promise_chain") or [])[-3:]],
                "relations": (graph_profile.get("top_relations") or [])[:4],
                "psychology": (
                    graph_profile.get("psychology_summary")
                    or graph_profile.get("interpretation")
                    or ""
                )[:700],
            }
        portraits_slim.append(entry)

    scenes_json = json.dumps(scenes_slim, ensure_ascii=False, indent=2)
    arcs_json = json.dumps(arcs_slim, ensure_ascii=False, indent=2)
    portraits_json = json.dumps(portraits_slim, ensure_ascii=False, indent=2)

    allocated = BUDGETS['p6_chapters'].allocate({
        "scenes": scenes_json,
        "arcs": arcs_json,
        "portraits": portraits_json,
    })

    user = (
        f"Глава {chapter_num}. Рабочее название: «{title}»\n"
        f"Период: {period_start or '?'} — {period_end or '?'}\n"
        f"Тема главы: {theme}\n"
        + (f"\n📖 Контекст предыдущей главы (для связности):\n{prev_chapter_context}\n" if prev_chapter_context else "")
        + (f"\n🌍 Годовая рамка: {yearly_context}\n" if yearly_context else "")
        + (f"\n🔗 Сеть связей между персонажами:\n{entity_network}\n" if entity_network else "")
        + f"\nПортреты ключевых участников:\n{allocated['portraits']}\n\n"
        f"Арки в этом периоде:\n{allocated['arcs']}\n\n"
        f"Сцены ({len(scenes)} шт.):\n{allocated['scenes']}\n\n"
        f"Напиши главу по всем правилам канона. "
        f"Если материала достаточно — развёртывай до 2500-4500 слов; "
        f"если мало — пиши честно и кратко."
    )
    return [
        {"role": "system", "content": _CHAPTER_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 7 — Book Assembler (prologue + TOC + epilogue synthesis)
# ---------------------------------------------------------------------------

_BOOK_FRAME_SYS = """Ты пишешь каркас биографической книги в жанре non-fiction:
название, подзаголовок, эпиграф, пролог и эпилог. Аудитория — русскоязычные
взрослые 45+, с широким кругозором. Имя владельца: Сергей Медведев.

""" + _STYLE_GUIDE + """

Верни строго ОДИН JSON:
{
  "title": "название книги (до 80 символов). Не пафосное, не ироническое до
            шутовства. Скорее спокойное и точное.",
  "subtitle": "подзаголовок (до 140 символов) — уточняет, о чём книга",
  "epigraph": "одна цитата из материала, или короткое авторское предложение.
               Можно оставить пустой строкой, если ничего не подошло.",
  "prologue": "3-5 абзацев: кто герой, как устроена книга (записи бесед,
               собранные в сюжеты), почему читателю это может быть интересно.
               Допустима самоироничная оговорка: «автор не обещает откровений
               века — только честный взгляд на несколько лет жизни».",
  "epilogue": "3-5 абзацев: сквозные мотивы, открытые линии, что поменялось в
               герое за период. Без морали и без «выводов для читателя».",
  "toc": [
    {"chapter_num": <int>, "title": "...", "one_liner": "одна фраза-аннотация"}
  ]
}

Правила:
- Русский язык, третье лицо в прологе и эпилоге.
- Не превращай книгу в бизнес-кейс и не заигрывай с читателем.
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
        f"{BUDGETS['p7_book'].trim_one(json.dumps(chapters_slim, ensure_ascii=False, indent=2), 'chapters')}\n\n"
        f"Главные арки:\n"
        f"{BUDGETS['p7_book'].trim_one(json.dumps(arcs_slim, ensure_ascii=False, indent=2), 'arcs')}\n\n"
        f"Главные персонажи/места:\n"
        f"{BUDGETS['p7_book'].trim_one(json.dumps(ents_slim, ensure_ascii=False, indent=2), 'entities')}\n\n"
        f"Верни JSON-каркас."
    )
    return [
        {"role": "system", "content": _BOOK_FRAME_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 8 — Editorial Pass (polish one chapter)
# ---------------------------------------------------------------------------

_EDITORIAL_SYS = """Ты редактор non-fiction книги для взрослой аудитории 45+.
Тебе дан черновик главы. Задача — довести его до уровня книги, а не
черновика: убрать повторы, сраcтить абзацы, выровнять тон, вычистить
канцелярит и любые упоминания цифр/длительности/«звонков».

""" + _STYLE_GUIDE + """

Что конкретно нужно сделать:
- Срастить разрозненные абзацы в связный поток; убрать «во-первых/во-вторых»,
  нумерацию там, где это сбивает на отчётность.
- Усилить 1-2 места коротким эпизодом-картинкой (одно предложение, без
  вымысла — только на основании уже приведённых в черновике фактов).
- Проверь, что в черновике есть: хотя бы одна цитата из беседы, хотя бы
  одна эмпатическая нота, не более одной самоироничной реплики. Если
  чего-то нет — не добавляй искусственно; только перераздели акценты в
  уже имеющемся тексте, не изобретай нового.
- Психологическое измерение: если персонажи плоские И в черновике уже
  описано несколько похожих ситуаций с одним человеком — добавь одно
  наблюдение-версию через «похоже»/«возможно». Если паттерн не просматривается
  — не форсируй; не каждый персонаж нуждается в «разборе».
- Сохранить все имена, даты, события. Не вводить новых персонажей, не
  изобретать реплик.
- Объём — как в черновике (+/- 15%). Не растягивай ради количества.

Верни ТОЛЬКО отредактированный markdown-текст главы (с # заголовком).
Без JSON, без пояснений, без «вот исправленная версия».
"""


def build_editorial_prompt(chapter_prose: str) -> list[dict]:
    user = (
        "Отредактируй главу ниже по правилам non-fiction для аудитории 45+.\n"
        "Сохрани примерный объём и все факты.\n\n"
        f"{BUDGETS['p8_editorial'].trim_one(chapter_prose, 'prose')}"
    )
    return [
        {"role": "system", "content": _EDITORIAL_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Pass 9 — Yearly Summary (Dovlatov-style annual retrospective)
# ---------------------------------------------------------------------------

_YEARLY_SYS = """Ты пишешь годовой итог биографической книги. Имя владельца:
Сергей Медведев. Третье лицо.

""" + _STYLE_GUIDE + """

Специфика годового итога:
- Не пересказывай главы подряд — ищи СКВОЗНЫЕ МОТИВЫ: что повторялось,
  что менялось, что так и не разрешилось.
- Тон — рефлексивный, как у Довлатова: спокойный, без морали, с иронией
  и уважением к читателю. Пример интонации: «Год прошёл — как обычно,
  с ощущением, что всё важное случилось чуть в стороне от плана».
- 3-5 абзацев. Без подзаголовков. Без списков. Без резюме «в заключение».
- Верни ТОЛЬКО markdown-текст (без JSON, без пояснений).
"""


def build_yearly_summary_prompt(
    year: int,
    chapters: list[dict],
    top_arcs: list[dict],
    top_entities: list[dict],
    psychology_profiles: list[str] | None = None,
) -> list[dict]:
    chapters_slim = [
        {
            "period": (c.get("period_start") or "")[:7],
            "title": c.get("title"),
            "theme": c.get("theme"),
            "excerpt": (c.get("prose") or "")[:400],
        }
        for c in chapters
    ]
    arcs_slim = [
        {
            "title": a.get("title"),
            "type": a.get("arc_type"),
            "status": a.get("status"),
            "outcome": a.get("outcome"),
        }
        for a in top_arcs[:12]
    ]
    ents_slim = [
        {"name": e.get("canonical_name"), "role": e.get("role")}
        for e in top_entities[:15]
    ]
    user = (
        f"Год: {year}\n\n"
        f"Главы года:\n"
        f"{BUDGETS['p9_yearly'].trim_one(json.dumps(chapters_slim, ensure_ascii=False, indent=2), 'chapters')}\n\n"
        f"Главные арки:\n"
        f"{BUDGETS['p9_yearly'].trim_one(json.dumps(arcs_slim, ensure_ascii=False, indent=2), 'arcs')}\n\n"
        f"Ключевые персонажи/места:\n"
        f"{BUDGETS['p9_yearly'].trim_one(json.dumps(ents_slim, ensure_ascii=False, indent=2), 'entities')}\n"
        + (f"\nПсихологические профили ключевых персонажей:\n" + "\n---\n".join(psychology_profiles) + "\n"
           if psychology_profiles else "")
        + f"\nНапиши годовой итог: 3-5 абзацев, без подзаголовков, без морали."
    )
    return [
        {"role": "system", "content": _YEARLY_SYS},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_hour(call_datetime: str | None) -> int | None:
    """Extract hour (0-23) from ISO-like datetime string, return None if not parseable."""
    if not call_datetime:
        return None
    for sep in ("T", " "):
        if sep in call_datetime:
            try:
                return int(call_datetime.split(sep)[1][:2])
            except (ValueError, IndexError):
                pass
    return None


def _clip(s: str, limit: int) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    half = limit // 2
    return s[:half] + "\n\n[... SKIPPED ...]\n\n" + s[-half:]

