# Pipeline Rules & Error Handling

## Pipeline Map (READ THIS FIRST — не перечитывать код на вопрос про pipeline)

> Источник истины для «как обрабатывается файл». Обновлять при смене стадий/статусов.
> Код: `pipeline/watcher.py`, `pipeline/orchestrator.py`, `config.py`.

**Watcher cycle** (`FileWatcher.run_loop`, каждые `watch_interval_sec`):
```
1. scan_all_users()    — обойти users.incoming_dir (из БД; дефолт C:\calls\in), рекурсивно
2. process_batch(new)  — прогнать НОВЫЕ звонки по стадиям
3. process_pending()   — добрать ЗАВИСШИЕ (status≠терминал, wav готов) после краха/сбоя
4. cleanup_sources()   — убрать исходник из incoming ТОЛЬКО при pipeline_stage>=2
5. cleanup_normalized()— снести normalized wav: СИРОТЫ (нет call-записи в БД) + терминал/stage≥2
6. retry_errors()
```
scan: MD5-дедуп (`get_call_by_md5`). Новый → ingest = КОПИЯ в архив
`users/{uid}/audio/originals/YYYY/MM` (на ВХОДЕ, до обработки). Файл-ещё-пишется →
ждать (`file_settle_sec`). Битый архив у существующего → восстановить из incoming + reset.

**Stages** (`pipeline_stage` / `status`):
| stage | status | действие | файл |
|---|---|---|---|
| 0 | new | зарегистрирован (ingest, mp3 в архив) | originals/YYYY/MM |
| 1 | normalizing | `normalize()` mp3→16k/mono/wav (атомарно: `.part`→`os.replace`) | …/normalized/`{call_id}__{источник}.wav` |
| – | diarizing | только если `enable_diarization` (pyannote) | — |
| 2 | transcribing | ASR (GigaAM) → `save_transcripts` (текст в БД) + .txt (`text_export_dir`) | wav УДАЛЯЕТСЯ если `delete_normalized_after_transcribe` |
| — | **transcribed** | ТЕРМИНАЛ Stage-1, если `enable_llm_analysis=false`. LLM не зовётся | — |
| 3 | analyzing | локальная LLM (llama-server) | — |
| 4 | delivering→**done** | карточка + Telegram | sync/ |

**Терминальные статусы:** `done` (полный путь), `transcribed` (Stage-1, LLM off), `error`.
`get_stalled_calls` реклаймит `status NOT IN (new,done,error,transcribed)`.

**Файлы/удаление:**
- mp3 источник: incoming → удаляется в `cleanup_sources` ТОЛЬКО при stage>=2 (`remove_source_on_success`); копия в `originals/YYYY/MM` остаётся = источник истины.
- normalized wav: имя = `{call_id}__{safe(источник)}.wav` (`norm_wav_path`). call_id префиксом — уникальность (нет коллизий аудио при одинаковых basename) + парсинг в `cleanup_normalized` (`stem.split("__")[0]`, back-compat со старым `{call_id}.wav`).
- **Resume без пере-нормализации:** перед `normalize()` orchestrator (оба пути) проверяет `Path(norm_path).exists()` → если есть, ffmpeg пропускается. Безопасно т.к. wav пишется атомарно (`.part`→`replace`): существование ⟺ нормализация завершена (битый `.part` не подхватится). Окно полезности = wav нормализован, но звонок прерван ДО транскрибации (после неё wav удалён).
- **Удаление сразу после текста КАЖДОГО файла:** в batch объединён Pass B+C — `save_transcripts`+stage2+`_maybe_delete_normalized` в одном цикле сразу после ASR звонка (ASR-модель грузится раз на батч). Не «весь батч, потом удаление»: wav сносится в момент готовности его текста. Гейт `delete_normalized_after_transcribe:true` (base.yaml). Регенерируется из mp3 — потеря невозможна. Подстраховка-sweep: `watcher.cleanup_normalized` ловит орфаны.

