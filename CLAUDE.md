# CallProfiler — План разработки для Claude Code

## Контекст

- Рабочая машина: Windows 11, Python системный (без venv), cmd
- Путь проекта: `C:\pro\callprofiler\`
- Работающий прототип: `C:\pro\mbot\batch_asr.py`
- Аудио: `D:\calls\audio` (с подпапками)
- Выход текущий: `D:\calls\out`
- Эталон голоса: `C:\pro\mbot\ref\manager.wav`
- GPU: RTX 3060 12GB, CUDA 12.4
- Зависимости уже установлены: torch 2.6.0+cu124, faster-whisper, pyannote.audio 3.3.2

---

## 🧠 MEMORY PROTOCOL (обязательный для КАЖДОЙ сессии)

**RULE 1 — СЕССИИ НЕ ИМЕЮТ ПАМЯТИ.** Контекст AI стирается между сессиями.
Единственная память — это код в git + три журнала: `CONTINUITY.md`, `CHANGELOG.md`, `AGENTS.md`.

**RULE 2 — ОБЯЗАТЕЛЬНО в НАЧАЛЕ СЕССИИ:**
```
1. Read CONTINUITY.md (первые 200 строк) → узнать текущее состояние, последний коммит, что дальше
2. Read последние 20 строк CHANGELOG.md → узнать последние изменения
3. Сказать: "Last state: [кратко что было] / Next: [конкретный шаг]"
```

**RULE 3 — СРАЗУ ПОСЛЕ РАБОЧЕГО БЛОКА КОДА:**
```
update CONTINUITY.md с текущим статусом (не ждать конца сессии)
update CHANGELOG.md [Unreleased] одной строкой (конкретно что изменилось)
Не нужно просить — ВСЕГДА ДЕЛАЙ ЭТО АВТОМАТИЧЕСКИ
```

**RULE 4 — КОНЕЦ КАЖДОГО ОТВЕТА где был код:**
```
[Memory updated]
```
Это сигнал для пользователя, что журналы обновлены.

**RULE 5 — ЕСЛИ БЛИЗКО К ЛИМИТУ КОНТЕКСТА:**
```
update CONTINUITY.md ПЕРВЫМ (перед всем)
warning: "Context limit approaching. CONTINUITY.md saved. [дальше что нужно делать]"
```

**RULE 6 — НИКОГДА НЕ ПРОПУСКАЙ обновление памяти.**
Это единственная преемственность между сессиями. Если забудешь:
- Следующая сессия потратит час на переоткрытие контекста
- Шаги повторятся впустую
- Можно забыть текущую задачу

---

## ⚡ SLASH-КОМАНДЫ (экономия токенов)

Вместо длинных инструкций используй slash-команды из `.claude/commands/`:

| Команда | Когда | Экономия |
|---------|-------|----------|
| `/brief` | В начале сессии | ~80% токенов vs ручное чтение всех журналов |
| `/quick-status` | Быстрый обзор | без чтения больших файлов |
| `/save` | В конце сессии | tests → journal → commit → push |
| `/check-schema` | Перед SQL | читает schema.sql, предотвращает баги |

Детали: `.claude/commands/README.md`. Это дополнение к MEMORY PROTOCOL, не замена.

---

## ШАГ 0: Создать структуру проекта

```
Создать дерево каталогов:

