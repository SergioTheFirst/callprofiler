# CallProfiler

Локальная мультипользовательская система обработки записей телефонных разговоров.

**Статус разработки:** 53% (8/15 шагов, см. [CONTINUITY.md](CONTINUITY.md))

## Назначение

Обработка входящих/исходящих звонков на локальной машине:
1. **Транскрибирование** русской речи (faster-whisper large-v3)
2. **Диаризация** — разделение на двух спикеров (pyannote + reference embedding)
3. **LLM-анализ** (Ollama Qwen) — извлечение саммари, приоритета, рисков, обещаний
4. **Delivery** — карточки контактов для Android overlay + Telegram дайджест

**Изоляция данных:** каждый пользователь видит только свои звонки.

## Основные зависимости

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| Python | 3.10+ | Runtime |
| torch | 2.6.0+cu124 | GPU ускорение |
| faster-whisper | latest | ASR (Whisper large-v3) |
| pyannote.audio | 3.3.2 | Speaker diarization |
| Ollama | latest | Local LLM (Qwen 2.5 14B) |
| SQLite3 | system | База данных + FTS5 |
| ffmpeg | system | Конвертация аудио |

## Ограничения

| Ограничение | Причина |
|-------------|---------|
| Только 2 спикера | Нет бизнес-задачи для >2 |
| Русский язык | По требованиям |
| No Docker | Один ПК, нулевая выгода |
| RTX 3060 12GB | Доступная GPU |
| Без облачных сервисов | Требование локальности |
| Windows (cmd) | Рабочая машина пользователя |

## Быстрый старт

### 1. Установка зависимостей

```bash
# Системные
sudo apt install ffmpeg ffprobe  # Linux
# brew install ffmpeg ffprobe   # macOS
# choco install ffmpeg          # Windows (chocolatey)

# Python зависимости (в системный Python)
pip install --break-system-packages torch==2.6.0 faster-whisper pyannote.audio==3.3.2

# Ollama (для локального LLM)
# https://ollama.ai → скачать и запустить
# ollama pull qwen2.5:14b-instruct-q4_K_M
```

### 2. Конфигурация

```bash
# Скопировать шаблон (ВАЖНО: не коммитить с реальными токенами!)
cp configs/base.yaml configs/base.local.yaml

# Отредактировать пути под вашу систему
nano configs/base.local.yaml
```

```yaml
data_dir: "/home/you/calls/data"        # Где хранить обработанные файлы
models:
  whisper_device: "cuda"                # или "cpu"
  whisper_language: "ru"
  ollama_url: "http://localhost:11434"  # Где запущен Ollama
hf_token: "YOUR_HF_TOKEN_HERE"          # https://huggingface.co/settings/tokens
```

### 3. Запуск тестов

```bash
make test              # Запустить все тесты
make test-verbose      # С выводом
make coverage          # Отчёт о покрытии
```

### 4. Запуск pipeline

```bash
# Добавить пользователя
python -m callprofiler add-user serhio \
  --display-name "Сергей" \
  --incoming /path/to/incoming/calls \
  --ref-audio /path/to/ref/manager.wav \
  --sync-dir /path/to/sync/cards

# Обработать один файл (для теста)
python -m callprofiler process /path/to/call.mp3 --user serhio

# Запустить watchdog (основной режим)
python -m callprofiler watch
```

## Структура проекта

```
callprofiler/
├── CLAUDE.md                    ← План разработки (15 шагов)
├── CONSTITUTION.md              ← Архитектурные принципы (merge-blocking)
├── CONTINUITY.md                ← Журнал непрерывности (обновляется каждый шаг)
├── CHANGELOG.md                 ← История изменений
├── README.md                    ← Этот файл
├── Makefile                     ← make test, make lint, make coverage
├── .github/workflows/
│   └── ci.yml                   ← GitHub Actions CI/CD
├── configs/
│   ├── base.yaml                ← Шаблон конфигурации
│   └── prompts/
│       └── analyze_v001.txt     ← Промпт для LLM анализа
├── src/callprofiler/            ← Основной код (969+ строк)
│   ├── config.py                ← Загрузка конфигурации
│   ├── models.py                ← Dataclasses (CallMetadata, Segment, Analysis)
│   ├── audio/normalizer.py      ← LUFS нормализация (ШАГ 5)
│   ├── transcribe/whisper_runner.py  ← Whisper wrapper (ШАГ 6)
│   ├── diarize/pyannote_runner.py    ← Pyannote + ref embedding (ШАГ 7)
│   ├── diarize/role_assigner.py      ← Сопоставление ролей
│   ├── ingest/ingester.py       ← Приём файлов + MD5 дедуп (ШАГ 8)
│   ├── db/repository.py         ← SQLite CRUD (ШАГ 3)
│   ├── analyze/                 ← LLM анализ (ШАГ 9, todo)
│   ├── deliver/                 ← Карточки + Telegram (ШАГ 10-11, todo)
│   ├── pipeline/                ← Оркестрация (ШАГ 12-13, todo)
│   └── cli/                     ← Команды (ШАГ 14, todo)
├── tests/
│   ├── test_filename_parser.py  ← 15+ кейсов парсинга
│   ├── test_repository.py       ← CRUD + изоляция user_id
│   └── fixtures/
└── .gitignore                   ← Исключить .env, __pycache__, data/
```

