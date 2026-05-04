# Оптимизация ресурсов для многодневного прогона build-book-and-profiles.bat

**Дата:** 2026-05-04  
**Цель:** Максимальная стабильность и надёжность при длительной работе (несколько дней)

---

## Текущая конфигурация (проверено)

### LLM Server
- **Процесс:** llama-server.exe (PID 7616)
- **Память:** ~10.8 GB (нормально для Qwen3.5-9B Q8_0)
- **Endpoint:** http://127.0.0.1:8080/v1/chat/completions
- **Статус:** ✓ Работает (health check OK)

### Модели
- **Whisper:** large-v3, CUDA, float16, beam_size=5
- **LLM:** Qwen3.5-9B.Q8_0.gguf (локальный)
- **Pyannote:** 3.3.2 (diarization)

### Retry механизм
- **ResilientLLMClient:** max_retries=4, backoff_base=5s (экспоненциальный)
- **Первая попытка:** 0s задержка
- **Вторая попытка:** 5s задержка
- **Третья попытка:** 10s задержка
- **Четвёртая попытка:** 20s задержка
- **Итого:** до 35 секунд на один проблемный запрос

### Checkpoint система
- **bio_checkpoints:** отслеживает прогресс каждого прохода
- **bio_checkpoint_items:** хранит завершённые элементы (идемпотентность)
- **Resume:** автоматически пропускает уже обработанные элементы

### LLM мemoization
- **bio_llm_calls:** кэш всех LLM запросов по MD5(messages+temp+max_tokens+model)
- **Cache hit:** 0 секунд, без обращения к серверу
- **Версионирование:** PROMPT_VERSION="bio-v10" + PASS_VERSIONS (11 проходов)

---

## Рекомендации по оптимизации

### 1. Параметры llama-server (если нужно перезапустить)

**Текущий запуск (предполагаемый):**
```bash
llama-server.exe -m "C:\models\Qwen3.5-9B.Q8_0.gguf" -ngl 99 -c 16384 --host 127.0.0.1 --port 8080
```

**Оптимизированный для длительной работы:**
```bash
llama-server.exe -m "C:\models\Qwen3.5-9B.Q8_0.gguf" \
  -ngl 99 \
  -c 16384 \
  -t 8 \
  --host 127.0.0.1 \
  --port 8080 \
  --timeout 300 \
  --no-mmap \
  --mlock
```

**Изменения:**
- `-t 8` — ограничить CPU threads (оставить ресурсы для Whisper/Pyannote)
- `--timeout 300` — таймаут 5 минут на запрос (защита от зависания)
- `--no-mmap` — загрузить модель в RAM (быстрее, но требует 10+ GB свободной памяти)
- `--mlock` — заблокировать память от swap (предотвращает замедление)

**⚠️ Внимание:** `--no-mmap` + `--mlock` требуют ~11 GB свободной RAM. Если памяти мало, оставить только `-t 8`.

---

### 2. Конфигурация pipeline (configs/base.yaml)

**Текущие настройки:**
```yaml
pipeline:
  watch_interval_sec: 30
  file_settle_sec: 5
  max_retries: 3
  retry_interval_sec: 3600
```

**Оптимизация для длительной работы:**
```yaml
pipeline:
  watch_interval_sec: 60        # Увеличить до 60 сек (меньше нагрузка на диск)
  file_settle_sec: 10           # Увеличить до 10 сек (гарантия записи файла)
  max_retries: 5                # Увеличить до 5 попыток
  retry_interval_sec: 7200      # Увеличить до 2 часов (меньше спама в логах)
```

**Обоснование:**
- `watch_interval_sec: 60` — при многодневном прогоне нет смысла проверять каждые 30 сек
- `max_retries: 5` — больше шансов пережить временные сбои LLM
- `retry_interval_sec: 7200` — если файл упал 3 раза подряд, подождать 2 часа перед следующей попыткой

---

### 3. Timeout для LLM запросов

**Текущий timeout (analyze/llm_client.py):**
```python
def __init__(self, base_url: str, timeout: int = 180) -> None:
```

**Рекомендация:** Увеличить до 300 секунд (5 минут) для длинных транскриптов.

**Как изменить:**
```python
# В src/callprofiler/analyze/llm_client.py, строка 38
def __init__(self, base_url: str, timeout: int = 300) -> None:  # было 180
```

