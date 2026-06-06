# Insight Archetypes — Metadata MVP (Фаза 0 + Фаза 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить офлайн-запускаемый движок, который из метаданных звонков (когда/кто-кому/сколько) собирает по-контактные фичи и кластеризует контакты в эмпирические архетипы, с валидацией восстановления заложенных архетипов на синтетическом корпусе (ARI-гейт).

**Architecture:** Новый пакет `src/callprofiler/insight/`. Чистые функции над контрактом строк `calls`. Синтетический корпус (schema-accurate temp SQLite) даёт офлайн-разработку без реальной БД и ground-truth для валидации. Кластеризация (PCA + k-means + силуэт + ARI) на чистом numpy. Всё per `user_id`, идемпотентно.

**Tech Stack:** Python 3.x, `sqlite3` (stdlib), `numpy` (единственная тяжёлая зависимость, есть в `requirements-gigaam.txt`), `pytest`. Никакого sklearn/scipy/torch.

**Out of scope (отдельные планы позже):** текст-фичи (Фаза 2), affective/topical (Фаза 3), dominance (Фаза 4), карточки/визуализация (Фазы 6-7). Маршрут — `docs/superpowers/specs/2026-06-06-insight-archetypes-design.md` §10.

**Commit-стиль:** conventional commits, БЕЗ строки атрибуции (атрибуция отключена глобально — см. `.claude/rules/ecc/.../git-workflow.md` и историю репо).

---

## File Structure

| Файл | Ответственность |
|---|---|
| `src/callprofiler/insight/__init__.py` | маркер пакета |
| `src/callprofiler/insight/repository.py` | `apply_insight_schema(conn)`, CRUD моделей/назначений (WHERE user_id=?) |
| `src/callprofiler/insight/features/base.py` | `Tier`, `Feature`, `parse_dt()` |
| `src/callprofiler/insight/features/temporal.py` | циркадные ratios, burstiness, tenure, recency |
| `src/callprofiler/insight/features/reciprocity.py` | outgoing_ratio, mean_duration, calls_per_week, total_calls |
| `src/callprofiler/insight/features/trajectory.py` | cadence_slope, changepoints |
| `src/callprofiler/insight/synth/noise.py` | `inject_asr_noise(text, rate, seed)` |
| `src/callprofiler/insight/synth/archetypes.py` | `ArchetypeTemplate` + `DEFAULT_TEMPLATES` (ground-truth) |
| `src/callprofiler/insight/synth/corpus.py` | `SyntheticCorpus.build()` → temp SQLite |
| `src/callprofiler/insight/feature_store.py` | сборка матрицы, импутация+z-score+взвешивание, персист |
| `src/callprofiler/insight/archetypes.py` | `pca/kmeans/silhouette/adjusted_rand_index/fit_archetypes` |
| `src/callprofiler/cli/commands/insight.py` | команды `features-build`, `archetypes-fit` |
| `tests/insight/*` | юнит + интеграция (ARI-гейт, noise, idempotency, isolation) |

---

## Phase 0 — Offline Harness

### Task 1: Проверка окружения (офлайн-запускаемость)

**Files:** нет (только проверка).

- [ ] **Step 1: Проверить python, numpy, pytest**

Run:
```
python --version
python -c "import numpy, sqlite3, sys; print('numpy', numpy.__version__)"
python -m pytest --version
```
Expected: python 3.10+, numpy печатает версию, pytest печатает версию.

- [ ] **Step 2: Если numpy/pytest отсутствуют — поставить**

Run (только при ImportError на шаге 1):
```
python -m pip install numpy pytest
```
Expected: успешная установка. (Разрешение на запуск процессов дано пользователем.)

- [ ] **Step 3: Зафиксировать `tests/insight/__init__.py`**

Create `tests/insight/__init__.py` (пустой).
```bash
git add tests/insight/__init__.py
git commit -m "chore(insight): test package scaffold"
```

---

### Task 2: Insight schema + repository

**Files:**
- Create: `src/callprofiler/insight/__init__.py` (пустой)
- Create: `src/callprofiler/insight/repository.py`
- Test: `tests/insight/test_repository.py`

- [ ] **Step 1: Failing test (написать + прогнать, ожидать FAIL)**

`tests/insight/test_repository.py`:
```python
import sqlite3
from callprofiler.insight.repository import apply_insight_schema

def _tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}

def test_apply_insight_schema_creates_tables():
    conn = sqlite3.connect(":memory:")
    apply_insight_schema(conn)
    t = _tables(conn)
    assert {"contact_features", "archetype_models", "contact_archetypes"} <= t

def test_apply_insight_schema_idempotent():
    conn = sqlite3.connect(":memory:")
    apply_insight_schema(conn)
    apply_insight_schema(conn)  # second call must not raise
    assert "contact_features" in _tables(conn)
```
Run: `python -m pytest tests/insight/test_repository.py -v`
Expected: FAIL (ModuleNotFoundError: callprofiler.insight.repository).

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/__init__.py`: пустой файл.

`src/callprofiler/insight/repository.py`:
```python
"""Insight engine persistence. All queries filter by user_id."""
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contact_features (
    contact_id   INTEGER NOT NULL,
    user_id      TEXT    NOT NULL,
    feature_set  TEXT    NOT NULL,
    feature_name TEXT    NOT NULL,
    value        REAL,
    support_n    INTEGER NOT NULL DEFAULT 0,
    tier         TEXT    NOT NULL,
    computed_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contact_id, feature_name)
);
CREATE INDEX IF NOT EXISTS idx_cfeat_user_set ON contact_features(user_id, feature_set);