C:\pro\callprofiler\
├── configs\
│   ├── base.yaml
│   ├── models.yaml
│   └── prompts\
│       └── analyze_v001.txt
├── src\
│   └── callprofiler\
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── db\
│       │   ├── __init__.py
│       │   ├── schema.sql
│       │   └── repository.py
│       ├── ingest\
│       │   ├── __init__.py
│       │   ├── filename_parser.py
│       │   └── ingester.py
│       ├── audio\
│       │   ├── __init__.py
│       │   └── normalizer.py
│       ├── transcribe\
│       │   ├── __init__.py
│       │   └── whisper_runner.py
│       ├── diarize\
│       │   ├── __init__.py
│       │   ├── pyannote_runner.py
│       │   └── role_assigner.py
│       ├── analyze\
│       │   ├── __init__.py
│       │   ├── llm_client.py
│       │   ├── prompt_builder.py
│       │   └── response_parser.py
│       ├── deliver\
│       │   ├── __init__.py
│       │   ├── telegram_bot.py
│       │   └── card_generator.py
│       ├── pipeline\
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   └── watcher.py
│       └── cli\
│           ├── __init__.py
│           ├── main.py
│           ├── add_user.py
│           └── reprocess.py
├── tests\
│   ├── test_filename_parser.py
│   ├── test_repository.py
│   └── fixtures\
├── data\
│   ├── users\
│   ├── db\
│   └── logs\
├── pyproject.toml
├── README.md
├── STRATEGIC_PLAN.md
└── ARCHITECTURE.md
```

Все `__init__.py` — пустые.
`pyproject.toml` — минимальный, name=callprofiler, version=0.1.0.

---

## ШАГ 1: config.py + base.yaml

**Файл:** `configs/base.yaml`

```yaml
data_dir: "D:\\calls\\data"
log_file: "D:\\calls\\data\\logs\\pipeline.log"

models:
  whisper: "large-v3"
  whisper_device: "cuda"
  whisper_compute: "float16"
  whisper_beam_size: 5
  whisper_language: "ru"
  llm_model: "qwen2.5:14b-instruct-q4_K_M"
  ollama_url: "http://localhost:11434"

pipeline:
  watch_interval_sec: 30
  file_settle_sec: 5
  max_retries: 3
  retry_interval_sec: 3600

audio:
  sample_rate: 16000
  channels: 1
  format: "wav"

hf_token: "TOKEN"
```

**Файл:** `src/callprofiler/config.py`

Загрузка YAML. Dataclass `Config` с полями. Функция `load_config(path) -> Config`.
Валидация: проверить что data_dir существует, ffmpeg доступен.

---

## ШАГ 2: models.py — dataclasses

**Файл:** `src/callprofiler/models.py`

```python
@dataclass
class CallMetadata:
    phone: str | None          # E.164
    call_datetime: datetime | None
    direction: str             # IN / OUT / UNKNOWN
    contact_name: str | None
    raw_filename: str

@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str               # OWNER / OTHER / UNKNOWN

@dataclass
class Analysis:
    priority: int              # 0-100
    risk_score: int            # 0-100
    summary: str
    action_items: list[str]
    promises: list[dict]
    flags: dict
    key_topics: list[str]
    raw_response: str
    model: str
    prompt_version: str
```

---

## ШАГ 3: db/schema.sql + db/repository.py

**Файл:** `src/callprofiler/db/schema.sql`

Таблицы: users, contacts, calls, transcripts, analyses, promises, transcripts_fts.
Полная схема — из ARCHITECTURE_v3.md, секция "Модель данных".

**Файл:** `src/callprofiler/db/repository.py`

Класс `Repository`:

```python
class Repository:
    def __init__(self, db_path: str): ...
    def init_db(self): ...                          # CREATE TABLE IF NOT EXISTS

    # users
    def get_user(self, user_id: str) -> dict | None
    def get_all_users(self) -> list[dict]
    def add_user(self, user_id, display_name, telegram_chat_id,
                 incoming_dir, sync_dir, ref_audio) -> None

    # contacts
    def get_or_create_contact(self, user_id, phone_e164, display_name=None) -> int
    def get_contact(self, contact_id) -> dict | None
    def get_contact_by_phone(self, user_id, phone_e164) -> dict | None

    # calls
    def call_exists(self, user_id, source_md5) -> bool
    def create_call(self, user_id, contact_id, direction, call_datetime,
                    source_filename, source_md5, audio_path) -> int
    def update_call_status(self, call_id, status, error_message=None) -> None
    def update_call_paths(self, call_id, norm_path, duration_sec) -> None
    def get_pending_calls(self) -> list[dict]       # status='new'
    def get_error_calls(self, max_retries=3) -> list[dict]
    def get_calls_for_user(self, user_id, limit=20) -> list[dict]

    # transcripts
    def save_transcripts(self, call_id, segments: list[Segment]) -> None
    def get_transcript(self, call_id) -> list[dict]
    def search_transcripts(self, user_id, query) -> list[dict]  # FTS5

    # analyses
    def save_analysis(self, call_id, analysis: Analysis) -> None
    def get_analysis(self, call_id) -> dict | None
    def get_recent_analyses(self, user_id, contact_id, limit=5) -> list[dict]
    def set_feedback(self, analysis_id, feedback) -> None

    # promises
    def save_promises(self, user_id, contact_id, call_id, promises: list[dict]) -> None
    def get_open_promises(self, user_id) -> list[dict]
    def get_contact_promises(self, user_id, contact_id) -> list[dict]
