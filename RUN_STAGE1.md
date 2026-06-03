# Stage-1 Runbook — GigaAM v3: audio → текст → БД (+ LLM)

Запускать на машине с GPU и моделью `C:\models\GigaAM-v3-rnnt`.
Код собран и протестирован (мок-тесты зелёные); реальный прогон — здесь.

**Отчёт о запуске** (весь лог: стадии, ошибки) автоматически пишется в
`C:\Users\SERGE\Desktop\rez.txt` (задано `log_file` в `configs/base.yaml`).
Консоль показывает то же в реальном времени. Файл дописывается между запусками —
очищайте его перед чистым прогоном, если нужно.

## Что делает Stage-1

```
C:\calls\in\**\*.{mp3,m4a,wav,ogg,opus,flac,aac,wma}
   → normalize (ffmpeg → 16кГц моно wav)
   → GigaAM v3 RNN-T (локально, нарезка окнами <25с, БЕЗ pyannote)   ← Stage-1
   → транскрипт в БД (transcripts) + читабельный .txt в C:\calls\text\<имя>.txt
   → исходник убирается из C:\calls\in (копия уже в архиве users/{uid}/audio/originals/YYYY/MM)
   → LLM-анализ (llama-server) → analyses/events/graph                ← Stage-2
```

- Спикеры пока **не размечаются** (`speaker=UNKNOWN`, в .txt все строки `[?]`).
  Роли `[me]/[s2]` добавим, когда поставим pyannote + HF_TOKEN (`enable_diarization`).
- Текст GigaAM — строчные русские буквы без пунктуации (особенность модели);
  LLM-этап с этим работает нормально.

## 0. Зависимости (один раз)

> ⚠ **Для GPU нужен Python 3.12** (не 3.14!). PyTorch не выпускает CUDA-колёса
> для cp314 → на 3.14 только CPU-сборка, RTX 3060 простаивает, GigaAM в 20-50×
> медленнее (подтверждено прогоном 2026-06-03, см. `rez.txt`).
> На 3.12 GigaAM (~1-2 ГБ) и llama-server (~10 ГБ) по очереди помещаются в 12 ГБ.

```powershell
# Python 3.12, затем:
pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-gigaam.txt
ffmpeg -version                                   # ffmpeg в PATH
python -c "import torch; print('CUDA:', torch.cuda.is_available())"   # → True
```

Проверка, что модель грузится (≈10–20с, скачает ничего — всё локально):
```powershell
python -c "from transformers import AutoModel; m=AutoModel.from_pretrained(r'C:\models\GigaAM-v3-rnnt', trust_remote_code=True); print('OK', type(m).__name__)"
```

## 1. Bootstrap (создаёт папки, БД, пользователя `me`)

```powershell
$env:PYTHONPATH="C:\pro\callprofiler\src"
python -m callprofiler bootstrap
# по умолчанию: user=me, incoming=C:\calls\in, text=C:\calls\text, ref-audio=C:\pro\mbot\ref\manager.wav
```

## 2. Разовый прогон одного файла (быстрая проверка)

```powershell
python -m callprofiler process "C:\calls\in\<подпапка>\<файл>.mp3" --user me -v
```
Ожидаем: `transcribing → N сегментов`, файл `C:\calls\text\<файл>.txt`, строки в БД.

## 3. Постоянный мониторинг (то, что нужно «прямо сейчас»)

```powershell
python -m callprofiler watch -v
```
- Следит за `C:\calls\in` (рекурсивно), берёт устоявшиеся файлы (`file_settle_sec`),
  гонит весь pipeline, после транскрибации убирает исходник из `in`.
- **Живой лог стадий — прямо в консоли** (`-v` = DEBUG): `normalizing → transcribing → analyzing → done`.

## 4. Реальное время в UI

```powershell
python -m callprofiler dashboard --user me --port 8765
# открыть http://127.0.0.1:8765
```
Дашборд (SSE + DB-poll) показывает звонки и их `status`, который оркестратор
обновляет на каждой стадии (`normalizing/transcribing/diarizing/analyzing/
delivering/done/error`) → видно, что происходит сейчас. Запускать рядом с `watch`.

## 5. Статус очереди в консоли

```powershell
python -m callprofiler status
```

## Конфиг (`configs/base.yaml`)

```yaml
log_file: "C:\\Users\\SERGE\\Desktop\\rez.txt"   # весь отчёт о запуске
models:
  asr_backend: gigaam
  gigaam_model_dir: "C:\\models\\GigaAM-v3-rnnt"
  gigaam_device: cuda
  gigaam_chunk_sec: 20      # окно нарезки (<25с)
  gigaam_overlap_sec: 0.0   # >0 — перекрытие (риск дублей слов на стыках)
pipeline:
  text_export_dir: "C:\\calls\\text"
  remove_source_on_success: true
features:                   # configs/features.yaml
  enable_diarization: false # Stage-1: ролей нет (pyannote не нужен)
  enable_llm_analysis: true # Stage-2: требует запущенного llama-server
```

LLM (Stage-2): поднять `llama-server` на `http://127.0.0.1:8080` до `watch`,
иначе анализ упадёт мягко (транскрипт в БД останется, статус error → retry).
Чтобы прогнать только Stage-1 без LLM — `enable_llm_analysis: false`.

## Тесты

```powershell
$env:PYTHONPATH="C:\pro\callprofiler\src"
python -m pytest tests/test_gigaam_runner.py tests/test_text_export.py tests/test_watcher_cleanup.py -q
```

## Известные ограничения Stage-1

- Нарезка фиксированными окнами может резать слово на стыке (раз в ~20с).
  Апгрейд: pyannote-VAD нарезка + диаризация (роли) — отдельный шаг.
- Смена ASR инвалидирует quote-зависимые данные (графа/биографии) —
  см. `.claude/rules/decisions.md` (blast-radius: `graph-replay`, `biography-run`).