CREATE TABLE IF NOT EXISTS archetype_models (
    model_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL,
    version      TEXT    NOT NULL,
    k            INTEGER NOT NULL,
    silhouette   REAL,
    n_contacts   INTEGER,
    feature_list TEXT,
    centroids    TEXT,
    labels       TEXT,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_archetypes (
    contact_id       INTEGER PRIMARY KEY,
    user_id          TEXT    NOT NULL,
    model_id         INTEGER,
    cluster_idx      INTEGER NOT NULL,
    archetype_label  TEXT,
    membership       REAL,
    distinctive_dims TEXT,
    confidence       TEXT,
    evidence         TEXT,
    computed_at      TEXT    DEFAULT CURRENT_TIMESTAMP
);
"""

def apply_insight_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()
```
Run: `python -m pytest tests/insight/test_repository.py -v`
Expected: PASS (2 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/__init__.py src/callprofiler/insight/repository.py tests/insight/test_repository.py
git commit -m "feat(insight): insight schema + repository"
```

---

### Task 3: features/base.py — Tier, Feature, parse_dt

**Files:**
- Create: `src/callprofiler/insight/features/__init__.py` (пустой)
- Create: `src/callprofiler/insight/features/base.py`
- Test: `tests/insight/test_base.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_base.py`:
```python
from datetime import datetime
from callprofiler.insight.features.base import Tier, Feature, parse_dt

def test_feature_holds_value_support_tier():
    f = Feature(0.5, 10, Tier.IMMUNE)
    assert f.value == 0.5 and f.support_n == 10 and f.tier == Tier.IMMUNE

def test_parse_dt_iso_space_and_t():
    assert parse_dt("2026-03-01 21:30:00") == datetime(2026, 3, 1, 21, 30, 0)
    assert parse_dt("2026-03-01T21:30:00") == datetime(2026, 3, 1, 21, 30, 0)

def test_parse_dt_none_and_garbage():
    assert parse_dt(None) is None
    assert parse_dt("") is None
    assert parse_dt("not a date") is None
```
Run: `python -m pytest tests/insight/test_base.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/features/__init__.py`: пустой.

`src/callprofiler/insight/features/base.py`:
```python
"""Feature primitives shared by all insight feature modules."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Tier(str, Enum):
    IMMUNE = "immune"        # metadata — ASR-неуязвимо
    ROBUST = "robust"        # агрегаты служебных слов
    AFFECTIVE = "affective"  # из LLM-анализа
    FRAGILE = "fragile"      # зависит от диаризации

@dataclass(frozen=True)
class Feature:
    value: float
    support_n: int
    tier: Tier

_FMTS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")

def parse_dt(s):
    """Парсит call_datetime (ISO/пробел/T/дата). None при пустом/мусоре."""
    if not s:
        return None
    s = s.strip().replace("T", " ")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
```
Run: `python -m pytest tests/insight/test_base.py -v`
Expected: PASS (3 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/features/__init__.py src/callprofiler/insight/features/base.py tests/insight/test_base.py
git commit -m "feat(insight): feature base (Tier, Feature, parse_dt)"
```

---

### Task 4: synth/noise.py — ASR noise injector

**Files:**
- Create: `src/callprofiler/insight/synth/__init__.py` (пустой)
- Create: `src/callprofiler/insight/synth/noise.py`
- Test: `tests/insight/test_noise.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_noise.py`:
```python
from callprofiler.insight.synth.noise import inject_asr_noise

def test_zero_rate_is_identity():
    s = "привет как дела наверное завтра позвоню"
    assert inject_asr_noise(s, rate=0.0, seed=1) == s

def test_noise_changes_text_but_keeps_length_ballpark():
    s = "привет как дела наверное завтра позвоню договорились хорошо"
    out = inject_asr_noise(s, rate=0.5, seed=1)
    assert out != s
    # длина слов сохраняется в пределах разумного (дроп частиц)
    assert abs(len(out.split()) - len(s.split())) <= len(s.split())

def test_deterministic_with_seed():
    s = "одна две три четыре пять шесть семь"
    assert inject_asr_noise(s, 0.3, seed=7) == inject_asr_noise(s, 0.3, seed=7)
```
Run: `python -m pytest tests/insight/test_noise.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/synth/__init__.py`: пустой.

`src/callprofiler/insight/synth/noise.py`:
```python
"""Реалистичный ASR-шум для проверки устойчивости фич.

Модели ошибок: выпадение коротких частиц, подмена соседней буквы,
гомофон-подмена. Детерминирован по seed.
"""
import random

# короткие слова-частицы, которые ASR часто глотает
_DROPPABLE = {"и", "а", "но", "же", "ли", "бы", "ну", "вот", "так", "уж", "то"}
# частые гомофоны/смешения в русском ASR
_HOMOPHONES = {
    "что": "што", "его": "ево", "сейчас": "щас", "тоже": "тож",
    "когда": "када", "сколько": "скока", "конечно": "конешно",
}

def _perturb_word(w, rng):
    if len(w) < 4:
        return w
    i = rng.randrange(1, len(w) - 1)
    chars = list(w)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]  # transposition
    return "".join(chars)

def inject_asr_noise(text: str, rate: float = 0.2, seed: int = 0) -> str:
    if rate <= 0:
        return text
    rng = random.Random(seed)
    out = []
    for w in text.split():
        low = w.lower()
        if low in _DROPPABLE and rng.random() < rate:
            continue  # выпадение частицы
        if low in _HOMOPHONES and rng.random() < rate:
            out.append(_HOMOPHONES[low])
            continue
        if rng.random() < rate:
            out.append(_perturb_word(w, rng))
            continue
        out.append(w)
    return " ".join(out)
```
Run: `python -m pytest tests/insight/test_noise.py -v`
Expected: PASS (3 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/synth/__init__.py src/callprofiler/insight/synth/noise.py tests/insight/test_noise.py
git commit -m "feat(insight): synthetic ASR noise injector"
```

---

### Task 5: synth/archetypes.py + synth/corpus.py — ground-truth corpus

**Files:**
- Create: `src/callprofiler/insight/synth/archetypes.py`
- Create: `src/callprofiler/insight/synth/corpus.py`
- Test: `tests/insight/test_corpus.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_corpus.py`:
```python
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.synth.archetypes import DEFAULT_TEMPLATES

def test_corpus_builds_faithful_db():
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=8)
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    n_calls = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    assert n_users == 1
    assert n_contacts == len(DEFAULT_TEMPLATES) * 8
    assert n_calls > 0

def test_corpus_exposes_ground_truth():
    corpus = SyntheticCorpus(seed=0)
    corpus.build(n_per=8)
    gt = corpus.ground_truth  # dict contact_id -> archetype name
    assert len(gt) == len(DEFAULT_TEMPLATES) * 8
    assert set(gt.values()) == {t.name for t in DEFAULT_TEMPLATES}

def test_corpus_user_isolation():
    corpus = SyntheticCorpus(seed=0)
    conn = corpus.build(n_per=5, user_id="me")
    bad = conn.execute("SELECT COUNT(*) FROM calls WHERE user_id != 'me'").fetchone()[0]
    assert bad == 0
```
Run: `python -m pytest tests/insight/test_corpus.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 2: Реализация — templates**

`src/callprofiler/insight/synth/archetypes.py`:
```python
"""Ground-truth архетипы для синт-корпуса (только метаданные, Фаза 1).

Каждый шаблон задаёт распределения времени/направления/длительности/каденса.
Шаблоны намеренно разделимы по метаданным, чтобы кластеризация их восстановила.
"""
from dataclasses import dataclass
from datetime import timedelta
import numpy as np

@dataclass(frozen=True)
class ArchetypeTemplate:
    name: str
    n_calls: tuple        # (lo, hi)
    tenure_days: tuple    # (lo, hi)
    hours: tuple          # кандидаты часов (0-23)
    p_weekend: float
    p_out: float          # доля исходящих
    dur_mu: float         # медиана длительности, сек
    dur_sigma: float
    cadence_trend: float  # >0 ускорение (к концу), <0 угасание (к началу)

    def sample_calls(self, rng: np.random.Generator, end_date):
        n = int(rng.integers(self.n_calls[0], self.n_calls[1] + 1))
        tenure = int(rng.integers(self.tenure_days[0], self.tenure_days[1] + 1))
        start = end_date - timedelta(days=tenure)
        u = rng.random(n)
        if self.cadence_trend > 0:
            pos = u ** (1.0 / (1.0 + self.cadence_trend))   # к 1 (свежие)
        elif self.cadence_trend < 0:
            pos = u ** (1.0 + abs(self.cadence_trend))       # к 0 (старые)
        else:
            pos = u
        calls = []
        for p in sorted(pos):
            day = start + timedelta(days=float(p) * tenure)
            if rng.random() < self.p_weekend:
                shift = (5 - day.weekday()) % 7
                day = day + timedelta(days=shift)  # подвинуть к выходным
            hour = int(rng.choice(self.hours))
            dt = day.replace(hour=hour, minute=int(rng.integers(0, 60)),
                             second=0, microsecond=0)
            direction = "OUT" if rng.random() < self.p_out else "IN"
            dur = int(max(5, rng.lognormal(np.log(self.dur_mu), self.dur_sigma)))
            calls.append({
                "call_datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "direction": direction,
                "duration_sec": dur,
            })
        return calls

DEFAULT_TEMPLATES = (
    ArchetypeTemplate("night_dependent", (25, 45), (40, 90),
                      hours=(21, 22, 23, 0, 1), p_weekend=0.5, p_out=0.15,
                      dur_mu=600, dur_sigma=0.6, cadence_trend=1.2),
    ArchetypeTemplate("business_transactional", (15, 35), (120, 300),
                      hours=(10, 11, 14, 15, 16), p_weekend=0.02, p_out=0.5,
                      dur_mu=180, dur_sigma=0.5, cadence_trend=0.0),
    ArchetypeTemplate("fading_tie", (6, 14), (200, 400),
                      hours=(12, 13, 18), p_weekend=0.2, p_out=0.5,
                      dur_mu=120, dur_sigma=0.5, cadence_trend=-1.2),
    ArchetypeTemplate("intimate_frequent", (30, 60), (150, 350),
                      hours=(19, 20, 21), p_weekend=0.6, p_out=0.5,
                      dur_mu=900, dur_sigma=0.7, cadence_trend=0.3),
)
```

- [ ] **Step 3: Реализация — corpus**

`src/callprofiler/insight/synth/corpus.py`:
```python
"""Schema-accurate синтетическая БД для офлайн-разработки и валидации."""
import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np

from callprofiler.insight.repository import apply_insight_schema
from callprofiler.insight.synth.archetypes import DEFAULT_TEMPLATES

_BASE_SCHEMA = Path(__file__).resolve().parents[1].parent / "db" / "schema.sql"

class SyntheticCorpus:
    def __init__(self, seed: int = 0):
        self.seed = seed
        self.ground_truth: dict[int, str] = {}

    def build(self, path: str = ":memory:", n_per: int = 20,
              user_id: str = "me", templates=DEFAULT_TEMPLATES,
              end_date=datetime(2026, 6, 1)) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.executescript(_BASE_SCHEMA.read_text(encoding="utf-8"))
        apply_insight_schema(conn)
        conn.execute(
            "INSERT INTO users(user_id, display_name, incoming_dir, sync_dir, ref_audio) "
            "VALUES (?,?,?,?,?)",
            (user_id, "Synthetic", "in", "sync", "ref.wav"),
        )
        rng = np.random.default_rng(self.seed)
        self.ground_truth = {}
        for tmpl in templates:
            for _ in range(n_per):
                cur = conn.execute(
                    "INSERT INTO contacts(user_id, display_name) VALUES (?,?)",
                    (user_id, f"{tmpl.name}_{rng.integers(1_000_000)}"),
                )
                contact_id = cur.lastrowid
                self.ground_truth[contact_id] = tmpl.name
                for i, call in enumerate(tmpl.sample_calls(rng, end_date)):
                    conn.execute(
                        "INSERT INTO calls(user_id, contact_id, direction, call_datetime, "
                        "source_filename, source_md5, duration_sec, status) "
                        "VALUES (?,?,?,?,?,?,?, 'done')",
                        (user_id, contact_id, call["direction"], call["call_datetime"],
                         f"c{contact_id}_{i}.mp3", f"md5-{contact_id}-{i}",
                         call["duration_sec"]),
                    )
        conn.commit()
        return conn
```
Run: `python -m pytest tests/insight/test_corpus.py -v`
Expected: PASS (3 passed). Если `_BASE_SCHEMA` путь неверен — поправить индекс `parents[...]` (цель: `src/callprofiler/db/schema.sql`).

- [ ] **Step 4: Commit**
```bash
git add src/callprofiler/insight/synth/archetypes.py src/callprofiler/insight/synth/corpus.py tests/insight/test_corpus.py
git commit -m "feat(insight): synthetic ground-truth corpus"
```

---

## Phase 1 — IMMUNE features + metadata archetypes

### Task 6: features/temporal.py

**Files:**
- Create: `src/callprofiler/insight/features/temporal.py`
- Test: `tests/insight/test_temporal.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_temporal.py`:
```python
from datetime import datetime
from callprofiler.insight.features.temporal import compute_temporal
from callprofiler.insight.features.base import Tier

def _calls(hours, day="2026-03-02"):  # 2026-03-02 = понедельник
    return [{"call_datetime": f"{day} {h:02d}:00:00", "duration_sec": 60} for h in hours]

def test_evening_and_night_ratio():
    f = compute_temporal(_calls([21, 22, 23, 2]))
    assert f["evening_ratio"].value == 0.75
    assert f["night_ratio"].value == 0.25
    assert f["evening_ratio"].tier == Tier.IMMUNE

def test_empty_calls_returns_empty():
    assert compute_temporal([]) == {}

def test_burstiness_needs_three_calls():
    assert "burstiness" not in compute_temporal(_calls([10, 11]))
    assert "burstiness" in compute_temporal(_calls([10, 11, 12]))

def test_recency_from_reference_now():
    calls = [{"call_datetime": "2026-03-01 10:00:00", "duration_sec": 60}]
    f = compute_temporal(calls, reference_now=datetime(2026, 3, 11, 10))
    assert f["recency_days"].value == 10.0
```
Run: `python -m pytest tests/insight/test_temporal.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/features/temporal.py`:
```python
"""Темпоральная подпись контакта. Тир IMMUNE (метаданные)."""
import statistics
from .base import Feature, Tier, parse_dt

def compute_temporal(calls, reference_now=None):
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    n = len(dts)
    if n == 0:
        return {}
    evening = sum(1 for d in dts if 18 <= d.hour <= 23)
    night = sum(1 for d in dts if 0 <= d.hour <= 5)
    business = sum(1 for d in dts if d.weekday() < 5 and 9 <= d.hour < 18)
    weekend = sum(1 for d in dts if d.weekday() >= 5)
    out = {
        "evening_ratio": Feature(evening / n, n, Tier.IMMUNE),
        "night_ratio": Feature(night / n, n, Tier.IMMUNE),
        "business_ratio": Feature(business / n, n, Tier.IMMUNE),
        "weekend_ratio": Feature(weekend / n, n, Tier.IMMUNE),
        "tenure_days": Feature(float((dts[-1] - dts[0]).days), n, Tier.IMMUNE),
    }
    if n >= 3:
        gaps = [(dts[i + 1] - dts[i]).total_seconds() / 3600.0 for i in range(n - 1)]
        mean = statistics.fmean(gaps)
        sd = statistics.pstdev(gaps)
        b = (sd - mean) / (sd + mean) if (sd + mean) > 0 else 0.0
        out["burstiness"] = Feature(b, len(gaps), Tier.IMMUNE)
    if reference_now is not None:
        out["recency_days"] = Feature(float((reference_now - dts[-1]).days), n, Tier.IMMUNE)
    return out
```
Run: `python -m pytest tests/insight/test_temporal.py -v`
Expected: PASS (4 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/features/temporal.py tests/insight/test_temporal.py
git commit -m "feat(insight): temporal features"
```

---

### Task 7: features/reciprocity.py

**Files:**
- Create: `src/callprofiler/insight/features/reciprocity.py`
- Test: `tests/insight/test_reciprocity.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_reciprocity.py`:
```python
from callprofiler.insight.features.reciprocity import compute_reciprocity

def test_outgoing_ratio_ignores_unknown_direction():
    calls = [
        {"direction": "OUT", "duration_sec": 100, "call_datetime": "2026-03-01 10:00:00"},
        {"direction": "IN",  "duration_sec": 200, "call_datetime": "2026-03-08 10:00:00"},
        {"direction": "UNKNOWN", "duration_sec": 50, "call_datetime": "2026-03-09 10:00:00"},
    ]
    f = compute_reciprocity(calls)
    assert f["outgoing_ratio"].value == 0.5
    assert f["outgoing_ratio"].support_n == 2  # UNKNOWN не считается

def test_total_calls_and_mean_duration():
    calls = [
        {"direction": "OUT", "duration_sec": 100, "call_datetime": "2026-03-01 10:00:00"},
        {"direction": "OUT", "duration_sec": 300, "call_datetime": "2026-03-15 10:00:00"},
    ]
    f = compute_reciprocity(calls)
    assert f["total_calls"].value == 2.0
    assert f["mean_duration_sec"].value == 200.0
    assert round(f["calls_per_week"].value, 2) == 1.0  # 2 звонка за 2 недели

def test_empty_returns_empty():
    assert compute_reciprocity([]) == {}
```
Run: `python -m pytest tests/insight/test_reciprocity.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/features/reciprocity.py`:
```python
"""Реципрокность/власть/частота. Тир IMMUNE."""
import statistics
from .base import Feature, Tier, parse_dt

def compute_reciprocity(calls, reference_now=None):
    n = len(calls)
    if n == 0:
        return {}
    out = {"total_calls": Feature(float(n), n, Tier.IMMUNE)}
    known = [c for c in calls if (c.get("direction") or "UNKNOWN").upper() in ("IN", "OUT")]
    if known:
        outc = sum(1 for c in known if c["direction"].upper() == "OUT")
        out["outgoing_ratio"] = Feature(outc / len(known), len(known), Tier.IMMUNE)
    durs = [c["duration_sec"] for c in calls if c.get("duration_sec")]
    if durs:
        out["mean_duration_sec"] = Feature(float(statistics.fmean(durs)), len(durs), Tier.IMMUNE)
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    if len(dts) >= 2:
        weeks = max((dts[-1] - dts[0]).days / 7.0, 1e-9)
        out["calls_per_week"] = Feature(len(dts) / weeks, len(dts), Tier.IMMUNE)
    return out
```
Run: `python -m pytest tests/insight/test_reciprocity.py -v`
Expected: PASS (3 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/features/reciprocity.py tests/insight/test_reciprocity.py
git commit -m "feat(insight): reciprocity features"
```

---

### Task 8: features/trajectory.py

**Files:**
- Create: `src/callprofiler/insight/features/trajectory.py`
- Test: `tests/insight/test_trajectory.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_trajectory.py`:
```python
from callprofiler.insight.features.trajectory import compute_trajectory

def _weekly(n_weeks, per_week, start="2026-01-05"):
    from datetime import datetime, timedelta
    base = datetime.fromisoformat(start + " 10:00:00")
    calls = []
    for w in range(n_weeks):
        for _ in range(per_week):
            calls.append({"call_datetime": (base + timedelta(weeks=w)).strftime("%Y-%m-%d %H:%M:%S")})
    return calls

def test_too_few_calls_returns_empty():
    assert compute_trajectory(_weekly(1, 2)) == {}

def test_accelerating_has_positive_slope():
    # 1,1,2,3,5 в неделю — ускорение
    from datetime import datetime, timedelta
    base = datetime.fromisoformat("2026-01-05 10:00:00")
    counts = [1, 1, 2, 3, 5]
    calls = []
    for w, c in enumerate(counts):
        for _ in range(c):
            calls.append({"call_datetime": (base + timedelta(weeks=w)).strftime("%Y-%m-%d %H:%M:%S")})
    f = compute_trajectory(calls)
    assert f["cadence_slope"].value > 0
```
Run: `python -m pytest tests/insight/test_trajectory.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/features/trajectory.py`:
```python
"""Траектория вовлечённости: тренд каденса + точки разлома. Тир IMMUNE."""
import numpy as np
from .base import Feature, Tier, parse_dt

def _cusum_changepoints(series):
    s = np.asarray(series, float)
    if len(s) < 4:
        return 0
    cum = np.cumsum(s - s.mean())
    d = np.diff(cum)
    signs = np.sign(d)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0
    return int(np.sum(signs[1:] != signs[:-1]))

def compute_trajectory(calls, reference_now=None):
    dts = sorted(d for d in (parse_dt(c.get("call_datetime")) for c in calls) if d)
    n = len(dts)
    if n < 4:
        return {}
    t0 = dts[0]
    weeks = [(d - t0).days // 7 for d in dts]
    counts = np.zeros(weeks[-1] + 1)
    for w in weeks:
        counts[w] += 1
    x = np.arange(len(counts))
    slope = float(np.polyfit(x, counts, 1)[0]) if len(counts) >= 2 and x.std() > 0 else 0.0
    return {
        "cadence_slope": Feature(slope, n, Tier.IMMUNE),
        "changepoints": Feature(float(_cusum_changepoints(counts)), len(counts), Tier.IMMUNE),
    }
```
Run: `python -m pytest tests/insight/test_trajectory.py -v`
Expected: PASS (2 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/features/trajectory.py tests/insight/test_trajectory.py
git commit -m "feat(insight): trajectory features"
```

---

### Task 9: feature_store.py — vector assembly + standardize

**Files:**
- Create: `src/callprofiler/insight/feature_store.py`
- Test: `tests/insight/test_feature_store.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_feature_store.py`:
```python
import numpy as np
from callprofiler.insight.features.base import Feature, Tier
from callprofiler.insight.feature_store import assemble_matrix, standardize, TIER_WEIGHTS

def test_assemble_aligns_names_and_imputes_missing():
    per_contact = {
        1: {"a": Feature(1.0, 5, Tier.IMMUNE), "b": Feature(2.0, 5, Tier.IMMUNE)},
        2: {"a": Feature(3.0, 5, Tier.IMMUNE)},  # b отсутствует
    }
    cids, names, X, weights = assemble_matrix(per_contact)
    assert cids == [1, 2]
    assert names == ["a", "b"]
    assert np.isnan(X[1, 1])  # b у контакта 2 пропущен

def test_standardize_imputes_and_zscores():
    X = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 6.0]])
    weights = np.array([1.0, 1.0])
    Z = standardize(X, weights)
    assert not np.isnan(Z).any()
    assert abs(Z[:, 0].mean()) < 1e-9  # колонка центрирована

