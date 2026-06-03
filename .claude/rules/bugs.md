# Bugs & Ideas

## Known Bugs (Active)

### 🔴 High Priority

None currently identified.

### 🟡 Medium Priority

1. **FTS5 index not used in /search — FIXED** (2026-04-17)
   - **Issue:** `search_transcripts()` used `LIKE` O(n) scan; FTS5 table existed but was never queried
   - **Fix:** Replaced with FTS5 MATCH subquery + BM25 ranking + LIMIT 50
   - **Status:** RESOLVED (2026-04-17)

2. **.bat file encoding** (2026-04-14)
   - **Issue:** new-session.bat, save-session.bat might have BOM on Windows
   - **Fixed:** Converted to ASCII encoding (no UTF-8 BOM)
   - **Status:** RESOLVED - removed BOM from all .bat files

3. **Telegram bot long-polling stability** (2026-04-11)
   - **Issue:** If bot process dies, notifications are lost (no message queue)
   - **Impact:** User misses real-time summaries during call processing
   - **Solution:** Implement in-memory buffer with crash recovery
   - **Status:** BACKLOG (Phase 6 optimization)

### 🟢 Low Priority / Ideas

1. **Contact card text truncation** (2026-04-11)
   - **Observation:** Card text limited to 512 bytes - some info may be cut
   - **Idea:** Implement card versioning (short vs. full) based on user preference
   - **Status:** IDEA - gather user feedback first

2. **Risk emoji scale clarity** (2026-04-14)
   - **Observation:** 🟢<30, 🟡 30-70, 🔴>70 thresholds are arbitrary
   - **Idea:** Calculate thresholds from historical data (percentiles across all contacts)
   - **Status:** IDEA - needs data collection first

3. **Promises deadline warnings** (2026-04-11)
   - **Idea:** /promises command should highlight overdue promises (deadline < today)
   - **Implementation:** Add formatting (emoji/bold) for overdue items
   - **Status:** BACKLOG - easy, low priority

4. **Contact relationship graph** (2026-04-14)
   - **Idea:** /contact command could show "mentioned Vasya in 3 calls" (person->person links)
   - **Requires:** NER (Named Entity Recognition) in LLM analysis
   - **Status:** FUTURE (Phase 8 analytics)

5. **Multi-language support for commands** (2026-04-14)
   - **Observation:** Telegram commands are hardcoded (/start, /digest, etc)
   - **Idea:** Allow Russian aliases (/дайджест, /поиск) for user convenience
   - **Status:** IDEA - low value, high complexity

6. **Call recording integration** (2026-04-09)
   - **Observation:** Currently system waits for user to copy audio files to incoming_dir
   - **Idea:** Direct integration with Android recorder (auto-upload when call ends)
   - **Requires:** Mobile app + backend API
   - **Status:** FUTURE (Phase 7 scale)

7. **CRM integration** (2026-04-14)
   - **Idea:** Sync contact names from Salesforce/HubSpot, not just from call filenames
   - **Benefits:** Better name accuracy, company context, deal tracking
   - **Status:** FUTURE (Phase 9 integration)

8. **LLM fine-tuning** (2026-04-14)
   - **Idea:** Fine-tune Ollama model on user's past calls for better extraction
   - **Benefits:** Better context understanding, personalized risk scoring
   - **Requires:** 50+ calls minimum for fine-tuning
   - **Status:** FUTURE (Phase 10 intelligence)

---

## Bug Report Template

```markdown
### Title
- **Issue:** Clear description
- **Impact:** Who/what is affected
- **Reproduction:** Steps to reproduce
- **Expected:** What should happen
- **Actual:** What happens instead
- **Solution:** Proposed fix (if known)
- **Status:** ACTIVE / RESOLVED / BACKLOG / IDEA
- **Date Found:** YYYY-MM-DD
- **Priority:** 🔴 High / 🟡 Medium / 🟢 Low
```

---

## Recent Fixes (Closed)

