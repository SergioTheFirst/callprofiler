# box-package — что запустить на боксе (R-01, R-16…R-28 плана)

> Всё здесь работает ТОЛЬКО на **копии** боевой БД. Ни один скрипт не открывает `C:\calls\data\db\
> callprofiler.db`; каждый принимает `--db` и отказывается работать, если путь указывает в `C:\calls\data`.
> Smoke-прогон на дев-ноутбуке: `python scripts/NN_*.py --synth` (строит мини-БД сам).

## 0. Подготовка бокса (один раз на сессию измерений)

1. Остановить `watch` и дашборд (открытые коннекты к БД).
2. `python -m callprofiler backup` → `python -m callprofiler verify-backup <файл>` (T-20 гейт).
3. Копия: `mkdir C:\calls\research` → `copy <backup.db> C:\calls\research\callprofiler-YYYYMMDD.db`.
   Все скрипты: `--db C:\calls\research\callprofiler-YYYYMMDD.db`.
4. Если `contact_reliability` ещё не существует в копии (до R-04/R-08 на боксе) — скрипты 04/05 строят
   оценку **в памяти** по тем же формулам (`--inline`), ничего не записывая в копию.
5. `llama-server` не нужен ни одному скрипту (все det/numpy). LLM-донасыщение исходов
   (`promise-outcomes --llm`) — отдельно, в LLM-окне, ДО копирования, если хочется больше разрешённых
   исходов (E-1 тогда измеряет и `q_llm`).
6. Запустить `watch` обратно только после окончания adjudication-сессии (копия от живой БД не зависит,
   но adjudication-request ссылается на `call_id`, которые должны существовать в дашборде для
   прослушивания — M2 audio player).

## 1. Порядок (соответствует R-01 → R-16 → R-18 → R-19 → R-21 → R-22 → R-23 → R-20 → R-27/28)

| Шаг | Команда | Результат | Правило решения |
|---|---|---|---|
| E-0a | `01_bs_dead_terms.py --db …` | `results/E0a.md`: распределение `event_type`, `MAX(bs_index)`, доля нулей | D1 подтверждён/опровергнут (см. `decision-rules.md` §E-0a) |
| E-0a | `02_promise_coverage.py --db …` | покрытие исходов по контактам, гистограмма n разрешённых | S-2: сколько контактов достигнут `limited/moderate` |
| E-0a | `03_role_quality.py --db …` | UNKNOWN-доля по звонкам, доля role_fragile среди звонков с обещаниями | E-9 вход; `w_role` режим |
| E-1/E-2 | `02_promise_coverage.py --db … --adjudication-request --seed 0 --n 30 --overdue 10` | `adjudication-request.md` (≤40 строк, рандомизировано, без CI/метода) | владелец заполняет колонку «исход» |
| E-1/E-2/E-3(1) | `04_cr_eval.py --db … --adjudicated adjudication-answers.csv` | `results/E1.md`, `E2.md`, `E3-stage1.md`: q/sens/spec по методу, sensitivity ±0.05, π_b vs π_r, reliability diagram, Brier, ECE_adapt+bootstrap | `decision-rules.md` §E-1/§E-2/§E-3 |
| E-8/E-4 | `05_temporal_holdout.py --db …` | `results/E8.md`, `E4.md` | §E-8/§E-4 |
| E-9 | `04_cr_eval.py --db … --adjudicated … --role-mode` | `results/E9.md` | §E-9 |
| E-3(2) | ежемесячно `04_cr_eval.py --db … --source outcome_feedback` | `results/E3-stage2-YYYYMM.md` | §E-3 стадия 2 |
| E-6 | `07_contradictions.py --db …` (после `graph-replay` на копии; 20 строк владельцу) | `results/E6.md` | §E-6 |
| E-7 | `08_hedge.py --db …` | `results/E7.md` | §E-7 |

## 2. Что нельзя
- Запускать скрипты против живой БД (гард в `_open_copy`).
- Менять правила решения после просмотра данных (они в `decision-rules.md`, версионируются git-ом).
- Показывать владельцу CI/метод/статус до его ответа (C-14; `adjudication-request.md` их не содержит).
- Отправлять что-либо из данных в сеть.

## 3. Файлы
`hypotheses.md` — H1…H9 с предсказаниями; `protocol.md` — выборки, split, bootstrap, множественные
сравнения, sensitivity к UNKNOWN; `decision-rules.md` — правила до данных; `adjudication-request.md` —
шаблон (заполняется скриптом 02); `scripts/` — 00…08; `results/` — создаётся на боксе.
