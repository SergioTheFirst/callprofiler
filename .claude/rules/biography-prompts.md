# Biography Prompt Rules

Contract для промптов модуля biography. Все промпты живут в
`src/callprofiler/biography/prompts.py`, адресуют локальный llama-server
(Qwen-класс), русский язык ввода и вывода.

---

## Global conventions

- `PROMPT_VERSION` (в начале `prompts.py`) — текущая версия. При смене
  **любого** system-prompt'а бампнуть, чтобы поломать memoization
  (`bio_llm_calls.prompt_hash`).
- System message = роль + строгий контракт на формат вывода.
- User message = данные + явные подписи полей.
- Output:
  - JSON-проходы (p1, p2, p3, p4, p5, p7 frame): **ОДИН JSON-объект**,
    без markdown-оборачиваний, без пояснений.
  - Прозаические (p6 chapter, p8 edited chapter): **только markdown**,
    без JSON, без «вот ваша глава».
- Язык вывода: **русский**. Имя владельца — Сергей Медведев.

---

## Per-pass contracts

### Pass 1 — Scene Extractor (`build_scene_prompt`)

**Input:**
- `call_datetime`, `contact_label`, `direction`, `duration_sec`
- `prior_analysis`: `{call_type, risk_score, summary, key_topics}` из
  `analyses` (context hint, не копировать дословно)
- `transcript` (клипается до 6000 символов head+tail)

**Output JSON:**
```json
{
  "importance": 0-100,
  "scene_type": "business|personal|conflict|joy|routine|transition",
  "setting": "короткая фраза",
  "synopsis": "2-4 предложения нарратива",
  "key_quote": "реплика до 240 символов",
  "emotional_tone": "tense|warm|neutral|worried|celebratory|angry|reflective",
  "named_entities": [{"name":"...", "type":"PERSON|PLACE|COMPANY|PROJECT|EVENT", "mention":"..."}],
  "themes": ["до 3"],
  "insight": "1 фраза: нарративная/психологическая важность сцены или пусто"
}
```

**Quote extraction rules:**
- `key_quote` — **дословная** цитата из транскрипта, не перифраз.
- Обрезать ≤ 240 символов, не ломая слово (ellipsis `…`).
- Если ничего выразительного нет — пустая строка.
- Не включать номера телефонов, email, реквизиты (см. `biography-data.md`
  → Anonymization).

**Failure mode:** `importance=0, scene_type="routine", synopsis="", insight=""`.

---

### Pass 2 — Entity Resolver (`build_entity_prompt`)

**Input:**
- `entity_type`: `PERSON|PLACE|COMPANY|PROJECT|EVENT`
- `mentions`: список `{name, context}` для одного type
  (чанки по CHUNK_SIZE=~30, обрезается до 10000 символов)

**Output JSON:**
```json
{
  "entities": [
    {
      "canonical": "каноническая форма",
      "aliases": ["все варианты, включая каноническое"],
      "role": "colleague|client|supplier|friend|family|null",
      "description": "1-2 предложения кто/что это"
    }
  ]
}
```

**Merge rule:** при совпадении ≥2 форм → объединять. При одном совпадении
и разном контексте → не объединять.

---

### Pass 3 — Thread Builder (`build_thread_prompt`)

**Input:**
- `entity_name`, `entity_type`
- `scenes`: список сцен одного entity в хронологии
  (condensed: date, importance, tone, synopsis, key_quote)

**Output JSON:**
```json
{
  "title": "≤80 символов",
  "summary": "3-6 абзацев",
  "turning_points": [{"scene_index": <int>, "why": "..."}],
  "open_questions": ["1-3 незакрытых вопроса"],
  "tension_curve": [<int 0-100>, ...]
}
```

**Invariant:** `len(tension_curve) == len(scenes)`.

---

### Pass 4 — Arc Detector (`build_arc_prompt`)

**Input:** sliding window сцен (60 с шагом 30), condensed.

**Output JSON:**
```json
{
  "arcs": [
    {
      "title": "короткий заголовок",
      "arc_type": "problem|project|relationship|life_event",
      "status": "ongoing|resolved|abandoned",
      "synopsis": "завязка → развитие → итог",
      "scene_indices": [<int>, ...],
      "entity_names": ["..."],
      "outcome": "чем закончилось",
      "importance": 0-100,
      "start_date": "YYYY-MM-DD или null",
      "end_date": "YYYY-MM-DD или null"
    }
  ]
}
```

**Constraints:** ≥2 сцены/арка, ≤20 арок/окно, сортировка по `importance` убыв.

