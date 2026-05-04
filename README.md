# CallProfiler

**Локальная система обработки телефонных звонков в реальном времени** с автоматическим распознаванием речи, идентификацией говорящего и отправкой резюме в Telegram.

> 📱 Запись → 🤖 Обработка (локально) → 💬 Дайджест → 📲 Telegram + Android overlay

---

## 🎯 Назначение

CallProfiler обрабатывает звонки, полученные на локальной машине Windows, и:

1. **Распознаёт речь** (Whisper + faster-whisper) в текст с временными метками
2. **Идентифицирует говорящих** (pyannote.audio 3.3.2) с разделением по `user_id`
3. **Нормализует аудио** (EBU R128) перед обработкой
4. **Сохраняет данные** в SQLite с полнотекстовым поиском (FTS5)
5. **Генерирует дайджесты** и отправляет в Telegram
6. **Синхронизирует оверлей** на Android (через FolderSync + MacroDroid)

Результат: **структурированный архив звонков с быстрым поиском и мобильным доступом**.

---

## ⚙️ Системные требования

| Параметр | Значение |
|----------|----------|
| **ОС** | Windows 10/11 |
| **GPU** | RTX 3060 12GB (или совместимый CUDA-чип) |
| **CUDA** | 12.4+ |
| **PyTorch** | 2.6.0+cu124 |
| **Python** | 3.10+ |
| **Свободное место** | ≥50 GB (модели + архив) |

### Модели (автозагрузка)

- **Whisper**: ~3 GB (faster-whisper)
- **pyannote.audio**: ~1.5 GB (speaker diarization)
- **Ollama Qwen 14B Q4**: ~10 GB (опционально, для обобщений)

---

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/SergioTheFirst/callprofiler.git
cd callprofiler
```

### 2. Зависимости

```bash
pip install --break-system-packages \
    torch==2.6.0+cu124 \
    torchaudio \
    faster-whisper \
    pyannote.audio==3.3.2 \
    torch-audiomentations \
    librosa \
    numpy \
    requests \
    python-telegram-bot
```

### 3. Авторизация pyannote

pyannote требует `use_auth_token` (не `token`):

```python
from pyannote.audio import Pipeline
pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token="YOUR_HUGGINGFACE_TOKEN"  # ← важно!
)
```

Получить токен: https://huggingface.co/settings/tokens

### 4. Переменные окружения

```bash
# .env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
LLM_SERVER_URL=http://127.0.0.1:8080  # Опционально (llama-server)
```

---

## 📋 Архитектура

```
callprofiler/
├── src/
│   ├── audio_processor.py       # Нормализация (EBU R128), сегментация
│   ├── speech_recognizer.py     # Whisper + временные метки
│   ├── speaker_diarizer.py      # pyannote.audio, идентификация
│   ├── database.py              # SQLite + FTS5, multi-user isolation
│   ├── telegram_notifier.py     # Отправка дайджестов
│   └── llm_adapter.py           # OpenAI-совместимый LLM (Ollama/llama-server)
├── config/
│   ├── config.json              # Параметры: device, batch_size, output_paths
│   └── users.json               # Маппинг speaker_id → user_id
├── models/
│   ├── whisper-model            # Кэш Whisper
│   └── pyannote-checkpoint      # Кэш pyannote
├── archive/
│   └── calls_db.sqlite          # База звонков (FTS5)
├── documents/
│   ├── STRATEGIC_PLAN_v3.md     # Долгосрочное видение
│   ├── ARCHITECTURE_v3.md       # Технический дизайн
│   ├── DEVELOPMENT_PLAN.md      # 15-step implementation plan
│   ├── CONSTITUTION.md          # 18-article merge-blocking rules
│   └── AGENTS.md                # AI-агенты для обработки
└── tests/
    └── test_pipeline.py         # Smoke tests (18/18 passing)
