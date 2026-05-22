# CallProfiler

**Локальная мультипользовательская система пост-обработки записей телефонных разговоров** с транскрибацией, диаризацией, LLM-анализом, графом знаний, психологическим профилированием и биографическим конвейером.

> 🎙️ Аудиофайл → normalize → whisper → pyannote → LLM → SQLite → Telegram / caller card

---

## 🎯 Возможности

CallProfiler обрабатывает аудиозаписи звонков на локальной машине Windows и:

1. **Нормализует аудио** (ffmpeg + EBU R128 LUFS) перед обработкой
2. **Транскрибирует речь** (faster-whisper large-v3) с временны́ми метками
3. **Диаризирует спикеров** (pyannote.audio 3.3.2 + reference embedding) — свой/чужой
4. **Анализирует разговор** через локальный LLM (llama.cpp, Qwen 3.5 9B) — риски, обещания, долги, факты, smalltalk
5. **Строит граф знаний** с BS-калибровкой, объединением сущностей и health gate
6. **Профилирует психологию** контактов (темперамент, Big Five OCEAN, мотивация McClelland)
7. **Генерирует биографические книги** (11-pass LLM конвейер по транскриптам)
8. **Доставляет результаты** в Telegram-бот и через caller cards (.txt) для Android-оверлея
9. **Веб-дашборд** — FastAPI + SSE + тёмная тема, мониторинг в реальном времени

---

## ⚙️ Системные требования

| Параметр | Значение |
|----------|----------|
| **ОС** | Windows 10/11 |
| **GPU** | RTX 3060 12GB |
| **CUDA** | 12.4+ |
| **PyTorch** | 2.6.0+cu124 |
| **Python** | 3.10+ (системный, без venv) |
| **Свободное место** | ≥50 GB |

### Модели (автозагрузка)

| Модель | VRAM | Библиотека |
|--------|------|------------|
| Whisper large-v3 | ~3 GB | faster-whisper |
| pyannote 3.1 | ~1.5 GB | pyannote.audio 3.3.2 |
| Qwen 3.5 9B Q8_0 | ~10 GB | llama.cpp server |

---

## 🚀 Установка

### 1. Клонирование

```bash
git clone https://github.com/SergioTheFirst/callprofiler.git
cd callprofiler
```

### 2. Установка пакета

```bash
pip install -e . --break-system-packages
```

### 3. Переменные окружения

```bash
# configs/base.yaml — основной конфиг (data_dir, модели, ffmpeg, HF_TOKEN)
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl
```

### 4. Обязательные хаки (CONSTITUTION Статья 13.1)

```python
# torch.load monkey-patch (src/callprofiler/__init__.py)
checkpoint = torch.load("model.pt", weights_only=False)

# pyannote 3.3.2: use_auth_token= (не token=)
Pipeline.from_pretrained(..., use_auth_token="hf_...")
```

---

## 📋 Архитектура

