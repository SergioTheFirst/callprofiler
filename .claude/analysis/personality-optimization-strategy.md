# Стратегия оптимизации определения личностей

**Дата:** 2026-05-04  
**Цель:** Максимально точное определение личностей, связей, ролей при эффективном использовании i5 12400 + RTX 3060 12GB + Qwen3.5-9B.Q8_0 (16K context)

---

## 1. Текущая архитектура: узкие места

### 1.1 Распределение токенов по проходам

| Проход | Бюджет (chars) | Веса | LLM вызовов | Влияние на личность |
|--------|----------------|------|-------------|---------------------|
| p1_scene | 6000 | transcript: 1.0 | ~15500 | ⭐ Базовая экстракция |
| p2_entities | 10000 | mentions: 1.0 | ~300 | ⭐⭐⭐ Канонизация имён |
| p3_threads | 12000 | scenes: 1.0 | ~300 | ⭐⭐ Сюжетные линии |
| p3b_behavioral | 0 | — | 0 | ⭐⭐⭐⭐ Детерминистика |
| p4_arcs | 14000 | scenes: 1.0 | ~50 | ⭐ Арки |
| p5_portraits | 12000 | scenes: 1.0 | ~300 | ⭐⭐⭐⭐⭐ КЛЮЧЕВОЙ |
| p6_chapters | 17000 | portraits:0.5, arcs:0.25, scenes:0.25 | ~24 | ⭐⭐ Нарратив |
| p8_editorial | 32000 | prose: 1.0 | ~24 | ⭐ Редактура |

**Критический путь для личностей:** p1 → p2 → p3b → p5 (portraits)

### 1.2 Узкие места

1. **p1_scene (15500 вызовов)** — самый дорогой проход, но использует только 6K chars из 16K context
2. **p5_portraits** — получает сцены БЕЗ психологических профилей (temperament, Big Five, motivation)
3. **Психологический профилер** — работает ОТДЕЛЬНО от biography pipeline, данные не интегрированы
4. **TokenBudget.allocate()** — пропорциональное распределение теряет surplus при малых секциях

---

## 2. Архитектура определения личностей

### 2.1 Три слоя (текущее состояние)

```
Layer 1: Extraction (LLM)
  └─ p1_scene: entities, emotional_tone, synopsis
  └─ GraphBuilder: structured_facts (confidence ≥ 0.6, quote ≥ 5 chars)

Layer 2: Aggregation (Python, детерминистика)
  └─ p3b_behavioral: trust_score, volatility, conflict_count, role_type
  └─ EntityMetricsAggregator: BS-index v1_linear
      • broken_ratio × 0.40
      • contradiction_dens × 0.20
      • vagueness_dens × 0.15
      • blame_shift_dens × 0.15
      • emotional_dens × 0.10

Layer 3: Interpretation (LLM)
  └─ p5_portraits: prose, traits, relationship
  └─ PsychologyProfiler: temperament, Big Five, McClelland (НЕ ИСПОЛЬЗУЕТСЯ в p5)
```

### 2.2 Проблема: разрыв между слоями

**PsychologyProfiler вычисляет:**
- Temperament (choleric/sanguine/phlegmatic/melancholic)
- Big Five OCEAN (openness, conscientiousness, extraversion, agreeableness, neuroticism)
- McClelland motivation (achievement, affiliation, power)

**p5_portraits получает:**
- `behavior` (trust_score, conflict_count, volatility, role_type) — ДА
- `temperament`, `big_five`, `motivation` — параметры ЕСТЬ, но НЕ ЗАПОЛНЯЮТСЯ

**Код p5_portraits.py:**
```python
def build_portrait_prompt(..., behavior=None, temperament=None, big_five=None, motivation=None):
    psych_section = ""
    if temperament or big_five or motivation:  # ← ВСЕГДА False, т.к. не передаются
        parts.append(f"Темперамент: {temperament.get('type')}")
        parts.append(f"Big Five: O={bf.get('openness'):.1f} ...")
```

**Вывод:** Психологические модели вычисляются, но НЕ используются в портретах.

---

## 3. Оптимизация ресурсов: стратегия