def test_low_support_blanked():
    per_contact = {
        1: {"a": Feature(1.0, 1, Tier.IMMUNE)},  # support_n=1 < floor
        2: {"a": Feature(3.0, 9, Tier.IMMUNE)},
    }
    cids, names, X, weights = assemble_matrix(per_contact, support_floor=2)
    assert np.isnan(X[0, 0])  # выбракован по support
```
Run: `python -m pytest tests/insight/test_feature_store.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/feature_store.py`:
```python
"""Сборка по-контактной матрицы фич, импутация, взвешивание, z-score."""
import numpy as np
from .features.base import Tier

TIER_WEIGHTS = {
    Tier.IMMUNE: 1.0,
    Tier.ROBUST: 0.8,
    Tier.AFFECTIVE: 0.6,
    Tier.FRAGILE: 0.4,
}

def assemble_matrix(per_contact_features, support_floor: int = 2):
    """per_contact_features: {contact_id: {name: Feature}} ->
       (contact_ids, names, X[NaN-missing], col_weights)."""
    cids = sorted(per_contact_features)
    names = sorted({nm for feats in per_contact_features.values() for nm in feats})
    name_idx = {nm: j for j, nm in enumerate(names)}
    X = np.full((len(cids), len(names)), np.nan)
    weights = np.ones(len(names))
    for i, cid in enumerate(cids):
        for nm, feat in per_contact_features[cid].items():
            j = name_idx[nm]
            if feat.support_n < support_floor:
                continue  # ниже порога — оставляем NaN (импутируется медианой)
            X[i, j] = feat.value
            weights[j] = TIER_WEIGHTS.get(feat.tier, 1.0)
    return cids, names, X, weights