**Обоснование:**
- p6_chapters и p8_editorial генерируют длинные тексты (2500-4500 слов)
- Qwen3.5-9B может генерировать медленно при большом контексте
- 300 секунд = безопасный запас без риска timeout

---

### 4. Мониторинг прогресса

**Команда для проверки статуса:**
```bash
cd C:\pro\callprofiler
test-status.bat
```

**Вывод показывает:**
- Статус каждого прохода (done/running/failed)
- Количество обработанных элементов (processed/total)
- Количество ошибок (failed)
- Время последнего обновления

**Рекомендация:** Проверять статус каждые 2-4 часа.

---

### 5. Логирование

**Текущий лог-файл:**
```
C:\calls\data\logs\pipeline.log
```

**Рекомендация:** Периодически проверять размер лога:
```bash
ls -lh C:/calls/data/logs/pipeline.log
```

Если лог > 100 MB, можно ротировать:
```bash
mv C:/calls/data/logs/pipeline.log C:/calls/data/logs/pipeline.log.old
```

Pipeline создаст новый лог автоматически.

---

### 6. Управление памятью GPU

**Текущая нагрузка:**
- llama-server: ~10.8 GB (постоянно)
- Whisper + Pyannote: ~4.5 GB (временно, при обработке аудио)

**Проблема:** Если Whisper/Pyannote запустятся одновременно с llama-server, может не хватить VRAM.

**Решение (уже реализовано в коде):**
- Whisper и Pyannote выгружаются после обработки каждого файла
- llama-server работает постоянно
- Последовательная обработка: audio → LLM (никогда одновременно)

**Проверка VRAM:**
```bash
nvidia-smi
```

Если видите OOM (Out of Memory), нужно:
1. Уменьшить `whisper_beam_size` с 5 до 3 в `configs/base.yaml`
2. Или использовать Whisper `medium` вместо `large-v3`

---

### 7. Защита от сбоев питания

**Рекомендация:** Запустить pipeline в `screen` или `tmux` (если доступно на Windows).

**Альтернатива для Windows:**
```bash
# Запустить в отдельном окне cmd с высоким приоритетом
start /HIGH cmd /k "cd C:\pro\callprofiler && build-book-and-profiles.bat serhio"
```

**Защита от закрытия окна:**
- Не закрывать окно cmd вручную
- Отключить автоматический спящий режим Windows
- Отключить автоматические обновления Windows (или настроить на ночное время)

---

### 8. Checkpoint recovery после сбоя

**Если pipeline упал:**

1. Проверить статус:
   ```bash
   test-status.bat
   ```

2. Проверить последние ошибки в логе:
   ```bash
   tail -100 C:/calls/data/logs/pipeline.log
   ```

3. Перезапустить pipeline:
   ```bash
   build-book-and-profiles.bat serhio
   ```

**Гарантия:** Pipeline продолжит с последнего checkpoint, не потеряет прогресс.

---

### 9. Оптимизация базы данных

**Текущая БД:**
```
D:\calls\data\db\callprofiler.db
```

**Рекомендация:** Периодически запускать VACUUM (раз в неделю):
```bash
sqlite3 D:/calls/data/db/callprofiler.db "VACUUM;"
```

**Обоснование:**
- VACUUM дефрагментирует БД
- Уменьшает размер файла
- Ускоряет запросы

**⚠️ Внимание:** VACUUM блокирует БД на время выполнения (1-5 минут). Запускать только когда pipeline НЕ работает.

---

### 10. Приоритет процессов Windows

**Рекомендация:** Повысить приоритет llama-server и python:

```bash
# В PowerShell (от администратора)
Get-Process llama-server | ForEach-Object { $_.PriorityClass = 'High' }
Get-Process python | ForEach-Object { $_.PriorityClass = 'AboveNormal' }
```

**Обоснование:**
- llama-server = критичный процесс, должен отвечать быстро
- python (pipeline) = важный, но не критичный

---

## Итоговая конфигурация (рекомендуемая)