```

Каждый метод, работающий с данными пользователя, ОБЯЗАН фильтровать по user_id.
Использовать `sqlite3` напрямую, без ORM.

**Тест:** `tests/test_repository.py` — in-memory SQLite, проверить CRUD + изоляцию user_id.

---

## ШАГ 4: ingest/filename_parser.py

**Файл:** `src/callprofiler/ingest/filename_parser.py`

Функция `parse_filename(filename: str) -> CallMetadata`.

Поддержать форматы:
1. `20260328_143022_OUT_+79161234567_Иванов.mp3` (BCR)
2. `(28.03.2026 14-30-22) Иванов +79161234567 OUT.m4a` (скобочный)
3. `+79161234567_20260328143022_OUT.wav` (ACR)
4. Любой нераспознанный → `phone=None, direction=UNKNOWN`

Нормализация номера: `8(916)123-45-67` → `+79161234567`.

**Тест:** `tests/test_filename_parser.py` — минимум 15 кейсов, включая грязные имена.

---

## ШАГ 5: audio/normalizer.py

**Файл:** `src/callprofiler/audio/normalizer.py`

Вырезать `convert_to_wav()` из `batch_asr.py`. Обернуть:

```python
def normalize(src_path: str, dst_path: str) -> None:
    """ffmpeg → WAV 16kHz mono. Raises RuntimeError on failure."""

def get_duration_sec(wav_path: str) -> int:
    """ffprobe → duration in seconds."""
```

Проверить что ffmpeg доступен при импорте модуля.

---

## ШАГ 6: transcribe/whisper_runner.py

**Файл:** `src/callprofiler/transcribe/whisper_runner.py`

Вырезать из `batch_asr.py`: `load_whisper()`, `transcribe()`. Обернуть:

```python
class WhisperRunner:
    def __init__(self, config: Config): ...
    def load(self) -> None: ...
    def transcribe(self, wav_path: str) -> list[Segment]: ...
    def unload(self) -> None:
        """del self.model, gc.collect(), torch.cuda.empty_cache()"""
```

Выход `transcribe()` → список `Segment(start_ms, end_ms, text, speaker='UNKNOWN')`.
Конвертация float секунд → int миллисекунд здесь.

---

## ШАГ 7: diarize/pyannote_runner.py + role_assigner.py

**Файл:** `src/callprofiler/diarize/pyannote_runner.py`

Вырезать из `batch_asr.py`: `load_pyannote()`, `diarize()`, `get_embedding()`, `build_ref_embedding()`.

```python
class PyannoteRunner:
    def __init__(self, config: Config): ...
    def load(self, ref_audio_path: str) -> None:
        """Загрузить модели + построить ref embedding."""
    def diarize(self, wav_path: str) -> list[dict]:
        """Возвращает [{start_ms, end_ms, speaker: 'OWNER'|'OTHER'}]"""
    def unload(self) -> None: ...
```

Внутри: та же логика cosine similarity с ref embedding из batch_asr.py.
Маппинг: ref_label → OWNER, other → OTHER.

**Файл:** `src/callprofiler/diarize/role_assigner.py`

Вырезать `assign_speakers()` из `batch_asr.py`:

```python
def assign_speakers(
    segments: list[Segment],
    diarization: list[dict]
) -> list[Segment]:
    """Назначить speaker каждому сегменту по overlap."""
