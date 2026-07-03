# Age Ensemble v2 — ревизия системы определения возраста (2026-07-03)

> Исполнители: Sonnet-субагенты (задачи B и C ниже). Задача A = `fixager.md` Ф1-Ф5 (отдельный документ).
> Архитектор: Fable (T3). Методология-источник: `vozrast.md`; карта слоя: `.claude/rules/insight.md`.
> Констрейнты: НИКАКОГО ML/обучения/эмбеддингов/внешних сервисов. numpy+regex+лексиконы. Каждый SQL — `WHERE user_id=?`.

## Итог аудита (что легло в основу v2)

**Реализовано верно:** маркер-система (direct/stage/relation/LLM, birth-year space, классы точности),
style-MVP (ch6/diversity/slang/archaism/i_ratio/vy_ratio/life_stage/realia, линейный пул, z-внутри-популяции,
sanity/confidence/edge-bonus), интеграция в досье.

**Баги (закрывает задача A = fixager Ф1-Ф5):** P1 startswith-омонимы; P2 support_n=корпус (life_stage/realia);
P3 z по stale-подвыборке; P4 ложно-узкий интервал; P5 маркеры без гардов («выйду на пенсию», «у дочки ЕГЭ»);
P6 обвал conf от мусорного низшего класса.

**Найдено сверх fixager (закрывают задачи B/C):**
1. `_density` (slang/archaism) тоже возвращает `support_n=len(norm)` → 1 хит = полный вес (та же болезнь, что P2).
2. Третье-личные упоминания жизненных этапов ВЫБРАСЫВАЮТСЯ, хотя несут сильный сигнал о возрасте контакта
   («у дочки ЕГЭ» ⇒ контакту 36-58, а не «отбросить»). Ансамблю нужен kin-класс (арифметика родства).
3. Прямые маркеры покрывают мало форм: нет «я с 75-го года», «школу закончил в 95-м», «мне сорокет/полтинник»,
   «мне под/за сорок», «армия в 99-м» — это класс-3/класс-2 сигналы, почти бесплатные.
4. Реалии: 14 записей, эпохи проставлены грубо (пейджер = 1930-1975 — неверно; пик пейджеров 1995-2000 ⇒
   рождённые ~1960-1982). Нужна пере-датировка через «reminiscence bump» (артефакт популярен в год Y ⇒
   носители тогда 10-30 лет ⇒ рождение Y-30..Y-10) + расширение.
5. Не реализованы дешёвые сильные оси: дискурс-маркеры-репертуар (Д4: «типа/короче» vs «значит/понимаешь»),
   канцелярит (Л6), служебная морфосинтаксика по закрытым спискам (М3 предлоги + С3 подчинит. союзы — pymorphy НЕ нужен),
   темп речи из start_ms/end_ms (слов/сек ↓ с возрастом — Jacewicz 2009, Quené 2008).
6. Нет популяционного приора: телефонные контакты взрослого владельца ≈ G3-G5; равномерный приор раздувает G1/G2 от мусора.
7. Нет ЕДИНОЙ итоговой оценки: marker-таблица и style-таблица живут раздельно, дашборд показывает две цифры.
   Нужен fusion-слой (детерминированный, версионированный, read-time — без новой таблицы и без циклов чтения самого себя).
8. Лексикон-матчер не умеет биграммы и точные формы ЧАСТИЧНО (fixager Ф1 вводит `=`); биграммы («ласковый май»,
   «по блату», «стало быть», «как бы») нужны трём лексиконным осям.

## Архитектура v2 (ансамбль независимых оценщиков)

