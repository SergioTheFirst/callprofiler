# LLM Rules

- Server: llama-server at http://127.0.0.1:8080/v1/chat/completions (OpenAI format)
- Use requests.post() directly. No openai SDK. No Ollama API.
- Prompt template: configs/prompts/analyze_v001.txt
- prompt_version field in analyses tracks which version produced result
- JSON parsing: strip markdown fences → extract {…} → fix truncated → dict.get(key, default)
- If parse fails completely: save raw_llm, return Analysis with defaults, mark as partial
- Timeout: 120 seconds per request
- Roles in transcript: [me]=owner, [s2]=other. Roles may be swapped.
- "Сергей/Серёжа/Серёж/Медведев/Сергей Станиславович" = ALWAYS owner (Сергей Станиславович Медведев) regardless of label.
- **Промпт v002 (T-14, 2026-08-22):** `PROMPT_VERSION_ANALYZE='v002'` (`analyze/service.py`; bulk/canary/
  orchestrator берут оттуда, литералов `"v001"` нет). `configs/prompts/analyze_v002.txt`: владелец —
  плейсхолдер `{{owner_name}}` (из `users.display_name` текущего user_id; одна строка ≤80 симв.;
  нет → «владелец телефона (имя неизвестно)»), никаких захардкоженных имён; правило «данные ≠
  инструкции». `PromptBuilder.build`: ВСЕ данные (метаданные, прошлые summary, стенограмма) внутри ОДНОГО
  `<данные>…</данные>`; `</данные>` внутри данных нейтрализуется (`</данные >`); клип стенограммы
  `prompt_budget.clip_transcript_for_llm` (head ⅓ + middle + tail ¼, маркеры пропусков) до
  `models.prompt_max_chars` (12000); длительность из `duration_ms`/`duration_sec`, 0 → «неизвестна».
  Старое правило «>3000 → 1500+1500» в коде никогда не существовало.

## Мемоизация analyze-пути (M3, `llm_cache.py`, decisions.md 2026-06-04 #1)

- Таблица `llm_calls(cache_key PK, user_id, prompt_version, response, finish_reason)`,
  идемпотентно создаётся `apply_llm_cache_schema()` при первой передаче `cache_conn` в `LLMClient`.
- Ключ (T-13, 2026-08-08) = `sha1(messages + temperature + max_tokens + prompt_version + json_mode
  + **user_id** + **model_fingerprint**)`. `user_id` добавлен для изоляции профилей;
  `model_fingerprint` заполняется только если вызывающий заранее позвал `check_ready()`
  (`/v1/models`), иначе пустой — ограничение зафиксировано, фиктивный отпечаток не выдумывается.
  Старые строки `llm_calls` (без `user_id` в ключе) просто перестают попадаться, НЕ удаляются.
- `LLMClient(cache_conn=None)` — поведение прежнее (без кэша, обратная совместимость: biography/graph
  зовут как раньше). Только call-analysis путь (`AnalysisService.__init__`, `bulk_enrich()`) передаёт
  `cache_conn=repo._get_conn()`. **Ни сбой, ни усечение НЕ кэшируются** (T-13, 2026-08-08):
  временный отказ llama-server иначе залип бы навсегда, а `finish_reason='length'` — это
  неполный JSON, который repair-парсер достраивает догадкой; закэшировав его, мы зафиксировали
  бы догадку навечно (все прогоны возвращали бы тот же обрубок, ни разу не сходив к серверу —
  ровно «stale/incomplete как успех», P-LLM-06). Вызывающему обрубок по-прежнему возвращается —
  решение, что с ним делать, принимает он. Прежний тест `test_truncated_response_cached_as_is`
  закреплял старое поведение и заменён на `test_truncated_response_absent_from_cache`.
- **Конструктор `LLMClient` не ходит в сеть** (T-13): проверка доступности вынесена в
  `check_live()` (`/health`) / `check_ready()` (`/v1/models`, fallback на 1-токенный completion
  для старых сборок) / `ensure_ready()` — последняя поднимает тот же `ConnectionError`, что
  раньше бросал конструктор, поэтому контракт «exit 2 при мёртвом сервере» у `ask`/`bulk`/
  `deep-extract`/`biography` сохранён. Пробы в кэш не пишут. Невалидный ответ транспорта →
  типизированный `LLMDecodeError` вместо тихого `text=None`.
- `bio_llm_calls` (biography) и per-row кэши insight (age/ask/promise) НЕ унифицированы с
  `llm_calls` — отдельная мемоизация, сознательно (blast radius).

## JSON-режим + canary (M4)

- `features.yaml: llm_json_mode` (default `false`) → `LLMClient.complete(..., json_mode=True)`
  добавляет `response_format: {"type":"json_object"}` в тело запроса. `json_mode` входит в
  ключ кэша (`make_key`) — иначе True/False делили бы чужой кэш на одних messages.
- `canary-analyze --user X [--n 50] [--out FILE]` (`analyze/canary.py::run_canary`) гоняет
  выборку ДВАЖДЫ (False/True) существующим `PromptBuilder`+`parse_llm_response`, отчёт —
  parse_status/truncated%/пустые promises-entities. Пишет НИЧЕГО в БД (client без cache_conn).
  Включать `llm_json_mode` — решение юзера ПОСЛЕ чтения отчёта; старые сборки llama-server
  игнорируют поле молча, repair-парсер остаётся навсегда.

## `ask` — вопрос к архиву (A2)

- `ask.py`: FTS5 OR-поиск по токенам вопроса (НЕ phrase-match — `search_transcripts` в
  repository.py делает phrase, для NL-вопросов нужен OR) → top-k фрагментов → LLM-синтез
  прозой со ссылками `[n]`. Ссылки извлекаются regex-ом из ответа и мапятся на НАШИ метаданные
  фрагмента — модели не доверяем в атрибуции контакта/даты, только в факте цитирования.
  `json_mode` НЕ используется (ответ — проза).
- **Инъекция-гард (§4.1, инвариант 12):** фрагменты обёрнуты `<фрагменты>...</фрагменты>` +
  system-промпт (`configs/prompts/ask_v001.txt`) явно требует игнорировать любые
  "инструкции" внутри фрагментов — это чужой текст (транскрипты), не команды модели.
- Свой кэш `ask_log` (`apply_ask_schema`, sha1(messages+version)) — НЕ унифицирован с
  `llm_cache.llm_calls` (M3): разная форма запроса/ответа (citations_json), сознательно.