✅ **Stage-1 GPU-прогон: 7 проблем из rez.txt** (2026-06-03)
- **B1 (env, не код):** бокс на Python 3.14 → PyTorch не даёт CUDA-колёс (только torch 2.12+cpu) → GPU простаивает, GigaAM в 20-50× медленнее. Fix: Python 3.12 + torch==2.6.0+cu124 + torchaudio==2.6.0 + transformers<5. На 3.12 патчи A/B (см. rez.txt) не нужны. Зафиксировано в `requirements-gigaam.txt`/`RUN_STAGE1.md`.
- **B2:** `orchestrator` инстанцировал `PyannoteRunner` на старте → лишняя связанность для Stage-1. Fix: lazy в `_diarize_segments`, `self.pyannote_runner=None` в `__init__`, guard в finally.
- **B3:** `process_call()` не писал `pipeline_stage` (в отличие от `process_batch`) → нет видимости/cleanup. Fix: stage 1→4 добавлены.
- **B4/B5 (потеря данных):** watcher удалял исходник дубликата из incoming БЕЗ проверки, что звонок реально транскрибирован → error/завис терял исходник. Fix: `_scan_user_dir` MD5-first через `repo.get_call_by_md5()`, удаление только при `pipeline_stage>=2`. Regression: `tests/test_watcher_cleanup.py::test_scan_keeps_untranscribed_duplicate` + `::test_scan_removes_transcribed_duplicate`.
- **B6:** `prompts_dir` резолвился от `data_dir` (`C:\calls\configs\prompts` — не существует) в 3 местах. Fix: `Config.prompts_dir` от корня проекта.
- **B7:** dashboard не стартовал — `__init__` импортировал несуществующие `app`/`set_user_id`; `DashboardDBReader` получал каталог вместо `.db`. Fix: фабрика `server._build_app()`, db_reader резолвит `data_dir/db/callprofiler.db`.
- **Status:** RESOLVED (код), B1 — требует Python 3.12 на боксе.

✅ **Diarization exception lost transcript + leaked VRAM** (2026-05-30)
- **Issue:** In `orchestrator.py` (`process_call` & `process_batch`), if `pyannote.diarize()`/`load()` threw, `save_transcripts()` was skipped (Whisper transcript lost) AND `pyannote_runner.unload()` was skipped (VRAM leaked before the ~10GB LLM phase → OOM risk). Violated `.claude/rules/pipeline.md` (continue with speaker=UNKNOWN) + CONSTITUTION Ст.9.3.
- **Found by:** strategic audit (2026-05-29), verified by reading `orchestrator.py:294-305`.
- **Fix:** extracted `Orchestrator._diarize_segments()` — try/except → return UNKNOWN segments on failure, `finally: unload()`. Both call sites rewired (de-duplicated). Transcript always saved; GPU always freed.
- **Companion fix:** `normalizer.py` ffmpeg/ffprobe presence check moved from import-time to call-time (`_require_ffmpeg()`), so the package is importable without ffmpeg (`config._validate()` still fail-fasts at startup). Unblocked the first orchestrator-level unit test.
- **Regression tests:** `tests/test_regressions.py::test_diarization_failure_keeps_transcript_and_frees_gpu`, `::test_diarization_disabled_returns_segments_without_loading`. Suite 414/414. Code-review: clean.
- **Status:** RESOLVED (2026-05-30)

✅ **BOM in .bat files** (2026-04-14)
- Removed UTF-8 BOM from all batch files
- Converted to ASCII encoding for Windows compatibility

✅ **Missing Memory Protocol** (2026-04-14)
- Added 6-rule Memory Protocol to CLAUDE.md
- Ensures AI session continuity via journals

✅ **Missing automation scripts** (2026-04-14)
- Created new-session.bat, save-session.bat, emergency-save.bat
- Provides Windows-friendly workflow

---

## Statistics

| Category | Count |
|----------|-------|
| Active Bugs | 3 |
| Resolved | 4 |
| Ideas/Backlog | 5 |
| Future Phase Items | 3 |
| **Total** | **14** |

**Burn Rate:** 3 issues fixed in Phase 5 (audit focus). Ready for Phase 6 (optimization).