```

Та же логика: overlap → best match → fallback nearest.

---

## ШАГ 8: ingest/ingester.py

**Файл:** `src/callprofiler/ingest/ingester.py`

```python
class Ingester:
    def __init__(self, repo: Repository, config: Config): ...

    def ingest_file(self, user_id: str, filepath: str) -> int | None:
        """
        1. parse_filename(filepath)
        2. md5 hash
        3. check duplicate: repo.call_exists(user_id, md5)
        4. get_or_create_contact(user_id, phone)
        5. copy original to data/users/{user_id}/audio/originals/
        6. repo.create_call(...) → call_id
        7. return call_id (or None if duplicate)
        """
```

---

## ШАГ 9: analyze/llm_client.py + prompt_builder.py + response_parser.py

**Файл:** `configs/prompts/analyze_v001.txt`

```
Ты — ассистент для анализа телефонных разговоров.
Проанализируй стенограмму и верни ТОЛЬКО валидный JSON без markdown:

{
  "priority": <0-100, насколько важен звонок>,
  "risk_score": <0-100, уровень риска/проблемности>,
  "summary": "<2-4 предложения, суть разговора>",
  "action_items": ["<что нужно сделать>", ...],
  "promises": [
    {"who": "OWNER|OTHER", "what": "<что обещано>", "due": "<YYYY-MM-DD или null>"}
  ],
  "flags": {
    "urgent": <true/false>,
    "follow_up_needed": <true/false>,
    "conflict_detected": <true/false>
  },
  "key_topics": ["<тема1>", "<тема2>", ...]
}

Метаданные звонка:
Контакт: {contact_name} ({phone})
Дата: {call_datetime}
Направление: {direction}
Длительность: {duration}

{context_block}

Стенограмма:
{transcript}
```

**Файл:** `src/callprofiler/analyze/llm_client.py`

```python
class OllamaClient:
    def __init__(self, base_url: str, model: str): ...
    def generate(self, prompt: str) -> str:
        """POST /api/generate, вернуть response text."""
```

**Файл:** `src/callprofiler/analyze/prompt_builder.py`

```python
class PromptBuilder:
    def __init__(self, prompts_dir: str): ...
    def build(self, transcript_text: str, metadata: dict,
              previous_summaries: list[str] = None,
              version: str = "v001") -> str:
        """Загрузить шаблон, подставить переменные."""
```

**Файл:** `src/callprofiler/analyze/response_parser.py`

```python
def parse_llm_response(raw: str) -> Analysis:
    """
    Извлечь JSON из ответа LLM.
    Обработать: markdown-обёртки, невалидный JSON, отсутствующие поля.
    При ошибке парсинга → Analysis с defaults и raw_response для отладки.
    """
```

---

## ШАГ 10: deliver/card_generator.py

**Файл:** `src/callprofiler/deliver/card_generator.py`

```python
class CardGenerator:
    def __init__(self, repo: Repository): ...

    def generate_card(self, user_id: str, contact_id: int) -> str:
        """
        Собрать:
        - display_name, phone из contacts
        - последний analysis (summary, risk)
        - кол-во звонков
        - открытые promises
        Вернуть текст ≤ 500 символов.
        """

    def write_card(self, user_id: str, contact_id: int, sync_dir: str) -> None:
        """Записать {phone_e164}.txt в sync_dir."""

    def update_all_cards(self, user_id: str) -> None:
        """Пересоздать карточки для всех контактов пользователя."""