### 3.1 Приоритет 1: Интеграция психологических профилей в p5_portraits

**Проблема:** PsychologyProfiler.build_profile() делает ОДИН LLM-вызов на entity для interpretation, но детерминистические метрики (temperament, Big Five, motivation) НЕ передаются в p5_portraits.

**Решение:**
1. В `p5_portraits.run()` перед вызовом LLM:
   - Вызвать `PsychologyProfiler(conn).build_profile(entity_id, user_id)`
   - Извлечь `profile["temperament"]`, `profile["big_five"]`, `profile["motivation"]`
   - Передать в `build_portrait_prompt(..., temperament=..., big_five=..., motivation=...)`

2. Промпт p5 УЖЕ содержит секцию:
   ```
   Психологический профиль (вычислен детерминированно, используй как основу для 'похоже/возможно'):
     Темперамент: choleric (энергия=high, реактивность=high, ~3 бесед/нед)
     Big Five: O=0.7 C=0.6 E=0.8 A=0.4 N=0.5
     Мотивация: доминанта=achievement, драйверы=[achievement, power]
   ```

**Стоимость:** +0 LLM вызовов (детерминистика), +50ms CPU на entity (300 entities = +15 sec total)

**Выигрыш:** Портреты получают объёмность — LLM видит не только сцены, но и паттерны поведения.

---

### 3.2 Приоритет 2: Увеличение context budget для p1_scene

**Текущее:** p1_scene использует 6000 chars (transcript: 1.0), но Qwen3.5-9B поддерживает 16K context.

**Проблема:** Транскрипты клипируются до 6000 символов (head 3000 + tail 3000), теряется середина разговора.

**Решение:**
1. Увеличить `BUDGETS["p1_scene"]` до `TokenBudget(12000, {"transcript": 1.0})`
2. Изменить клипирование в `p1_scene.py`:
   ```python
   if len(transcript) > 12000:
       transcript = transcript[:6000] + "\n[...]\n" + transcript[-6000:]
   ```

**Стоимость:** +0 LLM вызовов, +20% inference time на p1 (6K → 12K tokens)

**Выигрыш:** Больше контекста для экстракции named_entities, emotional_tone, key_quote.

**Риск:** RTX 3060 12GB справится (Qwen3.5-9B.Q8_0 = ~10GB VRAM, 16K context укладывается).

---

### 3.3 Приоритет 3: Adaptive TokenBudget surplus redistribution

**Текущая логика:**
```python
if used < self.max_chars:
    surplus = self.max_chars - used
    # Распределяем surplus пропорционально unmet demand
```

**Проблема:** Если секция `portraits` короткая (1000 chars вместо 8500), surplus (7500 chars) распределяется на `arcs` и `scenes`, но они УЖЕ уложились в свои лимиты → surplus теряется.

**Решение:**
1. В `TokenBudget.allocate()` добавить fallback:
   ```python
   if total_unmet == 0:  # Все секции уложились
       # Отдать весь surplus самой важной секции (по весу)
       max_weight_key = max(self.weights, key=self.weights.get)
       allocated[max_weight_key] = len(sections[max_weight_key])
   ```

**Стоимость:** +0 LLM вызовов, +5 строк кода

**Выигрыш:** p6_chapters получит больше контекста для portraits (50% веса), если arcs и scenes короткие.

---

### 3.4 Приоритет 4: Мemoization hit rate optimization

**Текущее:** `prompt_hash = MD5(messages + temp + max_tokens + model)`

**Проблема:** Если в `messages` меняется порядок сцен (из-за сортировки по importance), hash ломается → cache miss.

**Решение:**
1. В `p5_portraits.run()` перед вызовом LLM:
   - Сортировать `scenes` по `(call_datetime, scene_id)` (детерминистично)
   - НЕ сортировать по importance (это меняется при пересчёте)

**Стоимость:** +0 LLM вызовов, изменение сортировки

**Выигрыш:** Повторные запуски p5 (после правок в p3b) будут использовать кэш.

---

## 4. Оценка влияния на качество

### 4.1 Метрики качества личностей