```
КЛАСС 3 (факт):     direct_age, birth_year, jubilee, year-anchored events (new)
КЛАСС 2 (этап):     pension/grandkids/army/student/school (с гардами A) + KIN-арифметика (new)
КЛАСС 1 (якорь):    relation-якоря относительно владельца (сущ.)
КЛАСС 0 (LLM):      сущ., без изменений
STYLE (фон):        линейный пул: prior + ch6 + diversity + slang + archaism + i_ratio + vy_ratio +
                    life_stage + realia + discourse(new) + kancelyarit(new) + morphosyntax(new) + tempo(new)
FUSION (read-time): fuse_age(marker_row, style_row) → единая оценка профиля (FUSION_VERSION)
```
Классы 3-0 живут в marker-системе (`age_markers.py`/`age_estimate.py` → `contact_age_estimates`).
STYLE живёт в `age_style/` → `contact_age_style`. FUSION — чистая функция, зовётся из db_reader/CLI.
Устойчивость к отсутствию признаков: пул пропускает отсутствующие голоса; fusion работает при любом
подмножестве слоёв; при полном отсутствии — честное «нет данных».

---

# ЗАДАЧА B — маркеры-v2 + стиль-v2 (Sonnet, после задачи A)

Файлы: `src/callprofiler/insight/age_markers.py`, `age_estimate.py`, `age_style/{lexicons.py,tables.py,weights.py,scorer.py,estimate_style.py}`,
`insight/features/{lexical_age.py,discourse_age.py(new),tempo_age.py(new),morphosyntax_age.py}`,
`age_style/lexicons/*.txt` (+3 новых), тесты `tests/insight/`.
Прогон после каждого блока: `$env:PYTHONPATH="C:\pro\callprofiler\src"; python -m pytest tests/insight tests/test_dashboard_age_style.py -q`.

## B1. Биграммы в лексикон-матчере

`age_style/lexicons.py::load_lexicon` уже возвращает строки с `=`-префиксом (после задачи A).
Добавить поддержку записей с пробелом: стем из двух слов = биграмма. Единый матчер положить в
`features/lexical_age.py`:

```python
def lexicon_hits(tokens_norm: list[str], stems: tuple[str, ...]) -> int:
    # unigram: '=точная' → token == 'точная'; 'стем' → token.startswith
    # bigram:  'ласковый май' / '=стало быть' → пара соседних токенов (обе части точные)
```
Биграммные стемы матчятся ТОЧНО по обеим частям (независимо от `=`). Все density-функции и
life_stage/realia переводятся на `lexicon_hits`/его пер-стемовый вариант (нужен distinct-stem счёт из задачи A).

## B2. support_n = хиты для slang/archaism (закрыть найденное #1)

`lexical_age._density`: вернуть `Feature(hits*1000/len(norm), support_n=hits, ...)`.
`weights.SUPPORT_N0`: `slang: 3`, `archaism: 3` (полный вес от 3 хитов). `SUPPORT_FLOOR=2` в scorer
теперь отсекает одиночный ироничный хит — это желаемое. Отсутствие (raw=0, support 0) → голос не подаётся
(роль «нейтрального фона» переходит к prior-голосу B7). Обновить тесты, проверявшие «нет» строку slang
при hits=0 — теперь голоса нет вообще.
z-параметры slang/archaism в `estimate_style._score_and_save`: строка `zval = ... if f.support_n > 0 else None`
остаётся верной (support теперь хиты).

## B3. Маркеры-v2 (`age_markers.py`)

Все новые regex — OTHER-only (вызываются из существующего `extract_marker_signals`), с `_third_person`-гардом
и диапазоном рождения 1930-2015. Двузначный год: `NN>=30 → 1900+NN, иначе 2000+NN`.

Новые прямые (класс 3, добавить в `_PRIORITY`):
| signal | regex (суть) | вывод | conf |
|---|---|---|---|
| `born_in` | `я\s+родил(?:ся|ась)\s+в\s+(\d{2,4})(?:-м)?\s*(?:году)?` | birth=year точно | 92 |
| `since_year` | `я\s+(?:с\s+)?(\d{2})(?:-го)?\s+года\b(?!\s+(?:работа\|живу\|начал\|учусь\|служу))` + требовать `рожден`-контекст ИЛИ отсутствие глагола занятости в +20 симв. Без «рожден» → conf 78 | birth=year | 78/92 |
| `age_slangnum` | `мне\s+(тридцатник\|сорокет\|сороковник\|полтинник\|полтос\|шестьдесят\s+стукнуло)` + `(стукнул\|исполнил)?` | возраст из словаря {тридцатник:30, сорокет:40, сороковник:40, полтинник:50, полтос:50} | 80 |
| `age_approx` | `мне\s+(?:уже\s+)?(?:под\|за\|к)\s+(тридцать\|сорок\|пятьдесят\|шестьдесят\|семьдесят)` | «под N»→[N-3,N-1]; «за N»→[N+1,N+9]; «к N»→[N-3,N-1] | 65 |