```

---

## 🔧 Использование

### 📊 Real-time Web Dashboard

Веб-интерфейс для мониторинга pipeline в реальном времени:

```bash
# Запуск dashboard через CLI
python -m callprofiler dashboard --user serhio --port 8765 --host 127.0.0.1
```

**Быстрый запуск через .bat файлы:**

- `start-dashboard.bat` — запускает сервер (Ctrl+C для остановки)
- `open-dashboard.bat` — запускает сервер + автоматически открывает браузер

**Возможности:**
- Real-time обновления через SSE (Server-Sent Events)
- Список всех звонков с фильтрацией и сортировкой
- Детали звонка: транскрипт, анализ, события, обещания
- Профили контактов: риск-скор, психология, история взаимодействий
- Темная тема с премиум-дизайном
- Read-only доступ к БД (не блокирует pipeline)
- Graceful degradation: fallback на polling при проблемах с SSE

**Технологии:**
- Backend: FastAPI + Uvicorn (async)
- Frontend: Vanilla JS + EventSource API
- Database: SQLite read-only mode (`file:path?mode=ro`)
- Change detection: polling MAX(updated_at) каждые 2 секунды

### Базовый pipeline

```python
from src.audio_processor import AudioProcessor
from src.speech_recognizer import SpeechRecognizer
from src.speaker_diarizer import SpeakerDiarizer
from src.database import CallDatabase

# 1. Загрузить аудио
audio_processor = AudioProcessor()
normalized_audio = audio_processor.normalize_ebu_r128("path/to/call.wav")

# 2. Распознать речь
recognizer = SpeechRecognizer()
transcript = recognizer.transcribe(normalized_audio)  
# → [{'start': 0.5, 'end': 3.2, 'text': 'Привет', 'speaker': 'speaker_0'}, ...]

# 3. Идентифицировать говорящих
diarizer = SpeakerDiarizer()
speakers = diarizer.diarize(normalized_audio, transcript)
# → {'speaker_0': 'user_123', 'speaker_1': 'user_456'}

# 4. Сохранить в БД
db = CallDatabase("archive/calls_db.sqlite")
db.save_call(
    call_id="call_20250409_120000",
    user_id="user_123",
    transcript=transcript,
    speakers=speakers,
    audio_duration=125.5
)

# 5. Поиск
results = db.full_text_search("важное слово", user_id="user_123")
```

### Отправка в Telegram

```python
from src.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier(token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)

digest = {
    "call_id": "call_20250409_120000",
    "duration": "2:05",
    "speakers": ["Иван", "Петя"],
    "summary": "Обсудили квартальный план",
    "key_points": ["Deadline 30 апреля", "Нужна презентация"]
}

notifier.send_digest(digest)
```

### LLM-адаптер (опционально)

Для обобщений используется **llama-server** (совместимо с OpenAI API):

```bash
# Запуск локального LLM (Qwen 3.5 9B)
llama-server.exe -m "C:\models\Qwen3.5-9B.Q5_K_M.gguf" \
  -ngl 99 -c 16384 --host 127.0.0.1 --port 8080
```

```python
from src.llm_adapter import LLMAdapter

llm = LLMAdapter(base_url="http://127.0.0.1:8080/v1")
summary = llm.summarize_transcript(transcript)
```

---

## 🗄️ База данных

### Схема SQLite

```sql
CREATE TABLE calls (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration REAL,
    transcript TEXT,
    speakers JSON,
    metadata JSON
);

CREATE VIRTUAL TABLE calls_fts USING fts5(
    id UNINDEXED,
    user_id UNINDEXED,
    transcript,
    content=calls,
    content_rowid=rowid
);
```

### Изоляция по user_id

Все запросы **обязательно** фильтруют по `user_id` — исключена утечка данных между пользователями:

```python
db.search("текст", user_id="user_123")  # ← Безопасно
db.search("текст")                       # ✗ Ошибка: user_id не указан
```

---

## 🚨 Критические особенности

### ⚠️ torch.load()

**Проблема**: pyannote требует `weights_only=False` при загрузке чекпоинтов.

```python
# Неправильно (вызывает ошибку):
checkpoint = torch.load("model.pt")

# Правильно:
checkpoint = torch.load("model.pt", weights_only=False)
```

### ⚠️ pyannote токен

**Проблема**: параметр `token=` устарел.

```python
# Неправильно:
Pipeline.from_pretrained(..., token="hf_...")

# Правильно:
Pipeline.from_pretrained(..., use_auth_token="hf_...")
```

### ⚠️ Выгрузка моделей перед LLM

Whisper (~3GB) + pyannote (~1.5GB) занимают GPU память. Перед запуском Ollama Qwen 14B (~10GB) нужна очистка:

```python
# После обработки звонка
del recognizer, diarizer
torch.cuda.empty_cache()