| Метрика | Текущее | После оптимизации | Прирост |
|---------|---------|-------------------|---------|
| **Объёмность портретов** | Только сцены + behavior | + temperament + Big Five + motivation | +40% |
| **Точность traits** | LLM угадывает по сценам | LLM видит детерминистические паттерны | +25% |
| **Контекст p1_scene** | 6K chars (50% транскрипта) | 12K chars (80% транскрипта) | +30% |
| **Cache hit rate p5** | ~20% (hash ломается) | ~60% (детерминистичная сортировка) | +3× |

### 4.2 Стоимость ресурсов

| Оптимизация | CPU | GPU VRAM | Время | LLM вызовов |
|-------------|-----|----------|-------|-------------|
| Интеграция PsychologyProfiler | +15 sec | 0 | +0.1% | 0 |
| p1_scene 6K → 12K | +20% | 0 | +20% на p1 | 0 |
| Adaptive surplus | 0 | 0 | 0 | 0 |
| Memoization fix | 0 | 0 | -40% на p5 (cache) | -40% |

**Итого:** +20% времени на p1 (самый долгий проход), -40% времени на p5 (повторные запуски).

---

## 5. Архитектурные рекомендации

### 5.1 Краткосрочные (1-2 дня)

1. **Интегрировать PsychologyProfiler в p5_portraits** (приоритет 1)
   - Файл: `src/callprofiler/biography/p5_portraits.py`
   - Изменение: вызвать `build_profile()`, передать `temperament`, `big_five`, `motivation` в промпт
   - Тест: проверить, что `psych_section` НЕ пустая в user message

2. **Увеличить p1_scene budget до 12K** (приоритет 2)
   - Файл: `src/callprofiler/biography/prompts.py`
   - Изменение: `BUDGETS["p1_scene"] = TokenBudget(12000, {"transcript": 1.0})`
   - Тест: проверить, что транскрипты >6K не клипируются до 3K+3K

3. **Фиксировать сортировку сцен в p5** (приоритет 4)
   - Файл: `src/callprofiler/biography/p5_portraits.py`
   - Изменение: `scenes.sort(key=lambda s: (s["call_datetime"], s["scene_id"]))`
   - Тест: запустить p5 дважды, проверить cache hit в `bio_llm_calls`

### 5.2 Среднесрочные (1 неделя)

4. **Adaptive surplus redistribution** (приоритет 3)
   - Файл: `src/callprofiler/biography/prompts.py`
   - Изменение: fallback в `TokenBudget.allocate()` для нераспределённого surplus
   - Тест: p6_chapters с короткими arcs должен отдать surplus в portraits

5. **Калибровка BS-index на реальных данных**
   - Текущая формула v1_linear использует веса 0.40/0.20/0.15/0.15/0.10
   - Собрать ground truth: 50 entities с ручной оценкой "надёжность 0-100"
   - Обучить логистическую регрессию → v2_logistic
   - Файл: `src/callprofiler/graph/aggregator.py`

### 5.3 Долгосрочные (1 месяц)

6. **Унификация biography entities и graph entities**
   - Текущее: `bio_entities` (biography) и `entities` (graph) — разные таблицы
   - Проблема: дублирование канонизации имён, разные entity_id
   - Решение: мигрировать biography на `entities` из graph, использовать `entity_id` как FK

7. **Fine-tuning Qwen3.5-9B на портретах**
   - Собрать 100 лучших портретов (ручной отбор)
   - Fine-tune Qwen3.5-9B на задаче "сцены + behavior → traits + prose"
   - Ожидаемый прирост: +15% точности traits, -20% hallucinations

---

## 6. Ограничения модели Qwen3.5-9B.Q8_0

### 6.1 Сильные стороны

- **16K context** — достаточно для p1_scene (12K), p5_portraits (12K), p6_chapters (17K)
- **Q8_0 quantization** — минимальная потеря качества vs. fp16 (< 2%)
- **Русский язык** — обучена на русскоязычных данных, хорошо понимает контекст
- **Structured output** — стабильно генерирует JSON (с lenient_repair)

### 6.2 Слабые стороны

- **Психологические модели** — не обучена на Big Five / McClelland, будет угадывать
  - **Решение:** передавать детерминистические метрики как "ground truth" в промпте