Год-якорные события (класс 2, `_PRIORITY`=2), формат: событие в году Y при возрасте [alo,ahi] ⇒ birth=[Y-ahi, Y-alo]:
| signal | regex (суть) | возраст | conf |
|---|---|---|---|
| `school_finish_year` | `школу\s+(?:за\|о)конч\w+\s+в\s+(\d{2,4})` | 16-18 | 80 |
| `uni_enter_year` | `поступ\w+\s+(?:в\s+\w+\s+)?в\s+(\d{4})` с контекстом инстит/универ/вуз/академ в ±30 | 16-19 | 70 |
| `uni_finish_year` | `(?:за\|о)конч\w+\s+(?:институт\|универ\w*\|вуз\|академи\w+)\s+в\s+(\d{2,4})` | 21-24 | 70 |
| `army_year` | `(?:в\s+армию\s+(?:пошел\|пошёл\|призвали\|забрали)\|служил)\s+в\s+(\d{2,4})` | 18-20 | 70 |

Гарды: год события 1945-текущий; вычисленный birth в 1930-2015, иначе сигнал не создаётся.

## B4. KIN-арифметика (новый класс 2, `age_markers.py::extract_kin_signals`)

Вход: `contact_lines` (OTHER). Сигналы О СВОИХ родных контакта → возраст контакта через смещение.
Гард «свои»: перед kin-словом в −25 симв. НЕТ `тво|ваш|у\s+тебя|у\s+вас` (чужие родные — пропуск).

| signal | паттерн | арифметика | conf |
|---|---|---|---|
| `kin_child_age` | `(?:доч\w*\|сын\w*)\s*(?:у меня\s*)?.{0,12}?\b(\d{1,2})\s*(?:лет\|год\w*)\b` и зеркально `(доч\|сын)\w*\s+(\d{1,2})` — брать вариант «(дочке\|сыну)\s+(\d{1,2})(\s*(лет\|год))?» | ребёнку A (1≤A≤45) ⇒ контакт = A+[20..40] ⇒ birth=[Y-A-40, Y-A-20] | 60 |
| `kin_child_stage` | kin-слово (доч/сын/реб(ё\|е)нк/дет(и\|ей\|ям)) в −30 симв. перед этап-матчем: садик/детсад⇒реб.2-7; школ/урок⇒7-17; ЕГЭ/11 класс/выпускн⇒16-18; универ/сесси/поступ⇒17-23 | контакт = реб.возраст+[20..40] | садик 55; школа 55; ЕГЭ 60; вуз 55 |
| `kin_parent_age` | `(?:мам\w*\|пап\w*\|отц\w*\|матер\w*)\s*.{0,10}?\b(\d{2})\s*(?:лет\|год\w*)` (50≤A≤99) | родителю A ⇒ контакт = A−[18..40] ⇒ birth=[Y-A+18, Y-A+40] | 55 |
| `kin_grandchild` | (внук/внучк + садик/школ/выпускн/родил в ±30) | ⇒ контакт 50-85 (эквивалент существующего grandkids) | 60 |

Реализация: пройтись regex-ами по тексту реплики; связка «kin-слово ↔ этап/возраст» — по окну ±30 символов.
`_PRIORITY`: все `kin_*` → 2. Метод `marker`. Вызывать из `run_age_estimate` рядом с `extract_marker_signals`
(добавить `signals.extend(extract_kin_signals(text, dt))` в том же цикле — сигнатура `(text, call_dt)`).
ВАЖНО: этап-маркеры self (`_STAGES`) после задачи A уже НЕ срабатывают на kin-контекст (гарды P5) —
двойного счёта нет; kin-путь подхватывает то, что self-путь отбросил.

