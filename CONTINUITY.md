# CONTINUITY.md — Журнал непрерывности разработки

Этот файл обновляется после **каждой рабочей сессии**.
Цель: любой разработчик или AI-агент может открыть репозиторий и мгновенно
понять, что уже сделано, что в работе, и что делать дальше.

---

## Текущее состояние: 2026-03-30

### Ветка разработки
`claude/clone-callprofiler-repo-hL5dQ`

### Выполненные шаги

| # | Модуль | Статус | Коммит |
|---|--------|--------|--------|
| 0 | Структура проекта + pyproject.toml | ✅ готово | `885d137` |
| 1 | `config.py` + `configs/base.yaml` | ✅ готово | `885d137` |
| 2 | `models.py` (dataclasses) | ✅ готово | `885d137` |
| 3 | `db/schema.sql` + `db/repository.py` | ✅ готово | `885d137` |
| 4 | `ingest/filename_parser.py` + тесты | ✅ готово | `885d137` |
| 5 | `audio/normalizer.py` | ✅ готово | `5dbe6a7` |
| 6 | `transcribe/whisper_runner.py` | ✅ готово | `6f73a99` |
| 7 | `diarize/pyannote_runner.py` + `role_assigner.py` | ✅ готово | текущий |

### В работе

| # | Модуль | Следующий исполнитель |
|---|--------|-----------------------|
| 8 | `ingest/ingester.py` | Claude / разработчик |

### Не начато

| # | Модуль |
|---|--------|
| 9 | `analyze/llm_client.py` + `prompt_builder.py` + `response_parser.py` |
| 10 | `deliver/card_generator.py` |
| 11 | `deliver/telegram_bot.py` |
| 12 | `pipeline/orchestrator.py` |
| 13 | `pipeline/watcher.py` |
| 14 | `cli/main.py` |
| 15 | Интеграционный тест |

---

## Детали шага 5: audio/normalizer.py

### Что реализовано
- `normalize(src, dst, *, loudnorm, sample_rate, channels)` — конвертация в WAV 16kHz mono
- **Двухпроходная EBU R128 LUFS-нормализация** (loudnorm=True по умолчанию)
  - Целевой уровень: -16 LUFS / True Peak -1.5 dBFS
  - Fallback к простой конвертации если ffmpeg-анализ не удался
- `get_duration_sec(wav_path)` — длительность через ffprobe
- Проверка ffmpeg/ffprobe при импорте модуля
- Защита от битых файлов (минимальный размер 1024 байт)
- Логирование через `logging.getLogger(__name__)`

---

## CONSTITUTION.md — Конституция проекта (MERGE-BLOCKING)

**Создан полный документ архитектурных принципов:**

- **Статья 1-3**: назначение (локальная мультипользовательская система), фундаментальные принципы (вертикальные срезы, работающий код > архитектуре, только измеренные проблемы)
- **Статья 4-5**: запрещённые компоненты (Docker, Redis, WhisperX, ECAPA на текущей фазе) и зафиксированный стек
- **Статья 6-8**: изоляция данных по `user_id`, дедупликация MD5, статусы звонков, структура хранения
- **Статья 9-10**: 6-шаговый pipeline, GPU-дисциплина (Whisper+pyannote вместе, LLM отдельно), caller cards для Android overlay
- **Статья 11-13**: Telegram-бот (один на всех, различает по chat_id), версионирование промптов, миграция из batch_asr.py с обязательными хаками (torch.load, use_auth_token=)
- **Статья 14-18**: правила разработки, фазы (0-5), триггеры пересмотра архитектуры (измеренные пороги), антипаттерны

**Статус:** Любой PR, противоречащий CONSTITUTION.md, не мержится без изменения самой Конституции (требует замер + решение).

---

## Детали шага 6: transcribe/whisper_runner.py

### Что реализовано
- **Класс `WhisperRunner`** с методами:
  - `__init__(config: Config)` — инициализация с конфигурацией
  - `load()` — загрузка faster-whisper large-v3 с выбором device (cuda/cpu) и compute_type (float16/int8)
  - `transcribe(wav_path: str) -> list[Segment]` — транскрибирование с конвертацией float сек → int мс
  - `unload()` — выгрузка модели + `gc.collect()` + `torch.cuda.empty_cache()`
- Параметры транскрибирования:
  - Язык: русский (`whisper_language` из config)
  - VAD-фильтр: пропуск молчания, min_silence_duration_ms=400
  - Beam search: beam_size из config (обычно 5)
  - Условный текст и коррекция артефактов (compression_ratio, no_speech_threshold)
- Логирование через `logging` (device, статус загрузки, кол-во сегментов)
- Типизация: `list[Segment]` вместо `list[dict]`
- Обработка пустых сегментов (пропускаются автоматически)
- Защита от повторной загрузки и вызова до load()

