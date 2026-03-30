# CHANGELOG.md

Все значимые изменения в проекте фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/).
Версионирование: [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `CONSTITUTION.md` — принципы и правила разработки проекта
- `CONTINUITY.md` — журнал непрерывности: статус, что сделано, что дальше

---

## [0.1.0] — 2026-03-30

### Added — Шаг 0: Структура проекта
- Полное дерево каталогов `src/callprofiler/` со всеми подпакетами
- `pyproject.toml` (name=callprofiler, version=0.1.0)
- Пустые `__init__.py` во всех пакетах
- `__main__.py` — точка входа `python -m callprofiler`
- `data/db/`, `data/logs/`, `data/users/`, `tests/fixtures/` (с `.gitkeep`)
- `reference_batch_asr.py` — эталонный прототип для извлечения логики

### Added — Шаг 1: Конфигурация
- `configs/base.yaml` — базовая конфигурация (пути, модели, pipeline, audio)
- `configs/models.yaml` — спецификации моделей
- `configs/prompts/analyze_v001.txt` — шаблон промпта для LLM-анализа
- `src/callprofiler/config.py` — загрузчик YAML, dataclass Config, валидация
  - Проверка существования `data_dir`
  - Проверка доступности ffmpeg в PATH

### Added — Шаг 2: Модели данных
- `src/callprofiler/models.py`:
  - `CallMetadata` — метаданные звонка (телефон, дата, направление)
  - `Segment` — сегмент транскрипции (start_ms, end_ms, text, speaker)
  - `Analysis` — результат LLM-анализа (priority, risk_score, summary, …)

### Added — Шаг 3: База данных
- `src/callprofiler/db/schema.sql` — схема SQLite:
  - Таблицы: users, contacts, calls, transcripts, analyses, promises
  - FTS5 виртуальная таблица `transcripts_fts` для полнотекстового поиска
- `src/callprofiler/db/repository.py` — класс `Repository`:
  - CRUD для users, contacts, calls, transcripts, analyses, promises
  - Изоляция данных по `user_id` во всех запросах
  - FTS5 поиск по транскрипциям
- `tests/test_repository.py` — тесты in-memory SQLite, проверка CRUD + изоляции

### Added — Шаг 4: Парсер имён файлов
- `src/callprofiler/ingest/filename_parser.py`:
  - Функция `parse_filename(filename) -> CallMetadata`
  - Поддержка форматов: BCR, скобочный, ACR, нераспознанный
  - Нормализация номера в E.164 (`8(916)123-45-67` → `+79161234567`)
- `tests/test_filename_parser.py` — 15+ тест-кейсов, включая "грязные" имена

### Added — Шаг 5: Нормализация аудио
- `src/callprofiler/audio/normalizer.py`:
  - `normalize(src, dst, *, loudnorm, sample_rate, channels)`:
    - Двухпроходная EBU R128 LUFS-нормализация (цель: -16 LUFS / TP -1.5 dBFS)
    - Fallback к простой конвертации при сбое анализа
    - Защита от битых файлов (проверка минимального размера)
  - `get_duration_sec(wav_path) -> int` — длительность через ffprobe
  - Проверка ffmpeg/ffprobe при импорте модуля
  - Логирование через стандартный `logging`
  - Создание родительских директорий для dst автоматически

### Added — Шаг 6: Транскрибирование (Whisper)
- `src/callprofiler/transcribe/whisper_runner.py`:
  - **Класс `WhisperRunner`** — инкапсуляция загрузки/выгрузки faster-whisper
  - `load()` — загрузка модели (cuda/cpu автоматически, compute_type из config)
  - `transcribe(wav_path) -> list[Segment]`:
    - Конвертация float секунд → int миллисекунды
    - VAD-фильтр (min_silence_duration_ms=400), beam search, condition on previous text
    - Язык, beam_size из config
    - Возврат `list[Segment]` (не dict) с speaker='UNKNOWN'
    - Фильтрация пустых сегментов
  - `unload()` — выгрузка (del, gc.collect, torch.cuda.empty_cache)
  - Логирование device, GPU-info, статус операций
  - Типизированный код, обработка ошибок с контекстом

---

## Технический стек

| Компонент | Версия |
|-----------|--------|
| Python | 3.x (системный) |
| torch | 2.6.0+cu124 |
| faster-whisper | latest |
| pyannote.audio | 3.3.2 |
| GPU | NVIDIA RTX 3060 12GB |
| CUDA | 12.4 |