```

---

## ШАГ 11: deliver/telegram_bot.py

**Файл:** `src/callprofiler/deliver/telegram_bot.py`

```python
class TelegramNotifier:
    def __init__(self, token: str, repo: Repository): ...

    async def send_summary(self, user_id: str, call_id: int) -> None:
        """Отправить саммари звонка пользователю по его chat_id."""

    async def handle_feedback(self, callback_query) -> None:
        """Обработать нажатие [OK] / [Неточно]."""

    # Команды
    async def cmd_digest(self, update, context) -> None:    # /digest [N]
    async def cmd_search(self, update, context) -> None:    # /search текст
    async def cmd_contact(self, update, context) -> None:   # /contact +7...
    async def cmd_promises(self, update, context) -> None:  # /promises
    async def cmd_status(self, update, context) -> None:    # /status

    def run(self) -> None:
        """Запустить polling в отдельном потоке."""
```

---

## ШАГ 12: pipeline/orchestrator.py

**Файл:** `src/callprofiler/pipeline/orchestrator.py`

Это главный модуль. Собирает всё вместе.

```python
class Orchestrator:
    def __init__(self, config: Config, repo: Repository): ...

    def process_call(self, call_id: int) -> bool:
        """
        1. repo.update_call_status(call_id, 'transcribing')
        2. normalize audio → save norm_path
        3. whisper_runner.load()
        4. segments = whisper_runner.transcribe(norm_path)
        5. whisper_runner.unload()  ← освободить GPU

        6. repo.update_call_status(call_id, 'diarizing')
        7. pyannote_runner.load(ref_audio)
        8. diarization = pyannote_runner.diarize(norm_path)
        9. segments = role_assigner.assign_speakers(segments, diarization)
        10. pyannote_runner.unload()  ← освободить GPU
        11. repo.save_transcripts(call_id, segments)

        12. repo.update_call_status(call_id, 'analyzing')
        13. transcript_text = format_transcript(segments)
        14. previous = repo.get_recent_analyses(user_id, contact_id)
        15. prompt = prompt_builder.build(transcript_text, metadata, previous)
        16. raw = ollama_client.generate(prompt)
        17. analysis = parse_llm_response(raw)
        18. repo.save_analysis(call_id, analysis)
        19. repo.save_promises(...)

        20. card_generator.write_card(user_id, contact_id, sync_dir)
        21. telegram.send_summary(user_id, call_id)
        22. repo.update_call_status(call_id, 'done')
        """

    def process_pending(self) -> None:
        """Обработать все calls со status='new'."""

    def retry_errors(self) -> None:
        """Повторить calls со status='error' и retry_count < 3."""
```

**ВАЖНО:** модели Whisper и pyannote можно загружать один раз при старте и держать в памяти (как в batch_asr.py), а выгружать только перед LLM. Это быстрее, чем загружать/выгружать на каждый файл.

Оптимизированный вариант:

```python
def process_batch(self, call_ids: list[int]) -> None:
    """
    1. Загрузить Whisper + pyannote
    2. Для каждого call: transcribe + diarize
    3. Выгрузить Whisper + pyannote
    4. Для каждого call: LLM analyze (Ollama сам управляет моделью)
    """
```

---

## ШАГ 13: pipeline/watcher.py

**Файл:** `src/callprofiler/pipeline/watcher.py`

```python
class FileWatcher:
    def __init__(self, config: Config, repo: Repository,
                 ingester: Ingester, orchestrator: Orchestrator): ...

    def scan_all_users(self) -> list[int]:
        """
        Для каждого user в repo.get_all_users():
          Сканировать incoming_dir
          Для каждого аудиофайла:
            ingester.ingest_file() → call_id
          Вернуть список новых call_id
        """

    def run_loop(self) -> None:
        """
        while True:
          new_ids = scan_all_users()
          if new_ids:
            orchestrator.process_batch(new_ids)
          orchestrator.retry_errors()
          sleep(config.watch_interval_sec)
        """
