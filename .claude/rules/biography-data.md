# Biography Data Rules

Data contracts for the 8-pass biography pipeline. Все запросы ВСЕГДА
фильтруют по `user_id` (`.claude/rules/db.md`).

---

## Source data

### Из основной схемы

- `calls` — `call_id`, `user_id`, `contact_id`, `call_datetime`, `direction`,
  `duration_sec`, `status`, `source_filename`
- `transcripts` — `call_id`, `speaker` (`OWNER`|`OTHER`|`UNKNOWN`), `text`,
  `start_ms`
- `analyses` — `priority`, `risk_score`, `summary`, `call_type`, `hook`,
  `key_topics`, `raw_response`
- `contacts` — `display_name`, `guessed_name`, `phone_e164`

### SQL для Pass 1 (scene extraction)

```sql
-- Все звонки пользователя, упорядоченные хронологически
SELECT c.call_id, c.contact_id, c.call_datetime, c.direction,
       c.duration_sec, c.status, c.source_filename
  FROM calls c
 WHERE c.user_id = ?
 ORDER BY COALESCE(c.call_datetime, c.created_at);

-- Текст транскрипта (с префиксами ролей [me] / [s2] / [?])
SELECT t.speaker, t.text
  FROM transcripts t
  JOIN calls c ON c.call_id = t.call_id
 WHERE t.call_id = ? AND c.user_id = ?
 ORDER BY t.start_ms;

-- Снимок предыдущего анализа (prior context для LLM)
SELECT a.priority, a.risk_score, a.summary, a.call_type, a.hook,
       a.key_topics, a.raw_response
  FROM analyses a
  JOIN calls c ON c.call_id = a.call_id
 WHERE a.call_id = ? AND c.user_id = ?;
```

---

## Thresholds

### Scene importance (p1 output → p6 selection)

- `0-10`   — шум, пустой/мусорный транскрипт, не идёт в главы
- `11-30`  — рутинная сверка, упоминание только в общем ряду
- `31-69`  — рабочая сцена, может попасть в главу как фон
- `70-100` — узловая сцена, кандидат в chapter highlight / arc anchor

### Entity merge (p2)

- Если `aliases` двух mention-ов совпадают ≥ 2 формами → мерджим.
- Если только одно совпадение, но разные контексты (разные компании /
  роли / периоды) — НЕ мерджим. При сомнении — не объединяем.
- Минимум упоминаний для отдельного portrait: `mention_count >= 3` ИЛИ
  `importance_sum >= 150`.

### Thread build (p3)

- `MIN_MENTIONS = 3` — ниже не строим thread.
- `MAX_SCENES_PER_THREAD = 40` — если больше, берём top-N по importance
  и пересортировываем по дате.

### Arc detection (p4)

- Минимум 2 сцены на арку; одиночные сцены не выделяем.
- Максимум 20 арк на окно.
- Sliding window: 60 сцен с шагом 30 (overlap) — чтобы не потерять арки
  на стыках.

### Chapter assembly (p6)

- Окно: календарный месяц (`YYYY-MM`), либо узловой арк (custom).
- Top-40 сцен по `importance` для каждого окна.
- Портреты: top-6 сущностей, встретившихся в окне.
- Длина главы: **2500-4500 слов**. При меньшем материале — 1500-2500.

---

## Anonymization / PII rules

- Фамилии в книге — только если они уже звучат в транскрипте как часть
  бытовой речи («Медведев», «Петрович»). Паспортные полные ФИО,
  появляющиеся только в контексте формальностей, — заменять на
  уменьшительные или роль («знакомый юрист»).
- Номера телефонов, ИНН, номера карт/счетов, паспортные данные —
  **никогда** в prose. Даже если они были в транскрипте.
- Email и ссылки — не включать в цитаты.
- Названия компаний — можно, это публичная информация. Внутренние
  проекты/продукты — по возможности обобщать, если звучит как
  коммерческая тайна.
- Даты — до дня уместны («15 февраля»), но не обязательны: часто
  лучше «в начале февраля».

---

## Idempotency invariants

- `p1 → bio_scenes`: UPSERT по `call_id`. Повторный run с `status='failed'`
  — перезапишет.
- `p2 → bio_entities`: UPSERT по `(user_id, canonical_lower, entity_type)`;
  aliases аддитивно мерджатся.
- `p3 → bio_threads`: UPSERT по `(user_id, entity_id)`.
- `p4 → bio_arcs`: `clear_arcs(user_id)` + insert — полный перегенерат.
- `p5 → bio_portraits`: UPSERT по `(user_id, entity_id)`.
- `p6 → bio_chapters`: UPSERT по `(user_id, chapter_num, period_start)`.
- `p7 → bio_books`: новая запись при каждом run (`version_label`).
- `p8 → bio_chapters.prose`: заменяет prose in-place, выставляет
  `status='edited'`.
- `bio_checkpoints` — per-pass прогресс (`items_processed`, `items_failed`,
  `last_item_key`), позволяет resume.
- `bio_llm_calls` — memoization по MD5(messages+temp+max_tokens+model);
  если `prompt_hash` совпал, LLM не зовётся, берём из кэша.

---

## Resume protocol

После падения любого прохода:

1. `biography-status --user X` — показывает per-pass checkpoints.
2. Перезапуск `biography-run --user X --passes p1,p2,...` пропустит уже
   сделанные элементы (`scene_exists`, `already_canonicalized`, и т.п.).
3. LLM-кэш переживает крэш: повторные запросы с тем же hash не платят
   токенами.
4. Если сменили промпт (`PROMPT_VERSION` bump) — кэш поломается, proof
   answers будут новые; старые записи в `bio_llm_calls` остаются для аудита.

---

## When to drop cache

- Bump `PROMPT_VERSION` в `prompts.py` (например `bio-v2 → bio-v3`).
- Не чистим таблицу: пусть старые версии лежат для сравнения качества.
- Для полного пересчёта одного прохода: `DELETE FROM bio_checkpoints
  WHERE pass_name = ? AND user_id = ?` + (где уместно) TRUNCATE
  соответствующей output-таблицы через явный migration-скрипт.