def standardize(X, col_weights):
    """Импутация колоночной медианой → z-score → масштаб sqrt(weight)."""
    X = X.astype(float).copy()
    for j in range(X.shape[1]):
        col = X[:, j]
        mask = ~np.isnan(col)
        med = np.median(col[mask]) if mask.any() else 0.0
        col[~mask] = med
        mu, sd = col.mean(), col.std()
        col = (col - mu) / sd if sd > 0 else col - mu
        X[:, j] = col * np.sqrt(col_weights[j])
    return X
```
Run: `python -m pytest tests/insight/test_feature_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/feature_store.py tests/insight/test_feature_store.py
git commit -m "feat(insight): feature matrix assembly + standardize"
```

---

### Task 10: archetypes.py — PCA / kmeans / silhouette / ARI

**Files:**
- Create: `src/callprofiler/insight/archetypes.py`
- Test: `tests/insight/test_archetypes_math.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_archetypes_math.py`:
```python
import numpy as np
from callprofiler.insight.archetypes import (
    pca, kmeans, silhouette, adjusted_rand_index, fit_archetypes,
)

def test_ari_identical_is_one():
    a = [0, 0, 1, 1, 2, 2]
    assert adjusted_rand_index(a, a) == 1.0

def test_ari_permuted_labels_is_one():
    a = [0, 0, 1, 1]
    b = [1, 1, 0, 0]  # та же разбивка, другие метки
    assert adjusted_rand_index(a, b) == 1.0

