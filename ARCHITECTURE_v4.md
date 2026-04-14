# CallProfiler — Архитектура v4

## Изменения относительно v3

- Добавлена классификация звонков (call_type)
- Добавлена таблица contact_summaries (materialized aggregate)
- Структурированный формат карточки overlay
- Hook-фраза в промпте LLM
- Глобальный risk_score по контакту
- Отвергнуты: Event Store, NeMo, LLM Role Correction, USB-буфер

---

## Pipeline (обновлённый)

```
[Аудиофайл / .txt файл]
    │
    ▼
[1. Ingest] → parse filename, MD5, contact, call record
    │
    ▼
[2. Normalize] → ffmpeg WAV 16kHz mono (только для аудио)
    │
    ▼
[3. Transcribe] → faster-whisper large-v3 (GPU)
    │
    ▼
[4. Diarize] → pyannote + ref embedding → OWNER/OTHER
    │
    ▼
[5. Classify] → NEW: определить call_type
    │           short (<50 символов) → skip LLM, автозаполнение
    │           остальные → продолжить
    │
    ▼
[6. LLM Analyze] → llama-server Qwen3.5-9B
    │               Выход: summary, priority, risk, bs_score,
    │               action_items, promises, hook, call_type,
    │               contact_name_guess, people, companies, amounts
    │
    ▼
[7. Aggregate] → NEW: пересчитать contact_summary
    │             global_risk, open_promises, hook, advice
    │
    ▼
[8. Generate Card] → CallNotes/{phone}.txt (≤512 байт)
    │                 Структурированный формат
    │
    ▼
[9. Deliver] → Telegram + FolderSync → телефон
```

## Классификация звонков (шаг 5)

**До LLM (по длине текста):**
```
< 50 символов → call_type = 'short', пропустить LLM
< 200 символов → подать в LLM с пометкой "короткий звонок"
≥ 200 символов → полный анализ
```

**LLM определяет (в JSON ответе):**
```
call_type: business | personal | smalltalk | spam | unknown
```

**Влияние на агрегаты:**
```
business  → вес 1.0 в contact_summary
personal  → вес 0.7
smalltalk → вес 0.1 (только personal_facts)
short     → вес 0.0 (не влияет)
spam      → вес 0.0
```

## contact_summary (materialized aggregate)

Пересчитывается после каждого обработанного звонка.

```
Алгоритм пересчёта contact_summary(contact_id):

1. Выбрать все analyses для этого контакта
2. Отфильтровать: исключить short и spam
3. global_risk = weighted_avg(risk_score, weight=call_type_weight)
   с decay: свежие звонки важнее старых (half-life = 90 дней)
4. avg_bs_score = weighted_avg(bs_score) аналогично
5. open_promises = все promises где status='open'
6. open_debts = promises с суммами (amounts не пустой)
7. personal_facts = key_topics из smalltalk звонков (последние 5)
8. top_hook = hook из последнего business-звонка
   Если нет business → hook из последнего personal
   Если нет ничего → "Нет значимой истории"
9. advice = генерируется по правилам:
   - risk > 70 → "Говори первым. Фиксируй договорённости."
   - bs_score > 60 → "Осторожно: частые размытые обещания."
   - open_debts не пуст → "Начни с долга."
   - иначе → "Нейтральный контакт."
10. contact_role = contact_company_guess из последнего analysis
11. Записать в contact_summaries
```

## Формат карточки overlay

```
header: {display_name или guessed_name} — {contact_role}
risk: {global_risk} {🔴|🟡|🟢}
hook: {top_hook}
bullet1: {open_debts[0] или open_promises[0]}
bullet2: {contradictions или следующий promise}
bullet3: {personal_facts[0] или пусто}
advice: {advice}
```

Правила цвета risk:
- 🔴 risk ≥ 70
- 🟡 30 ≤ risk < 70
- 🟢 risk < 30

Если контакт новый (0 звонков с анализом):
```
header: Неизвестный ({phone}) — новый
risk: — ⚪
hook: Первый звонок. Нет истории.
advice: Слушай внимательно.
```

## Обновлённый промпт LLM

Добавлены поля к текущему промпту:

```json
{
  "call_type": "business|personal|smalltalk|spam",
  "hook": "одна фраза-напоминание для следующего звонка",
  "contradictions": ["противоречия с предыдущими звонками"],
  "debts": [{"who": "Me|S2", "amount": "сумма", "deadline": "дата"}]
}
```

## Модуль summary_builder.py

```
src/callprofiler/aggregate/
├── __init__.py
└── summary_builder.py

class SummaryBuilder:
    def __init__(self, repo: Repository)
    
    def rebuild_contact(self, contact_id: int) → None
        """Пересчитать contact_summary для одного контакта"""
    
    def rebuild_all(self, user_id: str) → None
        """Пересчитать все contact_summaries для пользователя"""
    
    def generate_card(self, contact_id: int) → str
        """Сгенерировать текст карточки из contact_summary"""
    
    def write_card(self, contact_id: int, sync_dir: str) → None
        """Записать {phone}.txt"""
    
    def write_all_cards(self, user_id: str) → None
        """Пересоздать все карточки"""
```

CLI:
```
python -m callprofiler rebuild-summaries --user serhio
python -m callprofiler rebuild-cards --user serhio
```

## Что НЕ меняется

- Весь текущий pipeline (ingest, normalize, transcribe, diarize)
- SQLite как единственная БД
- pyannote + ref embedding для диаризации
- llama-server (не Ollama) на http://127.0.0.1:8080
- Мультипользовательская модель с user_id
- FolderSync для синхронизации (без USB-буфера)
- MacroDroid для overlay

## Условия пересмотра

| Замер | Триггер | Действие |
|-------|---------|----------|
| Ошибка ролей | > 15% на 100 звонках | LLM Role Correction |
| pyannote DER | > 25% | Попробовать NeMo |
| FTS5 скорость | > 2 сек на запрос | Векторный поиск |
| Контакты с N номерами | > 5% контактов | Zero False Merge |
| JSON parse failures | > 10% | Упростить промпт |
| SQLite locks | Измеримые задержки | PostgreSQL |