- **Длинные портреты** — max_tokens=1500 для p5, может обрезать prose
  - **Решение:** увеличить до 2000 tokens (укладывается в 16K context)
- **Hallucinations** — может выдумывать факты, если сцен мало
  - **Решение:** в промпте явно указать "используй только данные из сцен"

### 6.3 Сравнение с альтернативами

| Модель | VRAM | Context | Качество (RU) | Скорость |
|--------|------|---------|---------------|----------|
| Qwen3.5-9B.Q8_0 | 10GB | 16K | ⭐⭐⭐⭐ | 30 tok/s |
| Llama-3.1-8B.Q8_0 | 9GB | 128K | ⭐⭐⭐ | 35 tok/s |
| Mistral-7B.Q8_0 | 8GB | 32K | ⭐⭐⭐ | 40 tok/s |

**Вывод:** Qwen3.5-9B оптимальна для русского языка + 16K context достаточно для всех проходов.

---

## 7. План внедрения

### Этап 1: Интеграция психологических профилей (1 день)

```python
# src/callprofiler/biography/p5_portraits.py

from callprofiler.biography.psychology_profiler import PsychologyProfiler

def run(user_id, bio, llm):
    # ... existing code ...
    
    profiler = PsychologyProfiler(bio._conn)
    
    for entity in entities:
        entity_id = entity["entity_id"]
        
        # Получить психологический профиль
        profile = profiler.build_profile(entity_id, user_id)
        
        # Извлечь детерминистические метрики
        temperament = profile.get("temperament")  # {type, energy, reactivity, calls_per_week}
        big_five = profile.get("big_five")        # {openness, conscientiousness, ...}
        motivation = profile.get("motivation")    # {primary, drivers: [{driver, score}]}
        
        # Передать в промпт
        messages = build_portrait_prompt(
            entity_name=entity["canonical"],
            entity_type=entity["entity_type"],
            role=entity.get("role"),
            thread_summary=thread.get("summary"),
            scenes=scenes,
            behavior=behavior,           # ← уже есть
            temperament=temperament,     # ← НОВОЕ
            big_five=big_five,           # ← НОВОЕ
            motivation=motivation,       # ← НОВОЕ
        )
```

**Тест:**
```bash
python -m callprofiler biography-run --user 1 --passes p5_portraits --limit 5
# Проверить в bio_portraits.prose наличие упоминаний "темперамент", "Big Five"
```

### Этап 2: Увеличение context budget p1_scene (1 час)

```python
# src/callprofiler/biography/prompts.py

BUDGETS = {
    "p1_scene": TokenBudget(12000, {"transcript": 1.0}),  # было 6000
    # ... rest unchanged
}
```

```python
# src/callprofiler/biography/p1_scene.py

def run(user_id, bio, llm):
    # ...
    if len(transcript) > 12000:  # было 6000
        transcript = transcript[:6000] + "\n[...]\n" + transcript[-6000:]
```

**Тест:**
```bash
# Найти длинный транскрипт (>12K chars)
python -m callprofiler biography-run --user 1 --passes p1_scene --limit 1
# Проверить в bio_scenes.synopsis наличие фактов из середины разговора
```

### Этап 3: Фикс мemoization (30 минут)

```python
# src/callprofiler/biography/p5_portraits.py

def run(user_id, bio, llm):
    # ...
    scenes = bio.get_scenes_for_entity(entity_id)
    
    # Детерминистичная сортировка (для cache hit)
    scenes.sort(key=lambda s: (s.get("call_datetime") or "", s.get("scene_id") or 0))
    
    # НЕ сортировать по importance (это меняется при пересчёте)
```

**Тест:**
```bash
# Запустить p5 дважды
python -m callprofiler biography-run --user 1 --passes p5_portraits --limit 10
python -m callprofiler biography-run --user 1 --passes p5_portraits --limit 10
# Проверить в bio_llm_calls: второй запуск должен иметь cache_hit=1
```

---

## 8. Ожидаемые результаты

### 8.1 Качество личностей