```
callprofiler/
├── AGENTS.md, CLAUDE.md, CONSTITUTION.md, CHANGELOG.md, CONTINUITY.md
├── configs/
│   ├── base.yaml
│   └── prompts/
│       ├── analyze_v001.txt          # Системный промпт LLM
│       └── psychology_profile.txt    # Промпт психопрофилирования
├── src/callprofiler/
│   ├── config.py                     # Dataclass Config + load_config()
│   ├── models.py                     # CallMetadata, Segment, Analysis
│   ├── audio/normalizer.py           # ffmpeg + EBU R128 LUFS
│   ├── transcribe/whisper_runner.py  # faster-whisper large-v3
│   ├── diarize/
│   │   ├── pyannote_runner.py        # pyannote 3.3.2 + ref embedding
│   │   └── role_assigner.py          # overlap-mapping → спикер
│   ├── analyze/
│   │   ├── llm_client.py             # HTTP клиент llama.cpp (OpenAI API)
│   │   ├── prompt_builder.py         # Подстановка в analyze_vNNN.txt
│   │   ├── response_parser.py        # 4-уровневый robust JSON parser
│   │   ├── prompt_budget.py          # Бюджетирование токенов
│   │   └── service.py                # Сервисный слой анализа
│   ├── db/
│   │   ├── schema.sql                # CREATE TABLE IF NOT EXISTS
│   │   └── repository.py             # sqlite3 + FTS5 (без ORM)
│   ├── ingest/
│   │   ├── filename_parser.py        # 5 форматов имён Android-диктофонов
│   │   └── ingester.py               # MD5 дедупликация + регистрация
│   ├── aggregate/summary_builder.py  # Построение сводок
│   ├── bulk/
│   │   ├── enricher.py               # Массовый LLM-анализ
│   │   ├── loader.py                 # Импорт готовых транскриптов
│   │   └── name_extractor.py         # Извлечение имён из транскриптов
│   ├── deliver/
│   │   ├── card_generator.py         # Caller cards ({phone}.txt)
│   │   └── telegram_bot.py           # Telegram-бот
│   ├── pipeline/
│   │   ├── orchestrator.py           # Главный pipeline
│   │   └── watcher.py                # Сканирование incoming_dir
│   ├── graph/
│   │   ├── builder.py, aggregator.py # Построение и агрегация графа
│   │   ├── calibration.py            # BS-калибровка
│   │   ├── resolver.py, llm_disambiguator.py  # Разрешение сущностей
│   │   ├── auditor.py, validator.py  # Аудит и валидация
│   │   ├── replay.py, repository.py  # Перестроение и хранение
│   ├── biography/                    # 11-pass LLM конвейер
│   │   ├── p1-p9/                    # Шаги 1-9
│   │   ├── psychology_profiler.py    # Психопрофиль
│   │   ├── orchestrator.py, repo.py  # Оркестратор и хранилище
│   │   └── prompts/                  # Промпты для каждого шага
│   ├── dashboard/
│   │   ├── server.py                 # FastAPI + SSE
│   │   ├── db_reader.py, models.py   # Чтение БД
│   │   ├── templates/index.html      # SPA интерфейс
│   │   └── static/                   # CSS/JS ассеты
│   ├── quality/extraction_eval.py    # Оценка качества извлечения
│   ├── cli/
│   │   ├── main.py                   # Точка входа (567 строк)
│   │   ├── commands/                 # admin, bulk, query, graph, biography, contacts
│   │   └── utils.py
│   └── events.py                     # Модель событий
├── tests/                            # 302 теста (pytest)
├── .claude/skills/                   # filename-parser, journal-keeper
└── memory/                           # roadmap, business, decisions, bugs
```

---

## 🔧 CLI (33 команды)

```bash
# Основной режим работы
python -m callprofiler watch                     # Watchdog: автообработка incoming_dir
python -m callprofiler process <файл> --user U  # Разовый процессинг
python -m callprofiler reprocess                # Переобработка
python -m callprofiler add-user                 # Добавить пользователя
python -m callprofiler status                   # Статус системы
python -m callprofiler dashboard                # Веб-дашборд (FastAPI)
python -m callprofiler bot                      # Telegram-бот

# Поиск и отчёты
python -m callprofiler digest U --days 7        # Дайджест за неделю
python -m callprofiler search "запрос" --user U # FTS5 полнотекстовый поиск
python -m callprofiler promises --user U        # Список обещаний
python -m callprofiler analytics --user U       # Аналитика
python -m callprofiler inspect-schema           # Схема БД

# Массовые операции
python -m callprofiler bulk-load <директория> --user U
python -m callprofiler bulk-enrich --user U [--limit N]
python -m callprofiler extract-names --user U [--dry-run]

# Перестроение
python -m callprofiler rebuild-summaries
python -m callprofiler rebuild-cards
python -m callprofiler backfill-events
python -m callprofiler backfill-calltypes

# Граф знаний
python -m callprofiler graph-backfill
python -m callprofiler graph-replay
python -m callprofiler graph-stats
python -m callprofiler graph-audit
python -m callprofiler graph-health

# Сущности
python -m callprofiler entity-merge
python -m callprofiler entity-unmerge
python -m callprofiler reenrich-v2

# Биография
python -m callprofiler biography-run
python -m callprofiler biography-status
python -m callprofiler biography-export
python -m callprofiler book-chapter
python -m callprofiler person-profile
python -m callprofiler profile-all
```