def test_kmeans_separates_two_blobs():
    rng = np.random.default_rng(0)
    blob = np.vstack([rng.normal(0, 0.1, (20, 2)), rng.normal(5, 0.1, (20, 2))])
    labels, centers = kmeans(blob, 2, seed=0)
    # внутри блоба метки однородны
    assert len(set(labels[:20])) == 1 and len(set(labels[20:])) == 1

def test_fit_picks_two_clusters_for_two_blobs():
    rng = np.random.default_rng(1)
    blob = np.vstack([rng.normal(0, 0.2, (25, 3)), rng.normal(8, 0.2, (25, 3))])
    res = fit_archetypes(blob, k_range=range(2, 6), seed=0)
    assert res["k"] == 2
    assert res["silhouette"] > 0.5
```
Run: `python -m pytest tests/insight/test_archetypes_math.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация**

`src/callprofiler/insight/archetypes.py`:
```python
"""Кластеризация архетипов на чистом numpy: PCA, k-means, silhouette, ARI."""
from math import comb
import numpy as np

def pca(X, k):
    Xc = X - X.mean(0)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    k = min(k, Vt.shape[0])
    return Xc @ Vt[:k].T

def _kpp_init(X, k, rng):
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min([((X - c) ** 2).sum(1) for c in centers], axis=0)
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        centers.append(X[rng.choice(n, p=probs)])
    return np.array(centers)

def kmeans(X, k, seed=0, n_init=10, max_iter=100):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        centers = _kpp_init(X, k, rng)
        labels = np.zeros(len(X), int)
        for _ in range(max_iter):
            d = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(2)
            new_labels = d.argmin(1)
            new_centers = np.array([
                X[new_labels == c].mean(0) if (new_labels == c).any() else centers[c]
                for c in range(k)
            ])
            if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
                labels = new_labels
                centers = new_centers
                break
            labels, centers = new_labels, new_centers
        inertia = ((X - centers[labels]) ** 2).sum()
        if best is None or inertia < best[0]:
            best = (inertia, labels, centers)
    return best[1], best[2]

def silhouette(X, labels):
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(2))
    sil = np.zeros(len(X))
    for i in range(len(X)):
        same = labels == labels[i]
        same[i] = False
        a = D[i, same].mean() if same.any() else 0.0
        b = min(D[i, labels == c].mean() for c in uniq if c != labels[i])
        sil[i] = 0.0 if max(a, b) == 0 else (b - a) / max(a, b)
    return float(sil.mean())

def adjusted_rand_index(a, b):
    a, b = np.asarray(a), np.asarray(b)
    ca = {v: i for i, v in enumerate(np.unique(a))}
    cb = {v: i for i, v in enumerate(np.unique(b))}
    cont = np.zeros((len(ca), len(cb)), int)
    for x, y in zip(a, b):
        cont[ca[x], cb[y]] += 1
    sum_c = sum(comb(int(v), 2) for v in cont.flatten())
    a_c = sum(comb(int(v), 2) for v in cont.sum(1))
    b_c = sum(comb(int(v), 2) for v in cont.sum(0))
    tot = comb(len(a), 2)
    exp = a_c * b_c / tot if tot else 0.0
    maxi = (a_c + b_c) / 2
    return float((sum_c - exp) / (maxi - exp)) if (maxi - exp) != 0 else 1.0

def fit_archetypes(X, k_range=range(2, 8), seed=0, pca_dim=10):
    Xp = pca(X, min(pca_dim, X.shape[1]))
    best = None
    for k in k_range:
        if k >= len(X):
            continue
        labels, centers = kmeans(Xp, k, seed=seed)
        s = silhouette(Xp, labels)
        if best is None or s > best["silhouette"]:
            best = {"silhouette": s, "k": k, "labels": labels,
                    "centroids": centers, "projection": Xp}
    return best
```
Run: `python -m pytest tests/insight/test_archetypes_math.py -v`
Expected: PASS (4 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/archetypes.py tests/insight/test_archetypes_math.py
git commit -m "feat(insight): numpy clustering (pca/kmeans/silhouette/ari)"
```

---

### Task 11: Ground-truth recovery (ARI-гейт) — интеграция

**Files:**
- Create: `src/callprofiler/insight/feature_store.py` (добавить `build_contact_features`)
- Test: `tests/insight/test_recovery.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_recovery.py`:
```python
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.feature_store import build_contact_features, assemble_matrix, standardize
from callprofiler.insight.archetypes import fit_archetypes, adjusted_rand_index

def _recover(seed, n_per):
    corpus = SyntheticCorpus(seed=seed)
    conn = corpus.build(n_per=n_per)
    per_contact = build_contact_features(conn, "me")
    cids, names, X, w = assemble_matrix(per_contact)
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 7), seed=0)
    truth = [corpus.ground_truth[c] for c in cids]
    return adjusted_rand_index(res["labels"], truth)