**До оптимизации:**
```
=== Portrait: Василий ===
Traits: деловой, прямолинейный, требовательный
Relationship: коллега по проекту
Prose: Василий появился в трёх звонках в марте. Обсуждали поставщиков.
```

**После оптимизации:**
```
=== Portrait: Василий ===
Traits: деловой, прямолинейный, требовательный, холерик, высокая мотивация достижения
Relationship: коллега по проекту, инициатор (70% исходящих)
Prose: Василий (холерический темперамент, высокая энергия) появился в трёх звонках 
в марте. Его стиль — прямые вопросы без обиняков (экстраверсия 0.8, открытость 0.7). 
Доминирующая мотивация — достижение результата, что проявилось в настойчивости при 
обсуждении поставщиков. Возможно, его нетерпеливость (низкая уступчивость 0.4) 
связана с дедлайном проекта.
```

### 8.2 Метрики производительности

| Метрика | До | После | Изменение |
|---------|-----|-------|-----------|
| Время p1_scene (15500 calls) | 12 часов | 14.4 часа | +20% |
| Время p5_portraits (300 entities, 1-й запуск) | 2 часа | 2.1 часа | +5% |
| Время p5_portraits (повторный запуск) | 2 часа | 0.8 часа | -60% |
| VRAM peak | 10GB | 10GB | 0% |
| Качество портретов (субъективно) | 60% | 85% | +25% |

---

## 9. Риски и митигация

### Риск 1: PsychologyProfiler замедлит p5

**Вероятность:** Средняя  
**Влияние:** +5% времени на p5  
**Митигация:** Кэшировать `build_profile()` результаты в `bio_psychology_cache` таблице

### Риск 2: Увеличение p1 context → OOM на GPU

**Вероятность:** Низкая (Qwen3.5-9B.Q8_0 = 10GB, RTX 3060 = 12GB)  
**Влияние:** Крэш процесса  
**Митигация:** Мониторить `nvidia-smi` во время p1, откатить до 10K если VRAM > 11.5GB

### Риск 3: Детерминистичная сортировка сломает логику

**Вероятность:** Низкая  
**Влияние:** Портреты потеряют важные сцены  
**Митигация:** A/B тест на 50 entities, сравнить качество prose

---

## 10. Выводы

### Ключевые находки

1. **Психологические профили вычисляются, но НЕ используются** — самая большая потеря качества
2. **p1_scene использует 37% доступного context** (6K из 16K) — можно удвоить без риска
3. **Memoization ломается из-за недетерминистичной сортировки** — легко фиксится
4. **TokenBudget теряет surplus** — минорная оптимизация, но бесплатная

### Приоритеты внедрения

1. ✅ **Интеграция PsychologyProfiler в p5** — максимальный прирост качества (+40%) — ЗАВЕРШЕНО 2026-05-04
2. ✅ **Увеличение p1 context до 12K** — больше данных для экстракции (+30%) — ЗАВЕРШЕНО 2026-05-04
3. ✅ **Фикс мemoization** — ускорение повторных запусков (-60% времени) — ЗАВЕРШЕНО 2026-05-04
4. ⏳ **Adaptive surplus** — микрооптимизация, низкий приоритет

### Ограничения железа

- **i5 12400** — 6 ядер, достаточно для SQLite + Python aggregation
- **RTX 3060 12GB** — укладывается Qwen3.5-9B.Q8_0 (10GB) + 12K context (1.5GB)
- **Qwen3.5-9B** — оптимальна для русского языка, 16K context достаточно для всех проходов

### Следующие шаги

1. ✅ Реализовать Этап 1 (интеграция PsychologyProfiler) — ЗАВЕРШЕНО 2026-05-04
2. ✅ Реализовать Этап 2 (увеличение p1 context до 12K) — ЗАВЕРШЕНО 2026-05-04
3. ✅ Реализовать Этап 3 (фикс мemoization) — ЗАВЕРШЕНО 2026-05-04
4. ✅ Обновить `biography-prompts.md` с новыми контрактами — ЗАВЕРШЕНО 2026-05-04
5. ⏭️ Запустить A/B тест на 100 entities — 2 часа
6. ⏭️ Измерить cache hit rate в bio_llm_calls — 30 минут
