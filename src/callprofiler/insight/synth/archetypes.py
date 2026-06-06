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

    def sample_calls(self, rng: "np.random.Generator", end_date):
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
