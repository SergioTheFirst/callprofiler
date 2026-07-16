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
- Max input: if transcript > 3000 chars → first 1500 + "[...]" + last 1500

## Мемоизация analyze-пути (M3, `llm_cache.py`, decisions.md 2026-06-04 #1)

- Таблица `llm_calls(cache_key PK, user_id, prompt_version, response, finish_reason)`,
  идемпотентно создаётся `apply_llm_cache_schema()` при первой передаче `cache_conn` в `LLMClient`.
- Ключ = `sha1(json.dumps(messages,sort_keys=True) + "|"+temperature+"|"+max_tokens+"|"+prompt_version)`.
- `LLMClient(cache_conn=None)` — поведение прежнее (без кэша, обратная совместимость: biography/graph
  зовут как раньше). Только call-analysis путь (`AnalysisService.__init__`, `bulk_enrich()`) передаёт
  `cache_conn=repo._get_conn()`. **Сбой (`text=None`) НЕ кэшируется** — иначе временный отказ
  llama-server залип бы навсегда; truncated (`finish_reason='length'`) кэшируется как есть.
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
