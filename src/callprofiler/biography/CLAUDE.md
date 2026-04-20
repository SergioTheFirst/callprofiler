# Biography Module

Генерация книги-биографии из транскриптов владельца. Многодневный локальный
прогон на llama-server. Читатель — не владелец (для него это зеркало), а
взрослый знакомый 45+ с широким кругозором.

## Mission

Сырой журнал бесед → связная non-fiction книга: со сценами, персонажами,
арками, главами и прологом. Стиль — спокойное достоинство, эмпатия к
собеседникам, умеренная самоирония владельца, без статистик и цифр.

## Inputs

- `calls`, `transcripts`, `analyses`, `contacts` из основной БД
  (фильтр по `user_id` ВСЕГДА, см. `.claude/rules/db.md`).
- `prior_analysis` (из `analyses`): call_type, summary, key_topics, risk —
  контекст для scene-экстрактора, снижает галлюцинации.

## Outputs

- `bio_scenes` — одна строка на звонок (importance, synopsis, key_quote…)
- `bio_entities` — канонические люди/места/компании + aliases
- `bio_threads` — сюжетные линии по одной сущности
- `bio_arcs` — многосценные арки (проблема/проект/отношения/событие)
- `bio_portraits` — литературные портреты повторяющихся персонажей
- `bio_chapters` — главы (месячные), 2500-4500 слов при достаточном материале
- `bio_books` — итоговая сборка (frame + stitched prose)
- `bio_checkpoints` — resume-состояние по каждому проходу
- `bio_llm_calls` — memoization (MD5-ключ → ответ)

## Pipeline (8 passes, all idempotent)

```
p1_scene     call      → bio_scenes         (per-call narrative unit)
p2_entities  mentions  → bio_entities       (canonicalize aliases)
p3_threads   entity    → bio_threads        (per-entity arc)
p4_arcs      windows   → bio_arcs           (multi-scene arcs)
p5_portraits entity    → bio_portraits      (character sketches)
p6_chapters  month     → bio_chapters       (thematic prose, 2500-4500 слов при достаточном материале)
p7_book      all       → bio_books          (frame + TOC + stitched)
p8_editorial chapter   → bio_chapters       (polish pass, version=final)
```

## Chapter types (p6 themes)

- По месяцам (основной режим): «Ноябрь 2024» / «Зима 2024-2025»
- По сюжетным узлам: один большой арк = одна глава
- Портретные главы: ключевой человек на фоне периода

## Principles

- Никаких цифр, процентов, слов «звонок/созвон/телефонный разговор».
- Эмпатия к собеседнику, даже трудному. Ярлыки запрещены.
- Самоирония владельца — не более одной реплики на главу.
- Факты только из материалов. Лакуны — честные, без домысла.
- Имена — живое письмо, как в материале (не механическое каноничение).
- Owner = Сергей Медведев; в тексте — от третьего лица.

## See also

- `.claude/rules/biography-data.md` — SQL, пороги, анонимизация
- `.claude/rules/biography-style.md` — тон, длина, запреты
- `.claude/rules/biography-prompts.md` — контракты промптов
- `.claude/rules/narrative-journal.md` — смежная архитектура событий

## Max tokens per pass (bio-v4; current: bio-v5)

p1=1800, p2=3800, p3=2500, p4=4200, p5=2500, p6=5500, p7=3500, p8=5500.
При смене промптов — бампни `PROMPT_VERSION` в `prompts.py`, чтобы
поломать memoization и получить свежие ответы.