## B5. Style: новые оси

### B5.1 Дискурс-репертуар (Д4)
Новые лексиконы `age_style/lexicons/fillers_young.txt` и `fillers_old.txt` (формат — 1 колонка, `=`/биграммы):
```
# fillers_young.txt
=типа
=короче
=жесть
=капец
=пипец
=прикинь
=реально
как бы
=походу
=блин
# fillers_old.txt
=значит
=понимаешь
=понимаете
стало быть
так сказать
=собственно
=соответственно
=допустим
=стало
вот именно
=нынче
```
(«=стало» убрать — омоним глагола; НЕ включать. «=реально» — спорно, оставить: пик у 18-35.)
`features/discourse_age.py::filler_repertoire(tokens_norm) -> Feature`:
`young = lexicon_hits(young_stems)`, `old = lexicon_hits(old_stems)`; total = young+old;
если total < 3 → `Feature(0.0, 0, ROBUST)` (нет голоса); иначе `Feature(young/total, total, ROBUST)`.
Таблица `discourse` (3 бина по RAW-доле, z не нужен): `молодой` (share>0.65), `смешанный` (0.35..0.65), `старший` (share<0.35):
```
молодой:   .25 .32 .22 .12 .06 .03
смешанный: .16 .18 .19 .18 .16 .13
старший:   .03 .06 .12 .22 .30 .27
```
Вес `discourse: 0.55`, tier ROBUST, `SUPPORT_N0: 6`.

### B5.2 Канцелярит (Л6)
`age_style/lexicons/kancelyarit.txt`:
```
осуществл
вышеуказанн
нижеподписавш
надлежащ
целесообразн
непосредственн
=ввиду
вследстви
посредством
=зачастую
=таковой
=таковых
уведомл
ходатайств
регламент
```
`kancelyarit_density` в `lexical_age.py` (реюз `_density`). Таблица однонаправленная вверх (как archaism):
```
нет:       .17 .19 .19 .18 .15 .12
умеренная: .02 .06 .16 .28 .30 .18
высокая:   .01 .04 .12 .28 .33 .22
```
Вес 0.50, ROBUST, SUPPORT_N0=4, контекст-модуляция: `context_mod` при business-теме → 0.6 (профессия перебивает).
Голос через `_onedirectional_vote` (id `kancelyarit`).

### B5.3 Морфосинтаксика по закрытым спискам (М3+С3, один голос `morphosyntax`)
`features/morphosyntax_age.py` дополнить:
```python
_PREPS = {"в","на","с","по","за","из","у","о","об","обо","при","для","без","до","через",
          "между","над","под","перед","около","среди","против","вокруг","вдоль","возле",
          "ради","сквозь","благодаря","вопреки","согласно","насчет","ввиду","вследствие"}
_SUBORD = {"чтобы","потому","поскольку","хотя","однако","впрочем","причем","причём",
           "который","которая","которые","которых","если","когда","пока","дабы","ибо"}
_COORD = {"и","а","но","или","либо","да","тоже","также","зато"}
def preposition_share(tokens) -> Feature   # preps/len(tokens), support=len(tokens), IMMUNE
def subordination_ratio(tokens) -> Feature # subord/(subord+coord), support=subord+coord, ROBUST
```
В `estimate_style`: оба идут в z-матрицу (`_Z_SCALAR_IDS` + `_SCALAR_FEATURE_FNS`), в scorer — ОДИН
объединённый голос (как `_diversity_vote`): средний z двух осей → 3-бин таблица `morphosyntax` (мягкая, ↑ с возрастом):
```
низкая:  .22 .24 .21 .15 .11 .07
средняя: .14 .18 .20 .19 .16 .13
высокая: .07 .11 .16 .22 .24 .20
```
Вес `morphosyntax: 0.50`. SUPPORT_N0: preposition_share 30, subordination_ratio 6, morphosyntax 30.