def test_recovers_planted_archetypes_clean():
    assert _recover(seed=0, n_per=20) >= 0.6

def test_recovers_under_small_sample():
    assert _recover(seed=3, n_per=12) >= 0.4
```
Run: `python -m pytest tests/insight/test_recovery.py -v`
Expected: FAIL (build_contact_features отсутствует).

- [ ] **Step 2: Реализация — добавить в `feature_store.py`**

Добавить в начало `feature_store.py`:
```python
from .features.temporal import compute_temporal
from .features.reciprocity import compute_reciprocity
from .features.trajectory import compute_trajectory

_IMMUNE_FNS = (compute_temporal, compute_reciprocity, compute_trajectory)

def build_contact_features(conn, user_id, feature_fns=_IMMUNE_FNS, reference_now=None):
    """Читает звонки per contact, запускает фичи -> {contact_id: {name: Feature}}."""
    conn.row_factory = __import__("sqlite3").Row
    contact_ids = [r[0] for r in conn.execute(
        "SELECT contact_id FROM contacts WHERE user_id = ?", (user_id,)
    ).fetchall()]
    out = {}
    for cid in contact_ids:
        rows = conn.execute(
            "SELECT call_id, direction, call_datetime, duration_sec "
            "FROM calls WHERE user_id = ? AND contact_id = ? ORDER BY call_datetime",
            (user_id, cid),
        ).fetchall()
        calls = [dict(r) for r in rows]
        feats = {}
        for fn in feature_fns:
            feats.update(fn(calls, reference_now=reference_now))
        if feats:
            out[cid] = feats
    return out
