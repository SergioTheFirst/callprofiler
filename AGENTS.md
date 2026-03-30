# AGENTS.md — Инструкции для AI-агентов

**Этот файл читается AI-агентами (Claude Code, Codex, Copilot) при работе с проектом.**

---

## Идентичность проекта

- **Название:** CallProfiler
- **Язык кода:** Python 3.10+
- **Язык комментариев:** русский или английский (не транслит)
- **Репозиторий:** https://github.com/SergioTheFirst/callprofiler.git
- **Ветка:** main
- **OS разработки:** Windows 10/11, cmd (НЕ WSL, НЕ bash)

---

## Обязательно прочитай перед работой

1. `CONSTITUTION.md` — что можно и нельзя в проекте
2. `CLAUDE.md` (DEVELOPMENT_PLAN) — пошаговый план разработки
3. `ARCHITECTURE_v3.md` или `STRATEGIC_PLAN_v3.md` — архитектура и стратегия
4. `reference_batch_asr.py` — работающий прототип, из которого берётся логика ASR и диаризации

---

## Среда выполнения

```
Python:           3.10+ системный (без venv, без conda)
pip install:      с флагом --break-system-packages
GPU:              RTX 3060 12GB, CUDA 12.4
torch:            2.6.0+cu124 (уже установлен)
faster-whisper:   установлен
pyannote.audio:   3.3.2 (установлен)
ffmpeg:           в PATH
Ollama:           http://localhost:11434
Запуск:           python -m callprofiler <command>
```

---

## Стиль кода

### Общее

- Типизация: type hints на всех публичных функциях и методах.
- Dataclasses для моделей данных, не dict.
- `pathlib.Path` для путей, не конкатенация строк.
- f-строки для форматирования.
- Логирование через `logging`, не `print` (кроме CLI-вывода).
- Docstring на каждом классе и публичном методе (одна строка или кратко).

### Именование

```python
# Модули и файлы
filename_parser.py          # snake_case

# Классы
class WhisperRunner:        # PascalCase

# Функции и методы
def parse_filename():       # snake_case

# Константы
MAX_RETRIES = 3             # UPPER_SNAKE_CASE

# Приватные
def _normalize_phone():     # одно подчёркивание
```

### Импорты

```python
# stdlib
import os
import hashlib
from pathlib import Path
from dataclasses import dataclass

# third-party
import torch
import yaml

# project
from callprofiler.config import Config
from callprofiler.models import CallMetadata
```

Порядок: stdlib → third-party → project. Пустая строка между группами.

### Обработка ошибок

```python
# ПРАВИЛЬНО — ловить конкретное, логировать, не терять стектрейс
try:
    result = transcribe(wav_path)
except RuntimeError as e:
    logger.error(f"Transcription failed for {wav_path}: {e}", exc_info=True)
    repo.update_call_status(call_id, "error", error_message=str(e))
    return None

# НЕПРАВИЛЬНО — голый except, silent fail
try:
    result = transcribe(wav_path)
except:
    pass
```

---

## Правила работы с кодом

### ДЕЛАЙ

- Бери логику ASR/diarize из `reference_batch_asr.py` без изменений.
- Используй `user_id` в каждом запросе к БД.
- Конвертируй float секунды → int миллисекунды при сохранении.
- Освобождай GPU перед загрузкой LLM: `gc.collect()` + `torch.cuda.empty_cache()`.
- Пиши тесты для парсера, репозитория, парсера ответов LLM.
- Коммить после каждого завершённого шага.
- Храни секреты в переменных окружения (os.environ).

### НЕ ДЕЛАЙ

- Не меняй логику `transcribe()` и `diarize()` из batch_asr.py.
- Не добавляй зависимости, которых нет в плане (никаких langchain, celery, redis, docker).
- Не пиши код для venv, conda, docker, WSL.
- Не хардкодь токены (HF_TOKEN, TELEGRAM_TOKEN) — только через `os.environ.get()`.
- Не создавай файлы вне структуры из DEVELOPMENT_PLAN.
- Не используй ORM (SQLAlchemy, Peewee) — только sqlite3 напрямую.
- Не добавляй WhisperX, ECAPA-TDNN, Neo4j, ChromaDB.
- Не удаляй и не модифицируй оригинальные аудиофайлы.
- Не запускай две GPU-модели, которые не помещаются вместе (>12GB суммарно).