### B5.4 Темп речи (слов/сек из таймстампов)
`_gather_contact`: SELECT добавить `t.start_ms, t.end_ms`; собрать для OTHER-сегментов
`(n_tokens_сегмента, dur_ms)`. `features/tempo_age.py::words_per_sec(seg_stats) -> Feature`:
суммарно tokens/сек по сегментам с `0 < dur_ms <= 300_000`; support = число валидных сегментов;
`Feature(rate, n_segments, FRAGILE)`. В z-матрицу (id `tempo`). Голос: 3-бин z-таблица `tempo`
(↓ с возрастом — медленнее речь у старших; z<−0.5 = «медленный»):
```
быстрый:   .22 .26 .22 .15 .10 .05
средний:   .16 .18 .19 .18 .16 .13
медленный: .05 .09 .15 .20 .26 .25
```
Вес `tempo: 0.50`, tier FRAGILE (×0.4 — зависит от качества сегментации), SUPPORT_N0=10.

### B5.5 Популяционный приор
В `score_contact` первым голосом всегда: `votes.append(("prior", PRIOR_WEIGHT, PRIOR_DIST))`,
`PRIOR_DIST = {"G1":.01,"G2":.07,"G3":.22,"G4":.28,"G5":.28,"G6":.14}` в `tables.py` (+assert Σ=1),
`PRIOR_WEIGHT = 0.25` в `weights.py`. Обоснование: vozrast.md §2.3 «G1 почти отсутствует и служит
поглотителем» — приор реализует это явно; гасит ложные G1/G2. `contributions["prior"]` писать.
`style_only` для marker_conflict считается ВКЛЮЧАЯ prior (он часть стиля).

## B6. Пере-датировка и расширение реалий (`realia_by_epoch.txt`)

Заменить содержимое (принцип reminiscence bump: артефакт пика года Y ⇒ рождение [Y-30, Y-10]):
```
# Т2 — поколенческие реалии. стем<TAB>birth_low<TAB>birth_high. `=`=точная форма, пробел=биграмма.
перестройк	1930	1978
=талоны	1930	1978
сберкнижк	1930	1975
=патефон	1930	1960
=авоська	1935	1975
октябрен	1930	1978
=комсомол	1930	1975
=комсомоле	1930	1975
пионерлагер	1930	1980
дискотек	1945	1980
кассетник	1950	1985
видеомагнитофон	1955	1988
=видик	1958	1990
пейджер	1960	1982
дискет	1965	1990
ласковый май	1968	1980
=денди	1980	1992
=сега	1980	1992
=тамагочи	1984	1994
=аська	1975	1995
=аське	1975	1995
=асе	1975	1995
icq	1975	1995
тикток	1990	2012
=твич	1987	2008
аниме	1982	2008
=стрим	1985	2008
=стримы	1985	2008
```
(записи «кассет», «диал», «тату», «ласковый», «талон» одиночные — УДАЛЕНЫ; «=талоны» — точная форма мн.ч.)
`realia_birth_year` (после задачи A уже с гейтом ≥2 хитов): добавить требование ≥2 РАЗНЫХ стемов
доминирующей эпохи (симметрично life_stage). При голосе — вернуть также hits для честного support
(если задача A выбрала вариант без смены сигнатуры — оставить фикс. support=10, пометить `# ponytail:`).

## B7. Обновления scorer/estimate_style/weights (сводно)

- `_SCALAR_FEATURE_FNS` += `preposition_share`, `subordination_ratio`, `tempo` (tempo считается отдельно от tokens —
  через seg_stats, прокинуть из `_gather_contact` через `per_contact_extra` и добавить в матрицу вручную, либо
  расширить `_raw_features(tokens, other_segments, seg_stats)`).
- `_Z_SCALAR_IDS` += `prep_share`, `subord_ratio`, `tempo`.
- scorer: новый `_morphosyntax_vote` (аналог `_diversity_vote`), голоса `discourse` (по raw), `kancelyarit`
  (onedirectional), `tempo` (3-бин z, ВНИМАНИЕ: инверсия не нужна — таблица уже написана по бинам
  быстрый/средний/медленный: быстрый = z>0.5), `prior` (всегда).
