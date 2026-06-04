# CONTINUITY.md — Continuity Ledger

> Canonical session briefing; survives context compaction. Facts only, no transcripts.
> Pre-ledger history (2253 lines of session logs) preserved in git @ commit `702ec13` and earlier.
> Read this at the start of every turn; update when goal/constraints/decisions/state change.

**Goal (incl. success criteria):**
- Приоритет пользователя (2026-06-03): рабочий авто-pipeline `C:\calls\in` → текст (GigaAM v3 локально) → БД → LLM, с видимостью стадий в UI почти в реальном времени. Stage-1 (audio→текст в БД) — критично и срочно.
- Success: watcher берёт файлы из incoming, GigaAM транскрибирует, транскрипт в БД + `.txt`, LLM-анализ пишет analyses/events; стадии видны в dashboard.

**Constraints/Assumptions:**
- 100% local. Windows + system Python 3.10. LLM = llama-server @127.0.0.1:8080. SQLite, no ORM. Каждый запрос фильтрует `user_id`. Never swallow errors. GPU sequential: ASR (GigaAM) выгружается перед LLM.
- **Обработка идёт на ДРУГОЙ машине** (с transformers/torchaudio/ffmpeg/GPU). Моя задача — код; пользователь запускает на рабочей машине. В ЭТОЙ среде стоит только torch+numpy (нет transformers/torchaudio/pyannote/faster_whisper/ffmpeg) → реальный GigaAM-прогон здесь невозможен.
- `data_dir = C:\calls\data`. Direct push to `main`. No attribution footer.
- ASR: **flat text, без pyannote** (выбор пользователя). Роли (`[me]/[s2]`) — следующий шаг.

**Key decisions:**
- GigaAM = **локальная in-process** модель (`C:\models\GigaAM-v3-rnnt`), НЕ HTTP. `GigaAMRunner` переписан: своя нарезка окнами <25с, без `transcribe_longform`/pyannote (он gated). См. `.claude/rules/decisions.md`.
- Папки: **per-user дерево** (выбор пользователя). Один юзер `me`, `incoming_dir=C:\calls\in`. Архив = `users/{uid}/audio/originals/YYYY/MM` (ingester копирует). Исходник из `in` убирается watcher'ом после транскрибации.
- `.txt` транскрипт (явное требование) → `C:\calls\text\<имя_исходника>.txt`.
- Realtime UI = существующий dashboard (SSE+DB-poll) + per-stage `update_call_status`; живой лог — консоль `watch -v`.

**State:**

🟢 **СИСТЕМА ГОТОВА К ПРОДАКШН-ПРОГОНУ 17k** (2026-06-04, коммиты до 256002d). Готово:
чистый старт `reset.bat` (бэкап БД, защищает in/source); удаление normalized после stage 2
(`delete_normalized_after_transcribe:true`); pyannote 1 загрузка/чанк + чанки по 100 + телеметрия
off (OTEL_SDK_DISABLED+set_telemetry_metrics(False)); роли работают; дашборд real-time (все 8 стадий,
SSE 5с). LLM вкл (нужен поднятый llama-server — в `run-one.log` был parse_failed из-за выключенного
сервера). НЕ сделано (Фаза 2, на реальных данных): улучшение профилей (карточки/психо/биография/граф) —
вслепую = гадание, ждём данные. Bat'ы: sync-main/run-one/run-watch/reset/cleanup/diag.

✅ **РОЛИ РАБОТАЮТ END-TO-END НА БОКСЕ** (2026-06-04, `run-one.log`, call_id=19751 «Халит
Мухтарович», 23-мин звонок): ingest → normalize → диаризация (405 turn'ов, OWNER=SPEAKER_01,
sim=0.581) → GigaAM по turn'ам (403 сегмента) → `.txt` с ролями → done. Фиксы torchcodec-обход
(in-memory waveform) + `_extract_annotation` (DiarizeOutput 4.x) сработали. Коммиты a156acd, 82d2669.
ХВОСТЫ: (1) llama-server не запущен → LLM `parse_failed` (транскрипт/роли/карточка целы); (2) ⚠️
pyannote 4.x шлёт телеметрию на `otel.pyannote.ai` — нарушает «100% local», вырубить в коде.
Качество ролей (sim=0.581 — средняя) сверяем по `.txt`.