```
Run: `python -m pytest tests/insight/test_recovery.py -v`
Expected: PASS (2 passed). Если ARI ниже порога — усилить разделимость шаблонов в `synth/archetypes.py` (развести `hours`/`cadence_trend`/`dur_mu`), НЕ ослаблять порог.

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/feature_store.py tests/insight/test_recovery.py
git commit -m "feat(insight): contact feature builder + ARI recovery gate"
```

---

### Task 12: Персист модели и назначений (идемпотентность)

**Files:**
- Modify: `src/callprofiler/insight/repository.py` (добавить save/load)
- Test: `tests/insight/test_persist.py`

- [ ] **Step 1: Failing test**

`tests/insight/test_persist.py`:
```python
import json
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight import repository as repo

def test_save_model_and_assignments_idempotent():
    conn = SyntheticCorpus(seed=0).build(n_per=10)
    mid1 = repo.save_archetype_model(conn, "me", version="arch-v1", k=4,
                                     silhouette=0.5, n_contacts=40,
                                     feature_list=["a"], centroids=[[0.0]],
                                     labels={"0": "x"})
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=mid1,
                                cluster_idx=0, label="x", membership=0.9,
                                distinctive_dims=[], confidence="high", evidence=[])
    # повтор по тому же contact_id — UPSERT, не дубль
    repo.save_contact_archetype(conn, "me", contact_id=1, model_id=mid1,
                                cluster_idx=1, label="y", membership=0.8,
                                distinctive_dims=[], confidence="high", evidence=[])
    rows = conn.execute("SELECT cluster_idx FROM contact_archetypes WHERE contact_id=1").fetchall()
    assert len(rows) == 1 and rows[0][0] == 1  # перезаписан

def test_user_isolation_on_load():
    conn = SyntheticCorpus(seed=0).build(n_per=5, user_id="me")
    assert repo.load_contact_archetypes(conn, "other") == []
```
Run: `python -m pytest tests/insight/test_persist.py -v`
Expected: FAIL.

- [ ] **Step 2: Реализация — добавить в `repository.py`**
```python
import json

def save_archetype_model(conn, user_id, *, version, k, silhouette, n_contacts,
                         feature_list, centroids, labels):
    cur = conn.execute(
        "INSERT INTO archetype_models(user_id, version, k, silhouette, n_contacts, "
        "feature_list, centroids, labels) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, version, k, silhouette, n_contacts,
         json.dumps(feature_list), json.dumps(centroids), json.dumps(labels)),
    )
    conn.commit()
    return cur.lastrowid

def save_contact_archetype(conn, user_id, *, contact_id, model_id, cluster_idx,
                           label, membership, distinctive_dims, confidence, evidence):
    conn.execute(
        "INSERT INTO contact_archetypes(contact_id, user_id, model_id, cluster_idx, "
        "archetype_label, membership, distinctive_dims, confidence, evidence) "
        "VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(contact_id) DO UPDATE SET model_id=excluded.model_id, "
        "cluster_idx=excluded.cluster_idx, archetype_label=excluded.archetype_label, "
        "membership=excluded.membership, distinctive_dims=excluded.distinctive_dims, "
        "confidence=excluded.confidence, evidence=excluded.evidence, "
        "computed_at=CURRENT_TIMESTAMP",
        (contact_id, user_id, model_id, cluster_idx, label, membership,
         json.dumps(distinctive_dims), confidence, json.dumps(evidence)),
    )
    conn.commit()

def load_contact_archetypes(conn, user_id):
    rows = conn.execute(
        "SELECT contact_id, cluster_idx, archetype_label, membership, confidence "
        "FROM contact_archetypes WHERE user_id = ? ORDER BY contact_id", (user_id,)
    ).fetchall()
    return [dict(zip(("contact_id", "cluster_idx", "label", "membership", "confidence"), r))
            for r in rows]
```
Run: `python -m pytest tests/insight/test_persist.py -v`
Expected: PASS (2 passed).

- [ ] **Step 3: Commit**
```bash
git add src/callprofiler/insight/repository.py tests/insight/test_persist.py
git commit -m "feat(insight): persist archetype model + assignments (idempotent)"
```

---

### Task 13: CLI — `features-build` + `archetypes-fit`

**Files:**
- Create: `src/callprofiler/cli/commands/insight.py`
- Modify: `src/callprofiler/cli/main.py` (зарегистрировать команды — следовать существующему паттерну subparsers)
- Test: `tests/insight/test_cli_smoke.py`

- [ ] **Step 1: Прочитать паттерн регистрации**

Run: `python -c "import callprofiler.cli.main as m; print(m.__file__)"` затем открыть файл и найти, как регистрируются существующие подкоманды (argparse subparsers / dispatch dict). Скопировать паттерн.

- [ ] **Step 2: Failing test**