- `BASE_WEIGHTS`/`FEATURE_TIER`/`SUPPORT_N0` — новые id.
- `TABLE_VERSION = "age-style-v2"`, `RULES_VERSION = "age-rules-v2"` (один бамп в конце задачи B).
- `__main__`-ассерт таблиц покрывает новые таблицы автоматически (TABLES + PRIOR_DIST отдельно).

## B8. Тесты задачи B (`tests/insight/`)

- `test_age_markers_v2.py`: born_in/since_year (+гард «с 2005 года работаю» → 0 сигналов), school_finish_year
  («школу закончил в 95-м» → birth 1977-1979), age_slangnum, age_approx («мне под сорок» → возраст 37-39).
- `test_age_kin.py`: «у дочки скоро ЕГЭ» → kin_child_stage birth≈[Y-58,Y-36]; «сыну тридцать» → kin_child_age;
  «маме восемьдесят пять» → kin_parent_age; «у твоей дочки ЕГЭ» → 0 сигналов; «дочке пять лет» → kin_child_age;
  агрегатор: kin (класс 2) проигрывает прямому «мне 45» (класс 3) без обвала conf (после задачи A).
- `test_age_discourse.py`: young-профиль («типа короче жесть капец») → share>0.65; old
  («значит понимаешь так сказать») → <0.35; <3 хитов → support 0.
- `test_age_tempo.py`: синт-сегменты 3 слова/сек vs 1.2 слова/сек → rate различим; dur=0 сегменты пропущены.
- `test_age_morphosyntax.py`: пред-лог-насыщенный текст → prep_share выше; support-контракты.
- `test_age_prior.py`: пустые фичи (нет голосов) → пул == PRIOR_DIST (не uniform).
- `test_age_realia_v2.py`: «пейджер… дискета…» (2 разных стема) → интервал пересечения эпох 1965-1982;
  одиночный «пейджер» → None; «ласковый май» биграмма → эпоха 1968-1980, а «ласковый голос» → None.
- Обновить существующие тесты, сломанные сменой support-семантики slang/archaism (ожидаемо).

DoD задачи B: `pytest tests/insight tests/test_dashboard_age_style.py -q` зелёный; новые тесты зелёные;
никаких новых зависимостей; лексиконы — данные.

---

# ЗАДАЧА C — Fusion + Dashboard «Пересчитать возраст» (Sonnet, после B)

Файлы: `src/callprofiler/insight/age_fusion.py` (NEW), `dashboard/db_reader.py`, `dashboard/tools.py`,
`dashboard/server.py` (если нужно), `static/app.js`, `templates/index.html` (если нужно),
тесты `tests/insight/test_age_fusion.py`, `tests/test_dashboard_age_style.py`.
Сначала выполнить fixager.md Ф6 (пункты 6.1-6.5) КАК НАПИСАНО, затем поверх — эта задача.

## C1. `insight/age_fusion.py` — единая итоговая оценка (чистая функция, без БД)

```python
FUSION_VERSION = "fuse-v1"

def fuse_age(marker: dict | None, style: dict | None, reference_year: int) -> dict | None:
    """marker: строка contact_age_estimates (dict c method, birth_year_low/high/point, confidence, evidence).
    style: строка contact_age_style (dict c birth_low/high/point, confidence, confidence_level, group_dist...).
    → {'age_point','age_low','age_high','birth_point','birth_low','birth_high',
       'confidence','source','warnings',[...]} | None."""
```
Правила (детерминированные, по убыванию точности; vozrast.md §4.6 «явное сильнее неявного»):
1. `marker` валиден, если `method in ('marker','relation','combined')` и `birth_year_low/high` не NULL.
   `llm`-строка (method='llm' с непустым birth_*) — тоже вход, но помечается слабой (conf capped 50).
