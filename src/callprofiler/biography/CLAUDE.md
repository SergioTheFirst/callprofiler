# Biography Module

Генерация книги-биографии из транскриптов владельца. Многодневный локальный
прогон на llama-server. Читатель — взрослый знакомый 45+ с широким кругозором.

## Mission

Сырой журнал бесед → связная non-fiction книга: со сценами, персонажами, арками, главами и прологом.

Стиль: спокойное достоинство, эмпатия к собеседникам, умеренная самоирония владельца.

## Pipeline (11 passes, all idempotent)

```
p1_scene        call → bio_scenes          (per-call narrative unit, ASR-cleaned quotes)
p2_entities     mentions → bio_entities    (canonicalize aliases, detect roles)
p3_threads      entity → bio_threads       (per-entity narrative arc + connections)
p3b_behavioral  entity → bio_behavior      (deterministic trust_score, volatility, dependency — no LLM)
p4_arcs         windows → bio_arcs         (multi-scene problem/project/relationship arcs)
p5_portraits    entity → bio_portraits     (literary character sketch + psych profile injection)
p6_chapters     month → bio_chapters       (thematic prose 2500-4500 words)
p8_editorial    chapter → bio_chapters     (polish pass, status=final)
p8b_doc_dedup   chapters → bio_chapters    (cross-chapter text dedup — no LLM)
p7_book         all → bio_books            (frame: title, prologue, TOC, epilogue → stitched markdown)
p9_yearly       year → bio_books           (Dovlatov-style annual retrospective)
```

## Psychology layer

`psychology_profiler.py` runs on Knowledge Graph data (entities, entity_metrics, events, relations):

- **Temperament**: Hippocrates-Galen — choleric / sanguine / phlegmatic / melancholic
  (from call frequency × emotional tone variance)
- **Big Five (OCEAN)**: Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism
  (from entity_metrics ratios — promises, contradictions, blame-shifts, emotional spikes)
- **Motivation (McClelland)**: achievement / power / affiliation / security
  (from promise chains, conflict counts, centrality)
- **Network position**: centrality, density, bridge score, top connections
  (from relations table)

These profiles are injected into p5_portraits and p9_yearly prompts.

## Adaptive token budget

`TokenBudget` class in `prompts.py` replaces all hard `[:NNNN]` caps:

```
p6_chapters: 17 000 chars JSON budget, portraits 50% / arcs 25% / scenes 25%
p9_yearly:   9 500 chars, chapters 50% / arcs 30% / entities 20%
...etc for all 9 passes
```

Sections compete proportionally; unused budget is redistributed.

## Resume / checkpoint system

- `bio_checkpoints` — per-pass state (total/processed/failed/status)
- `bio_checkpoint_items` — per-item tracking (fast skip without DB re-query)
- `start_checkpoint()` keeps counters when status=running (resume); resets when status=done
- `tick_checkpoint()` auto-saves completed items
- Each pass loads `done_ids` at start and skips already-processed items

## Cross-chapter narrative continuity

- p6_chapters passes `prev_chapter_context` (last 200 words + theme of previous chapter)
- p6_chapters passes `yearly_context` on year transitions
- `entity_network` computed from co-occurring entities in month scenes

## Per-pass prompt versioning

`PASS_VERSIONS` dict in `prompts.py` (11 entries, e.g. `p6-v3`).
Bump individual pass version to invalidate only that pass's memoization.

## Context budget (Qwen3.5, 16 384 tokens)

| Pass | Output reserve | Input cap | Notes |
|------|---------------|-----------|-------|
| p1   | 1800          | 12000 ch  | transcript clip (6K head + 6K tail) |
| p2   | 3800          | 10000 ch  | mention list |
| p3   | 2500          | 12000 ch  | scene JSON |
| p4   | 4200          | 14000 ch  | scene chronology |
| p5   | 2500          | 12000 ch  | scene + psych profile |
| p6   | 5500          | 17000 ch  | portraits(50%)+arcs(25%)+scenes(25%) |
| p7   | 3500          | 9000 ch   | chapters+arcs+entities |
| p8   | 5500          | 32000 ch  | chapter prose (was 20000) |
| p9   | 4000          | 9500 ch   | chapters+arcs+entities+psychology |

## Owner identity

- Owner = Сергей Медведев (user_id=serhio)
- In transcripts: always `[me]` / `OWNER`
- In prose: third person, full name Сергей Медведев
- Cannot talk to himself — Сергей Медведев ≠ any other Сергей in the data

## See also

- `prompts.py` — all prompt templates + TokenBudget + BUDGETS + PASS_VERSIONS
- `psychology_profiler.py` — temperament, Big Five, motivation, network classifiers
- `orchestrator.py` — top-level runner (run_all / run_passes / status)
- `.claude/rules/biography-style.md` — tone, length, prohibitions
- `.claude/rules/graph.md` — Knowledge Graph rules (separate from biography)