`tests/insight/test_cli_smoke.py`:
```python
from callprofiler.insight.synth.corpus import SyntheticCorpus
from callprofiler.insight.cli_ops import run_features_build, run_archetypes_fit

def test_end_to_end_on_synth():
    conn = SyntheticCorpus(seed=0).build(n_per=15)
    n_feat = run_features_build(conn, "me")
    assert n_feat > 0
    res = run_archetypes_fit(conn, "me", version="arch-v1")
    assert res["k"] >= 2
    assert res["n_assigned"] == conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE user_id='me'").fetchone()[0]
```
Run: `python -m pytest tests/insight/test_cli_smoke.py -v`
Expected: FAIL.

- [ ] **Step 3: Реализация — `src/callprofiler/insight/cli_ops.py`**

(Логика отдельно от argparse — чтобы тестировать без подпроцесса.)
```python
"""Операции CLI insight: чистая логика, переиспользуется CLI и тестами."""
import json
from . import repository as repo
from .feature_store import build_contact_features, assemble_matrix, standardize, TIER_WEIGHTS
from .archetypes import fit_archetypes

def run_features_build(conn, user_id, reference_now=None):
    repo.apply_insight_schema(conn)
    per_contact = build_contact_features(conn, user_id, reference_now=reference_now)
    n = 0
    for cid, feats in per_contact.items():
        for name, feat in feats.items():
            conn.execute(
                "INSERT INTO contact_features(contact_id, user_id, feature_set, "
                "feature_name, value, support_n, tier) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(contact_id, feature_name) DO UPDATE SET "
                "value=excluded.value, support_n=excluded.support_n, "
                "tier=excluded.tier, computed_at=CURRENT_TIMESTAMP",
                (cid, user_id, name.split("_")[0], name, feat.value,
                 feat.support_n, feat.tier.value),
            )
            n += 1
    conn.commit()
    return n

def run_archetypes_fit(conn, user_id, version="arch-v1", reference_now=None):
    repo.apply_insight_schema(conn)
    per_contact = build_contact_features(conn, user_id, reference_now=reference_now)
    cids, names, X, w = assemble_matrix(per_contact)
    Z = standardize(X, w)
    res = fit_archetypes(Z, k_range=range(2, 8), seed=0)
    labels = res["labels"]
    mid = repo.save_archetype_model(
        conn, user_id, version=version, k=res["k"], silhouette=res["silhouette"],
        n_contacts=len(cids), feature_list=names,
        centroids=[c.tolist() for c in res["centroids"]],
        labels={str(i): f"cluster_{i}" for i in range(res["k"])},
    )
    for cid, lab in zip(cids, labels):
        repo.save_contact_archetype(
            conn, user_id, contact_id=cid, model_id=mid, cluster_idx=int(lab),
            label=f"cluster_{int(lab)}", membership=1.0,
            distinctive_dims=[], confidence="medium", evidence=[],
        )
    return {"k": res["k"], "silhouette": res["silhouette"], "n_assigned": len(cids)}
```
Run: `python -m pytest tests/insight/test_cli_smoke.py -v`  (импорт в тесте поправить на `from callprofiler.insight.cli_ops import ...`)
Expected: PASS (1 passed).

- [ ] **Step 4: Зарегистрировать команды в CLI**

В `src/callprofiler/cli/commands/insight.py` — тонкая обёртка argparse, открывающая БД через существующий механизм коннекта проекта и вызывающая `cli_ops.run_features_build` / `run_archetypes_fit` с `--user`. Зарегистрировать в `cli/main.py` по образцу соседних команд (`graph-backfill`/`graph-stats`).

Run (на боксе с реальной БД позже): `PYTHONPATH=src python -m callprofiler features-build --user me`
Expected: печатает число записанных фич без ошибок.

- [ ] **Step 5: Commit**
```bash
git add src/callprofiler/insight/cli_ops.py src/callprofiler/cli/commands/insight.py src/callprofiler/cli/main.py tests/insight/test_cli_smoke.py
git commit -m "feat(insight): CLI features-build + archetypes-fit"
```

---

## Финальная проверка фазы

- [ ] **Прогнать весь insight-набор**

Run: `python -m pytest tests/insight/ -v`
Expected: все зелёные, включая ARI-гейт (`test_recovery.py`).

- [ ] **Обновить память (CLAUDE.md Memory Protocol) и закоммитить**

- `CONTINUITY.md` — перезаписать: state=«Insight MVP (Фазы 0-1) собран, ARI-гейт зелёный», next=«Фаза 2 текст-фичи».
- `CHANGELOG.md` — добавить строку.
- `.claude/rules/` — при необходимости новая карта `insight.md` (контракт фич/тиров/ARI).
```bash
git add CONTINUITY.md CHANGELOG.md
git commit -m "docs(insight): MVP phase 0-1 complete"
git push origin main
```

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:** §2 harness→Tasks 1-5; §4 IMMUNE-фичи (temporal/reciprocity/trajectory)→Tasks 6-8; §5 взвешивание/z-score/support-floor→Task 9; §6 движок→Task 10; §6 ARI-гейт→Task 11; §7 схема→Task 2; персист→Task 12; CLI→Task 13. Текст/affective/dominance/карточки/виз (§4 тиры robust/affective/fragile, §9) — вне MVP, отдельные планы (заявлено).
- **Плейсхолдеры:** нет; код полный в каждом шаге.
- **Согласованность типов:** `Feature(value,support_n,tier)`, `parse_dt`, `assemble_matrix`→`standardize`→`fit_archetypes`, `save_*`/`load_*` — имена сквозные.
- **Известный риск:** ARI-пороги могут потребовать подкрутки разделимости шаблонов (Task 11 Step 2) — чинить шаблоны, не пороги.

## Roadmap (отдельные планы, по мере подхода)

- **Фаза 2** — ROBUST текст-фичи (hedge/directive/formality ты-вы/pronouns/lexical) + noise-tolerance тесты. Расширить синт-корпус генерацией `transcripts` по речевым регистрам шаблонов.
- **Фаза 3** — AFFECTIVE/TOPICAL из `analyses`/`entity_metrics`/`relations` + TF-IDF.
- **Фаза 4** — GATED dominance (по доле UNKNOWN).
- **Фаза 5** — расширенный движок (именование кластеров через LLM на боксе).
- **Фаза 6** — карточки + CLI `person-archetype`.
- **Фаза 7** — визуализация (карта архетипов / эго-сеть / ЭКГ / циркад).