## Разработка

### Инструменты качества (по статье Habr #932762)

```bash
# Статический анализ
make lint               # Запустить flake8 + ruff
make format             # Форматировать код (black)

# Тесты
make test               # Все тесты
make test-unit          # Только unit тесты
make coverage           # Отчёт о покрытии

# CI/CD локально
make ci                 # Симуляция GitHub Actions локально

# Сборка и проверка
make build              # Проверить сборку (syntax check)
make validate           # Полная валидация (lint + test + coverage)
```

### Принципы разработки

По [CONSTITUTION.md](CONSTITUTION.md) — 18 статей, merge-blocking:

1. **Вертикальные срезы** — каждый шаг даёт работающий pipeline
2. **Работающий код > архитектура** — рабочий прототип важнее идеального дизайна
3. **Только измеренные проблемы** — сложность оправдывается замерами
4. **GPU-дисциплина** — load → use → unload, две модели максимум одновременно
5. **Изоляция по user_id** — каждый запрос фильтруется
6. **Логирование вместо print()** — полная трассировка
7. **Типизация с TYPE_CHECKING** — runtime efficiency

Каждый PR проверяется на соответствие CONSTITUTION.md.

## Тестирование

### Текущее покрытие

```
✅ ingest/filename_parser.py      — 15+ кейсов (BCR, скобочный, ACR форматы)
✅ db/repository.py               — CRUD + изоляция user_id
⚪ audio/normalizer.py            — TODO (mock ffmpeg)
⚪ transcribe/whisper_runner.py    — TODO (mock whisper model)
⚪ diarize/pyannote_runner.py      — TODO (mock pyannote)
⚪ pipeline/orchestrator.py        — TODO (интеграционный тест)
```

### Запуск тестов

```bash
# Все тесты
python -m pytest tests/ -v

# С покрытием
pytest tests/ --cov=src/callprofiler --cov-report=html

# Результат открыть в браузере
open htmlcov/index.html
```

## CI/CD

GitHub Actions `.github/workflows/ci.yml`:

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
      - name: Install dependencies
        run: make install
      - name: Lint
        run: make lint
      - name: Test
        run: make test
      - name: Coverage
        run: make coverage
```

## Документирование по сборке

### Локально (Linux/Mac)

```bash
git clone https://github.com/SergioTheFirst/callprofiler.git
cd callprofiler

# Проверить Python 3.10+
python --version

# Установить зависимости (см. "Быстрый старт")
pip install --break-system-packages torch==2.6.0 faster-whisper pyannote.audio==3.3.2

# Запустить тесты
make test

# Запустить приложение
python -m callprofiler --help
```

### Локально (Windows cmd)

```cmd
git clone https://github.com/SergioTheFirst/callprofiler.git
cd callprofiler

python --version
pip install --break-system-packages torch==2.6.0 faster-whisper pyannote.audio==3.3.2

python -m pytest tests/

python -m callprofiler --help
```

## Статус разработки

| Фаза | Статус | Критерий завершения |
|------|--------|-------------------|
| 0-2 | ✅ | Структура, конфиг, модели |
| 3-4 | ✅ | БД + парсер |
| 5-8 | ✅ | Audio, Whisper, Pyannote, Ingester |
| 9-11 | 🔄 | LLM анализ, доставка |
| 12-14 | ⚪ | Pipeline, CLI |
| 15 | ⚪ | Интеграционный тест |

Детальный журнал: [CONTINUITY.md](CONTINUITY.md)

## Лицензия

TBD

## Контакты

- Разработчик: Sergei
- Статус: Development
- Ветка: `claude/clone-callprofiler-repo-hL5dQ`