2. `style` валиден, если `birth_point` не NULL и `confidence_level >= 2`.
3. Оба валидны:
   - пересечение интервалов непусто → интервал = marker-интервал (НЕ сужать по стилю — стиль шумный),
     `confidence = min(95, marker_conf + 5)`, source='marker+style'.
   - нет пересечения → интервал/точка от marker, `confidence = max(20, marker_conf - 10)`,
     warnings += 'стиль расходится с маркером', source='marker'.
4. Только marker → как есть, source='marker' (или 'llm' при llm-методе, conf cap 50).
5. Только style → его интервал/точка, `confidence = min(style_conf, 70)` (стиль без факта не бывает
   увереннее 70), source='style'.
6. Ни одного → None.
Возраст: `age_* = clamp(reference_year - birth_*, 0, 105)` (age_low из birth_high и наоборот).
Тесты C-теста покрывают все 6 ветвей.

## C2. Дашборд читает fusion

- `db_reader.get_person_dossier`: собрать `fused = fuse_age(age_row, age_style_row, current_year)` и
  положить в `d["age_fused"]`. Существующие `d["age"]`/`d["age_style"]` НЕ трогать (детализация).
- `db_reader.get_people`: колонка возраста в списке — из fusion (заменить текущий fallback-каскад
  marker→style на единый вызов fuse_age; `age_source` = fused['source']; серым при conf<50 — сохранить).
  Guarded: нет таблиц → None (паттерн `_has_table` сохранить).
- `app.js` досье: заголовочная строка возраста — из `d.age_fused` («~48 лет (41-55) · уверенность 62/100 ·
  источник: маркер+стиль»), под ней существующие секции маркеров и стиля как детализация.

## C3. Кнопка «Пересчитать возраст»

Поверх fixager Ф6 (маркер-пасс контакта + полный style-пасс, hint про owner_birth_year, кнопка всегда видна):
- Текст кнопки: `Пересчитать возраст ↻` (title: «полный пересчёт: маркеры этого контакта + стилометрия всей
  популяции; без LLM»). Это ЕДИНСТВЕННОЕ отличие от Ф6-нейминга.
- Ответ эндпоинта дополнить `"age_fused"` (посчитать fuse_age от свежих строк) — фронт обновляет заголовок
  без повторного GET досье (если обработчик уже перезагружает досье целиком — оставить перезагрузку, поле
  в ответе всё равно добавить для CLI/тестов).
- P9-диагностика: если у контакта есть звонки, но 0 OTHER-реплик (все UNKNOWN) — в ответ
  `"hint_diarization": "реплики контакта не размечены (UNKNOWN) — стилометрия невозможна, только маркеры/LLM"`;
  app.js показывает под кнопкой (muted). Определять дёшево: `stats["skipped_no_data"] > 0` при
  `contact_id`-пут° ИЛИ прямой COUNT по transcripts этого контакта со speaker='OTHER' (один SQL с user_id).

## C4. Тесты задачи C

- `tests/insight/test_age_fusion.py`: 6 ветвей C1 + clamp возрастов + llm-cap.
- `tests/test_dashboard_age_style.py`: `test_dossier_age_fused_present` (сеем marker+style строки → dossier
  содержит age_fused c source='marker+style'); `test_people_age_from_fusion`; `test_recompute_returns_fused`;
  `test_recompute_hint_diarization` (звонок только с UNKNOWN-репликами).
- Полный прогон: `python -m pytest tests/ -q` зелёный.

DoD задачи C: единая оценка в списке и в досье; кнопка запускает полный пересчёт (маркеры+стиль) и
возвращает fused; все hints работают; LLM из дашборда не вызывается.

---

# Порядок и верификация

```
A (fixager Ф1-Ф5, Sonnet) → B (Sonnet) → C (Sonnet) → code-review (Sonnet) → архитектор: независимая
проверка ключевых формул + полный pytest → бамп-фиксация (TABLE/RULES v2 уже в B; FUSION v1 в C) →
память (insight.md, CONTINUITY, CHANGELOG) → commit+push.
```
Замечание для всех задач: dev-ПК без БД/GPU — всё тестируется офлайн (synth/tmp sqlite);
не добавлять зависимостей; не трогать LLM-пасс и схему `contact_age_estimates`.