### Ключевые отличия от batch_asr.py
| Аспект | batch_asr.py | WhisperRunner |
|--------|--------------|---------------|
| Структура | функции | класс с состоянием |
| Возвращаемый тип | `list[dict]` | `list[Segment]` |
| Время | float секунды | int миллисекунды |
| Выгрузка | ручная | метод `unload()` |
| Логирование | print() | logger |
| Конфигурация | константы | Config объект |

### Почему LUFS-нормализация
Телефонные звонки имеют разный уровень записи:
- AGC на телефоне может сильно занижать/завышать сигнал
- Whisper при слишком тихом сигнале пропускает сегменты или галлюцинирует
- Цель -16 LUFS — стандарт EBU R128 для речи (та же норма, что у подкастов)
- Двухпроходный режим точнее одного прохода: сначала анализируем, затем корректируем

### Источники решений
- EBU R128 loudness recommendation
- ffmpeg `loudnorm` filter documentation
- Статья Habr #932762 (основные практики нормализации аудио для ASR)

---

## Известные ограничения и технические долги

- `configs/base.yaml` содержит `hf_token: "TOKEN"` — перед продакшн-запуском
  заменить на реальный токен HuggingFace
- `data_dir` в конфиге указывает на `D:\\calls\\data` — пути Windows,
  на Linux нужно переопределить
- `tests/` пока содержат только `test_filename_parser.py` и `test_repository.py`;
  тест для `normalizer.py` (с mock ffmpeg) — технический долг

---

---

## Детали шага 7: diarize/pyannote_runner.py + role_assigner.py

### PyannoteRunner — инкапсуляция диаризации

**Методы класса:**
- `__init__(config: Config)` — инициализация
- `load(ref_audio_path: str)` — загрузка pyannote (embedding + pipeline) + построение reference embedding
- `diarize(wav_path: str) -> list[dict]` — диаризация с маппингом OWNER/OTHER по cosine similarity
- `unload()` — выгрузка моделей + GPU cleanup

**Ключевая логика (из batch_asr.py без изменений):**
1. Запустить pyannote pipeline: `min_speakers=2, max_speakers=2`
2. Собрать сегменты по label, отфильтровать < 400мс
3. Для каждого label вычислить embedding (конкатенация его аудиосегментов)
4. Найти label с max cosine similarity к ref_embedding → это OWNER
5. Остальные → OTHER
6. Конвертировать: float сек → int мс, вернуть sorted list

**Параметры pyannote из CONSTITUTION.md Статья 13.1:**
- `use_auth_token=` (не `token=`) для pyannote 3.3.2
- Embedding model: "pyannote/embedding"
- Diarization pipeline: "pyannote/speaker-diarization-3.1"

### role_assigner.assign_speakers() — сопоставление ролей

**Функция:**
```python
def assign_speakers(
    segments: list[Segment],  # from Whisper (speaker='UNKNOWN')
    diarization: list[dict]   # from PyannoteRunner
) -> list[Segment]            # with assigned speakers
```

**Алгоритм:**
1. Для каждого Segment (start_ms, end_ms) найти диаризационный интервал с max overlap
2. Если overlap > 0 → скопировать speaker из диаризации
3. Если overlap = 0 → взять ближайший по времени интервал
4. Вернуть новый list[Segment] с назначенными ролями

**Ключевая функция:**
```python
overlap = max(0.0, min(seg_end, dia_end) - max(seg_start, dia_start))
```

### Отличия от batch_asr.py

| Аспект | batch_asr.py | PyannoteRunner |
|--------|--------------|---|
| Структура | функции (load_pyannote, diarize, get_embedding) | класс с state |
| Reference embedding | построен в load_pyannote | построен в load() |
| Возврат diarize() | `{"s": float, "e": float, "speaker": str}` | `{"start_ms": int, "end_ms": int, "speaker": str}` |
| Логирование | print() | logger |
| Выгрузка | ручная del | метод unload() |
| assign_speakers | функция, работает с dict | функция, работает с Segment |

---

## Как подхватить работу

```bash
git checkout claude/clone-callprofiler-repo-hL5dQ
git pull origin claude/clone-callprofiler-repo-hL5dQ

# Следующий шаг:
# ШАГ 8: ingest/ingester.py
# Класс Ingester для приёма файлов с диска:
#   - parse_filename()
#   - вычислить MD5 (дедупликация)
#   - check repo.call_exists(user_id, md5)
#   - get_or_create_contact()
#   - copy to data/users/{user_id}/audio/originals/
#   - repo.create_call() → call_id
# Без обработки — только ingest + DB
```