---

### Pass 5 — Portrait Writer (`build_portrait_prompt`)

**Input:**
- `entity_name`, `entity_type`, `role`
- `thread_summary` (из p3, если есть)
- `scenes`: ключевые сцены (condensed)

**Output JSON:**
```json
{
  "prose": "3-5 абзацев",
  "traits": ["до 6 ярлыков, основанных на поведении"],
  "relationship": "1 фраза",
  "what_owner_learned": "1-2 предложения или пусто",
  "pivotal_scene_indices": [<int>, ...]
}
```

**Style requirement:** эмпатия к персонажу, без ярлыков-диагнозов.
Допустима 1 психологическая интерпретация поведенческого паттерна — только
через «похоже»/«возможно»/«по всей видимости» и только если паттерн явно
виден в нескольких сценах. Это делает портрет объёмным, а не плоским.

---

### Pass 6 — Chapter Writer (`build_chapter_prompt`)

**Input (data_json):**
```
chapter_num, title, period_start, period_end, theme
portraits: [{name, relationship, traits, prose (≤1200 симв.)}]  # top-6
arcs:      [{title, type, status, synopsis, outcome}]            # all in period
scenes:    [{date, with, tone, synopsis, key_quote}]             # top-40 by importance
```

Лимиты JSON в user message: portraits=6000, arcs=4500, scenes=9000 символов.

**Output:** **только markdown** главы. Контракт структуры —
`biography-style.md` → «Structure of a chapter».

**Требования к прозе:**
- 2500-4500 слов.
- 2-4 подзаголовка `## …`.
- 1-3 прямых цитаты (key_quote из данных, дословно).
- ≥1 эмпатическая сцена.
- 1-2 психологических наблюдения о поведенческих паттернах (через
  «похоже», «возможно», «по всей видимости»). Только если паттерн явно
  виден в материале. Делает персонажей объёмными.
- ≤1 самоироничная реплика владельца.
- Имена — канонические.
- Никаких цифр количества, никаких слов «звонок/созвон».

---

### Pass 7 — Book Frame (`build_book_frame_prompt`)

**Input:**
- `chapters`: список глав с `n, title, theme, period`
- `top_arcs` (≤15), `top_entities` (≤20)
- `period_start`, `period_end`

**Output JSON:**
```json
{
  "title": "≤80",
  "subtitle": "≤140",
  "epigraph": "цитата или пусто",
  "prologue": "3-5 абзацев",
  "epilogue": "3-5 абзацев",
  "toc": [{"chapter_num": <int>, "title": "...", "one_liner": "..."}]
}
```

---

### Pass 8 — Editorial (`build_editorial_prompt`)

**Input:** `chapter_prose` (весь черновик главы, до 20000 символов).

**Output:** **отредактированный markdown** (с `# заголовком`).

**Что делает:**
- Убирает повторы, срастает абзацы.
- Вычищает канцелярит, цифры количества, слова «звонок/созвон».
- Усиливает 1-2 места коротким эпизодом-картинкой (без вымысла).
- Обеспечивает минимум 1 цитата / 1 эмпатическая нота / ≤1 самоирония.
- Проверяет психологическую объёмность: если персонажи плоские — добавляет
  1-2 наблюдения-версии поведенческих паттернов (через «похоже»/«возможно»),
  только на основе уже описанных фактов.
- Сохраняет все имена, даты, события.
- Объём ±15%; если черновик < 2500 слов — можно расширить до 3000-3500.

---

## Quote extraction conventions

- Цитаты извлекаются из `transcripts.text` через `key_quote` поля сцен.
- Формат в prose:
  ```
  «Нам нужна опора на юге», — сказал Василий.
  ```
  или
  ```
  Как потом заметил Пётр Иванович, «это вообще не про деньги».
  ```
- Один абзац ≤ 1 цитаты.
- В главе 1-3 цитаты; не больше.
- Если цитата содержит PII (номер, email) — не использовать её.

---

## Versioning workflow

1. Изменил system prompt → `PROMPT_VERSION = "bio-vN+1"`.
2. Коммит с пометкой в `CHANGELOG.md` секция `Changed`.
3. При следующем `biography-run` — старые ответы в `bio_llm_calls`
   остаются для аудита (не удаляем), но новые запросы с новым hash
   вызывают LLM заново.
4. Для целенаправленного A/B сравнения — сохранять старые главы с
   `version_label = "bio-v1"`, новые — `version_label = "bio-v2"`.