# Теперь безопасно запустить LLM
llm = LLMAdapter(...)
```

### ✅ --break-system-packages

На Windows 10/11 без venv нужен флаг:

```bash
pip install --break-system-packages torch faster-whisper pyannote.audio
```

---

## 📱 Мобильная интеграция

### Android overlay (MacroDroid + FolderSync)

1. **FolderSync** синхронизирует `archive/` → Android
2. **MacroDroid** читает `.txt` файлы (результаты) и показывает overlay при входящем звонке
3. CallProfiler пишет в `archive/pending_overlay/{caller_id}.txt`

```
archive/
├── calls_db.sqlite
├── transcripts/
│   ├── call_20250409_120000.json
│   └── call_20250409_120100.json
└── pending_overlay/
    ├── +71234567890.txt          ← Появляется перед звонком
    ├── +71234567891.txt
    └── ...
```

---

## 📊 Документация проекта

| Документ | Описание |
|----------|---------|
| **STRATEGIC_PLAN_v3.md** | Долгосрочное видение: масштабирование, новые источники, интеграции |
| **ARCHITECTURE_v3.md** | Полный технический дизайн: компоненты, потоки данных, обработка ошибок |
| **DEVELOPMENT_PLAN.md** | 15-шаговый план реализации (текущий статус: Step 5 завершён) |
| **CONSTITUTION.md** | 18 статей merge-blocking: качество кода, testing, документация |
| **AGENTS.md** | AI-агенты для автоматизации (анализ, категоризация, поиск паттернов) |

---

## ✅ Тестирование

### Smoke tests (18/18 passing)

```bash
python tests/test_pipeline.py
```

Покрытие:
- ✓ Нормализация аудио (EBU R128)
- ✓ Распознавание речи (Whisper)
- ✓ Дарваризация (pyannote)
- ✓ Сохранение в БД
- ✓ Поиск (FTS5)
- ✓ Отправка в Telegram
- ✓ LLM-адаптер

---

## 🔒 Безопасность

- ✓ Изоляция данных по `user_id` (multi-user safe)
- ✓ Локальная обработка (нет передачи в облако)
- ✓ Шифрование Telegram токена в `.env`
- ✓ HTTPS для HuggingFace API

---

## 📈 Производительность

| Операция | Время | GPU |
|----------|-------|-----|
| Нормализация 10 мин аудио | 5 сек | CPU |
| Распознавание (Whisper) | 2-3x реальное время | RTX 3060 |
| Дарваризация (pyannote) | 1-2x реальное время | RTX 3060 |
| LLM-обобщение | зависит от длины | Ollama Qwen |

---

## 🐛 Известные проблемы

| Проблема | Решение |
|----------|---------|
| `RuntimeError: Model not found` (pyannote) | Установить `use_auth_token` с валидным HF токеном |
| CUDA out of memory при 2+ параллельных звонках | Использовать `--break-system-packages`, выгружать модели после каждого звонка |
| Telegram сообщения не отправляются | Проверить `TELEGRAM_BOT_TOKEN`, интернет-соединение |
| FTS5 поиск очень медленный на >10k записях | Добавить индексы: `CREATE INDEX idx_user_id ON calls(user_id)` |

---

## 🤝 Контрибьютинг

Любые PR должны соответствовать **CONSTITUTION.md** (18 статей). Ключевые требования:

- [ ] Код покрыт тестами
- [ ] Документация актуальна
- [ ] Совместимость с Python 3.10+, PyTorch 2.6.0+
- [ ] Изоляция по `user_id` (multi-user safe)
- [ ] Нет нарушений CONSTITUTION.md

---

## 📄 Лицензия

MIT License. Используй свободно, но указывай авторство.

---

## 👤 Автор

**Sergio** (@SergioTheFirst)  
GitHub: https://github.com/SergioTheFirst  
CallProfiler Repository: https://github.com/SergioTheFirst/callprofiler

---

## 📚 Ссылки

- [PyTorch + CUDA Setup](https://pytorch.org/get-started/locally/)
- [faster-whisper docs](https://github.com/guillaumekln/faster-whisper)
- [pyannote.audio](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [llama.cpp server](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md)

---

**Последнее обновление**: Апрель 2026  
**Статус**: Production Ready (Phase 1 complete, Step 5/15)