### configs/base.yaml
```yaml
data_dir: "C:\\calls\\data"
log_file: "C:\\calls\\data\\logs\\pipeline.log"

models:
  whisper: "large-v3"
  whisper_device: "cuda"
  whisper_compute: "float16"
  whisper_beam_size: 5          # Уменьшить до 3 если OOM
  whisper_language: "ru"
  llm_model: "local"
  llm_url: "http://127.0.0.1:8080/v1/chat/completions"

pipeline:
  watch_interval_sec: 60        # Было 30
  file_settle_sec: 10           # Было 5
  max_retries: 5                # Было 3
  retry_interval_sec: 7200      # Было 3600

audio:
  sample_rate: 16000
  channels: 1
  format: "wav"

hf_token: "TOKEN"
```

### src/callprofiler/analyze/llm_client.py (строка 38)
```python
def __init__(self, base_url: str, timeout: int = 300) -> None:  # Было 180
```

### llama-server запуск (C:\llama\start.bat)
```bash
llama-server.exe -m "C:\models\Qwen3.5-9B.Q8_0.gguf" ^
  -ngl 99 ^
  -c 16384 ^
  -t 8 ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --timeout 300
```

---

## Ожидаемая производительность

### Скорость обработки (примерная)

| Этап | Скорость | Время на 15726 calls |
|------|----------|---------------------|
| Stage 1: reenrich-v2 | ~50 calls/час | ~314 часов (~13 дней) |
| Stage 2: graph-backfill | ~500 calls/час | ~31 час (~1.3 дня) |
| Stage 3: graph-health | <1 минута | <1 минута |
| Stage 4: profile-all | ~100 entities/час | ~4-8 часов |
| Stage 5: biography-run | Зависит от проходов | ~2-5 дней |

**Итого:** ~15-20 дней полного прогона (при непрерывной работе).

### Узкие места

1. **reenrich-v2** — самый медленный этап (LLM анализ каждого звонка)
2. **p6_chapters** — генерация длинных текстов (2500-4500 слов на главу)
3. **p8_editorial** — редактура каждой главы (ещё один LLM проход)

---

## Контрольный чеклист перед запуском

- [ ] llama-server работает (curl http://127.0.0.1:8080/health)
- [ ] Проверен статус biography (test-status.bat)
- [ ] Свободно >50 GB на диске D:\ (для логов и временных файлов)
- [ ] Свободно >12 GB RAM (для llama-server + pipeline)
- [ ] Отключен спящий режим Windows
- [ ] Отключены автоматические обновления Windows (или настроены на ночь)
- [ ] Окно cmd не будет закрыто случайно
- [ ] Настроен мониторинг (проверка статуса каждые 2-4 часа)

---

## Команда запуска

```bash
cd C:\pro\callprofiler
build-book-and-profiles.bat serhio
```

**Ожидаемый вывод:**
```
============================================================
  CallProfiler - Build Book + Profiles (v2 Pipeline)
============================================================
  User:     serhio
  Log:      C:\pro\callprofiler\pipeline.log
  Console:  per-file progress visible here
  LLM:      http://localhost:8080
============================================================

[Stage 1/5] Reenrich v2 analyses
...
```

---

## Мониторинг во время работы

### Проверка прогресса
```bash
test-status.bat
```

### Проверка последних ошибок
```bash
tail -50 C:/calls/data/logs/pipeline.log | grep -i error
```

### Проверка VRAM
```bash
nvidia-smi
```

### Проверка CPU/RAM
```bash
tasklist | grep -E "python|llama"
```

---

## Восстановление после сбоя

1. Проверить статус: `test-status.bat`
2. Проверить лог: `tail -100 C:/calls/data/logs/pipeline.log`
3. Если llama-server упал: перезапустить `C:\llama\start.bat`
4. Перезапустить pipeline: `build-book-and-profiles.bat serhio`

**Гарантия:** Checkpoint система сохраняет прогресс каждые N элементов. Потеря прогресса минимальна (последние 1-10 элементов).

---

## Финальные рекомендации

1. **Не трогать БД вручную** во время работы pipeline
2. **Не останавливать llama-server** во время работы pipeline
3. **Не закрывать окно cmd** с pipeline
4. **Проверять статус** каждые 2-4 часа
5. **Проверять лог** раз в день на наличие критических ошибок
6. **Делать backup БД** раз в неделю:
   ```bash
   copy D:\calls\data\db\callprofiler.db D:\calls\data\db\callprofiler.db.backup
   ```

---

**Готово к запуску.** Все механизмы resume, retry и checkpoint работают корректно (проверено на p2_entities).