---

## 🗄️ Модель данных

```
users → contacts → calls → transcripts (FTS5 indexed)
                       → analyses (LLM results)
                       → promises (open/closed tracking)
                       → events (promise/debt/risk/fact/smalltalk)

entities → relations → entity_metrics → bs_thresholds

bio_books, bio_portraits, bio_scenes, bio_chapters (biography)
```

**Приоритет имён контактов:**
```
МАКСИМАЛЬНЫЙ: display_name (из имени файла = телефонная книга Android)
ВТОРИЧНЫЙ:    guessed_name (автоизвлечение из транскрипта)
```

Все SQL-запросы к `contacts/calls/analyses/promises` — строго с `WHERE user_id = ?`.

---

## ⚡ Pipeline

```
аудиофайл → normalize (EBU R128, ffmpeg) → transcribe (faster-whisper large-v3)
→ diarize (pyannote 3.3.2 + ref embedding) → assign roles (OWNER|OTHER)
→ analyze (llama.cpp Qwen 3.5 9B Q8_0) → deliver (Telegram + caller cards)
```

**GPU-дисциплина**: Whisper + pyannote загружаются вместе, выгружаются перед LLM-запросом. Три модели одновременно в VRAM не держатся.

---

## 💻 Веб-дашборд

```bash
python -m callprofiler dashboard --user serhio --port 8765
```

- Real-time обновления через SSE (Server-Sent Events)
- Список всех звонков с фильтрацией и сортировкой
- Детали звонка: транскрипт, анализ, события, обещания
- Профили контактов: риск-скор, психология, история
- Тёмная тема, адаптивный дизайн
- Read-only доступ к БД (не блокирует pipeline)

---

## 📱 Android-интеграция

1. **FolderSync** синхронизирует caller cards (.txt) на телефон
2. **MacroDroid** читает файл и показывает оверлей при входящем звонке
3. CallProfiler генерирует `{phone}.txt` в sync-директории пользователя

---

## ✅ Тестирование

```bash
pytest tests/ -v          # 302/302 passing
python -m compileall src/ # OK
```

Покрытие: все модули от `filename_parser` до `biography`, включая граф знаний, психопрофили и веб-дашборд.

---

## 📊 Производительность

| Операция | Время | Устройство |
|----------|-------|-----------|
| Нормализация (10 мин аудио) | ~5 сек | CPU |
| Транскрибация (faster-whisper) | 2-3x real-time | RTX 3060 |
| Диаризация (pyannote) | 1-2x real-time | RTX 3060 |
| LLM-анализ (llama.cpp) | зависит от длины | RTX 3060 / CPU |

---

## 🔒 Безопасность

- Локальная обработка — никаких облаков, Docker, Redis, PostgreSQL
- Изоляция данных по `user_id` во всех запросах
- MD5-дедупликация аудиофайлов
- Оригиналы аудио неприкосновенны

---

## 🐛 Известные особенности

| Ситуация | Решение |
|----------|---------|
| `RuntimeError: Model not found` (pyannote) | Проверить `HF_TOKEN` и `use_auth_token=` |
| CUDA out of memory | Выгружать Whisper+pyannote перед LLM |
| Telegram не отправляет | Проверить `TELEGRAM_BOT_TOKEN` |
| FTS5 поиск медленный на больших объёмах | Штатная работа SQLite FTS5 |

---

## 📚 Документация

| Документ | Описание |
|----------|---------|
| **CONSTITUTION.md** | 18 статей merge-blocking правил |
| **AGENTS.md** | Руководство для AI-агентов |
| **CLAUDE.md** | Исходный 15-шаговый план разработки |
| **CHANGELOG.md** | Журнал всех изменений |
| **CONTINUITY.md** | Текущее состояние и незавершённые задачи |
| **memory/** | Рабочая память: roadmap, решения, баги |

---

## 📄 Лицензия

MIT License.

---

**Автор**: Sergio (@SergioTheFirst)  
**Репозиторий**: https://github.com/SergioTheFirst/callprofiler  
**Последнее обновление**: Май 2026  
**Статус**: Production Ready — все 15+ шагов завершены, 302 теста проходят