diag #5 (2026-06-04, `diag.txt`/`rez.txt`): ОКРУЖЕНИЕ НА БОКСЕ ГОТОВО — py3.12, torch
2.6.0+cu124, CUDA True (RTX 3060), ffmpeg в PATH, HF_TOKEN задан, pyannote.audio 4.0.4,
GigaAM грузится на GPU (load-test PASS). Прошлые env-блокеры (B1, install-roles) закрыты.
`test-all.bat` отработал чисто, но НОВЫХ файлов не было (единственный 1.mp3 — дубликат
уже транскрибированного → убран), т.е. путь ролей в этом прогоне не проверялся.

Исправлено этой сессией (НЕ закоммичено), оба покрыты тестами, suite 478 зелёных локально:
- **РОЛИ — найден истинный блокер = torchcodec.** pyannote 4.x декодирует WAV по пути через
  torchcodec, чьи DLL на Windows не грузятся → диаризация падала бы → роли UNKNOWN (ASR при
  этом работает: GigaAM на ffmpeg, не на torchcodec). Фикс: `pyannote_runner` подаёт аудио
  pyannote В ПАМЯТИ (`{waveform, sample_rate}`, soundfile+librosa) — torchcodec обойдён.
- **754 зависших в 'normalizing'@stage0** — `get_stalled_calls` фильтр `pipeline_stage>0`
  сиротил их; условие → `status NOT IN ('new','done','error')`.

Данные в БД (diag): 16645 done, 2349 error (retry-exhausted), 754 normalizing(stage0).
ВСЕ 92267 транскриптов — speaker=UNKNOWN (legacy: обработаны до фикса ролей). 2 юзера:
`me` (рабочий) и `serhio` (битый: все звонки error «файл не найден», incoming=C:\calls\audio).

Next:
- **Проверка ролей на боксе (главное):** капнуть НОВЫЙ по содержимому звонок в `C:\calls\in` →
  `process "<файл>" --user me --force -v`. В логе ждать «Диаризация: N turn'ов» + сегменты [me]/[s2]
  в `.txt`. Диаризация деградирует graceful: при сбое — роли UNKNOWN + ТОЧНАЯ причина в логе
  (одной строкой) → прислать её мне. Если в логе всё ещё всплывает torchcodec — значит soundfile
  не отработал, прислать трейс.
- **Чистка данных — РЕШЕНО, инструмент готов (`cleanup.py`/`cleanup.bat`, dry-run по умолчанию):**
  пользователь выбрал «удалить 2349 мёртвых error» + «снести юзера serhio». Прогнать НА БОКСЕ:
  `cleanup.bat prune-missing --user me` → проверить план → `... --apply`; затем
  `cleanup.bat purge-user --user serhio` → план → `... --apply`. FTS-safe, транзакция.
- Ручное на боксе (не код): удалить 0-байтный `C:\calls\data\callprofiler.db` (легаси, никто не
  пишет); `git` «dubious ownership at C:/» — проверить стрэй `C:\.git`, `git config --global
  --add safe.directory C:/pro/callprofiler`.
- Опц.: переобработать legacy-звонки, чтобы получить роли задним числом (после успешной проверки).
- Полный pytest на боксе: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`.
- `git add -A && commit && push origin main` (после согласования; на боксе сперва safe.directory).

**Open questions (UNCONFIRMED):**
- Совпадение версии `torchaudio` с `torch 2.6.0+cu124` на рабочей машине (ставить с cu124 index).
- `from_pretrained` weights_only на torch 2.6 — добавлен защитный патч в `GigaAMRunner.load()`; проверить на реальной загрузке.
- Качество нарезки окнами на стыках (раз в ~20с возможен разрез слова) — оценить на реальных звонках, при необходимости включить overlap или VAD.

**Working set (files/ids/commands):**
- Touched: `transcribe/{gigaam_runner,text_export}.py`, `pipeline/{orchestrator,watcher}.py`, `config.py`, `configs/{base,features}.yaml`, `cli/commands/admin.py`, `cli/main.py`, tests×3, `requirements-gigaam.txt`, `RUN_STAGE1.md`.
- Run tests (рабочая машина): `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/ -q`
- Last pushed commit: `67d950f` (main). Эта сессия + Фаза 4 ещё не закоммичены.