**Perf (2026-06-06):** Фаза 1 нормализует ПАРАЛЛЕЛЬНО — `ThreadPoolExecutor(min(8,n))` (ffmpeg I/O-bound, атомарный `.part`-per-file → безопасно). Модели грузятся раз на батч (не на звонок).

**GPU sequential:** в Фазе 2 GigaAM+pyannote КО-РЕЗИДЕНТНЫ (~5GB); `_unload_models()` выгружает ОБА в `finally` Фазы 2 — ДО Фазы 3 (LLM). Иначе 5GB + llama-server Qwen 9B Q8_0 (~10GB) > 12GB (RTX 3060) → OOM. Никогда ASR и LLM одновременно. LLM читает текст из БД, не аудио → удалённый wav ей не нужен.

**Флаги (configs/):** `features.yaml` = `enable_diarization` / `enable_llm_analysis` (Stage-1: оба false). `base.yaml` `pipeline:` = `remove_source_on_success` / `delete_normalized_after_transcribe` / `text_export_dir`.

---

## Diarization Failure Handling

**Rule:** IF diarization fails OR returns 0 segments:

1. **Mark all transcript segments** with `speaker=UNKNOWN`
2. **Set call metadata** `diarization_failed=true`
3. **Continue pipeline** — DO NOT stop or mark call as error
4. **LLM will still extract meaning** from undiarized text (analyses still run normally)

**Rationale:**
- Audio might be corrupted but still transcribable
- LLM can extract context even without speaker attribution
- User gets partial result instead of complete failure
- Diarization is "nice to have", not "must have" for analysis

**Implementation:**
```python
# In diarize/pyannote_runner.py
try:
    diarization = pyannote_runner.diarize(wav_path)
except Exception as e:
    logger.warning("Diarization failed: %s", e)
    diarization = []

# In role_assigner.py
if not diarization:
    for segment in segments:
        segment.speaker = "UNKNOWN"
    call_metadata["diarization_failed"] = True
    # Continue to LLM analysis
```

**Test case:** Call with corrupted audio (Whisper can still transcribe but Pyannote fails)
- Expected: Card generated with speaker=UNKNOWN but analysis still present
- Risk/summary/action items should be extracted from text alone

---

## Short Call Handling (< 50 chars)

**Rule:** If `len(transcript_text.strip()) < 50`:
- Skip LLM analysis entirely
- Create stub Analysis with:
  - `call_type="short"`
  - `priority=0`
  - `risk_score=0`
  - `summary=""`
  - No promises, flags, actions
- Mark in database as "analyzed" (don't retry)

**Rationale:** Avoids unnecessary LLM calls for noise/silence

---

## LLM Response Validation

**Rule:** After LLM response parsing:
1. Check `parse_status` value (see response_parser.py)
2. Log parse_status to database (`analyses.parse_status`)
3. If `parse_status="output_truncated"` → flag for manual review
4. If `parse_status="parse_failed"` → keep raw_response for debugging

---

## Enricher Progress Reporting

**Rule:** Enricher must log:
- Total calls to process
- Current call_id being processed
- Stage (transcribe/diarize/analyze/save)
- parse_status for each analysis (after parsing)
- Errors with full exception trace

This helps user monitor long-running batches and diagnose failures.

---

## Fallback Strategy

**Rule:** One file failure must NEVER block the entire batch.

| Stage | Failure | Action |
|-------|---------|--------|
| Audio normalization | Any exception | status=error, skip file, continue |
| Whisper | Any exception | status=error, skip file, continue |
| Diarization | Exception OR 0 segments | mark all segments speaker=UNKNOWN, continue pipeline |
| LLM request | Timeout / HTTP error | retry once; if still fails → save transcript without analysis, status=error |
| LLM JSON parse | parse_status=parse_failed | save raw_response, set parse_status=parse_failed, continue |

**Implementation pattern:**
```python
for call in calls:
    try:
        process_call(call)
    except Exception as e:
        logger.error("Call %s failed: %s", call.call_id, e, exc_info=True)
        repo.set_status(call.call_id, "error", error_message=str(e))
        continue  # never raise, never break
```