```

---

## ШАГ 14: cli/main.py — точка входа

**Файл:** `src/callprofiler/cli/main.py`

```python
"""
Использование:
  python -m callprofiler watch          # основной режим: watchdog + обработка
  python -m callprofiler process <file> # обработать один файл
  python -m callprofiler reprocess      # повторить ошибки
  python -m callprofiler add-user ...   # добавить пользователя
  python -m callprofiler digest <user>  # сгенерировать дайджест
  python -m callprofiler status         # показать состояние очереди
"""
```

Парсинг аргументов через `argparse`.

**Файл:** `src/callprofiler/__main__.py`

```python
from callprofiler.cli.main import main
main()
```

---

## ШАГ 15: Интеграционный тест

Ручной прогон полного цикла:

```cmd
cd C:\pro\callprofiler

:: Добавить пользователя
python -m callprofiler add-user serhio --display-name "Сергей" --incoming "D:\calls\audio" --ref-audio "C:\pro\mbot\ref\manager.wav" --sync-dir "D:\calls\sync\serhio\cards"

:: Обработать один файл
python -m callprofiler process "D:\calls\audio\test_call.mp3" --user serhio

:: Проверить результат
:: - запись в БД (calls, transcripts, analyses)
:: - карточка в D:\calls\sync\serhio\cards\{phone}.txt
:: - (если настроен Telegram) саммари в чат

:: Запустить watchdog
python -m callprofiler watch
```

---

## Порядок выполнения (сводка)

| # | Модуль | Зависит от | Сложность |
|---|--------|-----------|-----------|
| 0 | Структура + pyproject.toml | — | 5 мин |
| 1 | config.py + base.yaml | — | 15 мин |
| 2 | models.py | — | 10 мин |
| 3 | db/schema.sql + repository.py | models | 1 час |
| 4 | ingest/filename_parser.py + тесты | models | 45 мин |
| 5 | audio/normalizer.py | config | 15 мин |
| 6 | transcribe/whisper_runner.py | config, models | 30 мин |
| 7 | diarize/pyannote_runner.py + role_assigner.py | config, models | 45 мин |
| 8 | ingest/ingester.py | repo, parser, normalizer | 30 мин |
| 9 | analyze/* (client, prompt, parser) | config, models | 1 час |
| 10 | deliver/card_generator.py | repo | 30 мин |
| 11 | deliver/telegram_bot.py | repo | 1 час |
| 12 | pipeline/orchestrator.py | ВСЕ ВЫШЕ | 1 час |
| 13 | pipeline/watcher.py | orchestrator, ingester | 30 мин |
| 14 | cli/main.py | orchestrator, watcher | 30 мин |
| 15 | Интеграционный тест | ВСЕ | 1 час |

---

## Правила для Claude Code

1. **Не использовать venv.** Всё ставить в системный Python: `pip install X --break-system-packages`.
2. **Не менять рабочий стек.** torch 2.6.0+cu124, faster-whisper, pyannote.audio 3.3.2 — зафиксированы.
3. **Patch torch.load** обязателен (weights_only=False). Копировать из batch_asr.py.
4. **use_auth_token=** (не token=) для pyannote 3.3.2.
5. **HF_TOKEN** = `TOKEN`.
6. **Запуск из cmd:** `python -m callprofiler <command>`.
7. **Кодировка файлов:** UTF-8 везде.
8. **При ошибке на любом шаге** — не ронять pipeline, логировать и идти дальше.
9. **Каждый модуль** должен работать автономно (можно протестировать отдельно).
10. **Не добавлять** то, чего нет в плане. Никаких Docker, Redis, WhisperX, ECAPA enrollment.

---

## Git Branch Policy

**РАЗРЕШЕНИЕ (2026-04-14):** Claude может пушить напрямую в `main` БЕЗ PR.

- **Development branch:** `claude/clone-callprofiler-repo-hL5dQ` (для промежуточной работы)
- **Push destination:** `main` (прямой пуш, без PR)
- **Strategy:**
  1. Работать на feature branch (для отдельных задач)
  2. При готовности: merge в `main` и push
  3. Все critical files (CLAUDE.md, CHANGELOG.md, CONTINUITY.md, AGENTS.md) ВСЕГДА обновлены перед push
  4. Каждый коммит включает "Journal updated: CHANGELOG.md + CONTINUITY.md"