---

## Обязательные хаки

### torch 2.6 weights_only fix

Вставлять в любой модуль, который загружает модели pyannote/speechbrain:

```python
import torch as _torch
_original_load = _torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_load(*args, **kwargs)
_torch.load = _patched_load
```

### pyannote 3.3.2 auth

```python
# ПРАВИЛЬНО
Model.from_pretrained("pyannote/embedding", use_auth_token=HF_TOKEN)

# НЕПРАВИЛЬНО (не работает в 3.3.2)
Model.from_pretrained("pyannote/embedding", token=HF_TOKEN)
```

---

## Структура БД

Каждая таблица с пользовательскими данными содержит `user_id`. Каждый SELECT, UPDATE, DELETE фильтрует по `user_id`.

```python
# ПРАВИЛЬНО
def get_calls(self, user_id: str, limit: int = 20) -> list[dict]:
    self.cur.execute(
        "SELECT * FROM calls WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )

# НЕПРАВИЛЬНО — нет фильтра по user_id
def get_calls(self, limit: int = 20) -> list[dict]:
    self.cur.execute("SELECT * FROM calls ORDER BY created_at DESC LIMIT ?", (limit,))
```

---

## Git-команды

После завершения работы:

```bash
git add .
git commit -m "описание что сделано"
git push origin main
```

Формат коммитов:
```
step-03: create schema.sql and repository.py
step-04: add filename_parser with tests
fix: remove hardcoded token from config
refactor: extract normalizer from batch_asr
```

---

## Порядок выполнения шагов

Если дан промпт «выполни ШАГ N» — найди этот шаг в `CLAUDE.md` (DEVELOPMENT_PLAN) и выполни точно по описанию.

Не перескакивай шаги. Не объединяй больше двух шагов за раз.

Если шаг требует код из `reference_batch_asr.py` — прочитай файл, извлеки нужные функции, оберни в класс/модуль по структуре проекта.

---

## Тестирование

```bash
# Запуск всех тестов
python -m pytest tests/ -v

# Запуск одного теста
python -m pytest tests/test_filename_parser.py -v
```

Тесты БД — на in-memory SQLite (`:memory:`).
Тесты парсера — без внешних зависимостей.
Тесты с GPU — только интеграционные, запускаются вручную.

---

## Чеклист перед коммитом

- [ ] Нет хардкоженных токенов (grep `hf_`, grep `bot_token`)
- [ ] Каждый запрос к БД фильтрует по `user_id`
- [ ] Ошибки ловятся конкретно, логируются, записываются в БД
- [ ] Type hints на публичных методах
- [ ] Тесты проходят (`python -m pytest tests/ -v`)
- [ ] Нет `__pycache__` в коммите (проверить .gitignore)

---

## Контекст для LLM-промптов

Когда строишь промпт для Ollama в `prompt_builder.py`, всегда включай:

```
1. Полную стенограмму с метками [OWNER] / [OTHER]
2. Метаданные: номер, имя контакта, дата, направление, длительность
3. (Фаза 3+) Саммари последних 5 звонков с этим контактом
```

Выход LLM всегда парси как JSON. При ошибке парсинга — сохрани raw ответ в `raw_llm_response`, создай Analysis с дефолтными значениями.

---

## Что делать при неясности

1. Прочитай CONSTITUTION.md — скорее всего ответ там.
2. Если вопрос об архитектуре — прочитай ARCHITECTURE_v3.md.
3. Если вопрос о конкретном шаге — прочитай CLAUDE.md.
4. Если вопрос о логике ASR/diarize — прочитай reference_batch_asr.py.
5. Не додумывай. Не добавляй компоненты, которых нет в плане.
