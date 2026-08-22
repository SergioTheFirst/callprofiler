# -*- coding: utf-8 -*-
"""00_ci_demo.py — численная демонстрация формулы CI (20-first-principles.md §6), claim C-11.

Synth / mechanism only — НЕ evidence. Не открывает никакую БД. Запуск: `python 00_ci_demo.py`.
Выводит: при каких взвешенных n (исходов) CI = масса Beta-posterior в выбранном band достигает 50/60/80.
"""
from __future__ import annotations

import math

# 5 равных band ширины 0.2 (round 2: band <0.4 шириной 0.4 давал CI=62 после ~2 провалов — негативный
# ярлык почти без evidence; равные band убирают эту асимметрию).
BANDS = [(0.8, 1.0001, "выполнял почти все"), (0.6, 0.8, "выполнял большинство"),
         (0.4, 0.6, "выполнял около половины"), (0.2, 0.4, "выполнял меньшинство"), (0.0, 0.2, "почти не выполнял")]
NEG_MIN_N = 4.0  # негативные band (<0.4) показываются только при n_eff >= 4 (этика: цена ложного негатива)
GRID = 20001


def beta_pdf_grid(a: float, b: float):
    ln_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    xs, ys = [], []
    for i in range(GRID):
        x = i / (GRID - 1)
        x = min(max(x, 1e-9), 1 - 1e-9)
        xs.append(x)
        ys.append(math.exp(ln_norm + (a - 1) * math.log(x) + (b - 1) * math.log(1 - x)))
    return xs, ys


def band_mass(a: float, b: float, lo: float, hi: float) -> float:
    xs, ys = beta_pdf_grid(a, b)
    s = 0.0
    for i in range(1, GRID):
        if lo <= xs[i] < hi:
            s += 0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1])
    return s


HALF_WIDTH = 0.1  # CI = масса posterior в [median-0.1, median+0.1] (round 2: фиксированные band давали
                  # boundary-артефакт — контакт с истинной долей 0.2 на границе band никогда не получал CI>56)


def posterior_median(a: float, b: float) -> float:
    xs, ys = beta_pdf_grid(a, b)
    acc = 0.0
    for i in range(1, GRID):
        acc += 0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1])
        if acc >= 0.5:
            return xs[i]
    return 1.0


def phrase(m: float) -> str:
    return next(bd[2] for bd in BANDS if bd[0] <= m < bd[1])


def ci(alpha: float, beta: float) -> tuple[int, str]:
    m = posterior_median(alpha, beta)
    lo = min(max(m - HALF_WIDTH, 0.0), 1.0 - 2 * HALF_WIDTH)
    mass = band_mass(alpha, beta, lo, lo + 2 * HALF_WIDTH + 1e-9)
    return max(1, min(100, round(100 * mass))), phrase(m)


def demo() -> None:
    print("prior Beta(a0,b0) | доля исполнено | n(взвеш.) -> CI, band")
    for a0, b0 in [(1.0, 1.0), (2.0, 1.0), (3.0, 2.0)]:
        for rate in [1.0, 0.9, 0.7, 0.5, 0.2]:
            row = []
            for n in [0, 2, 4, 6, 8, 10, 12, 16, 24, 40]:
                k = rate * n
                c, band = ci(a0 + k, b0 + (n - k))
                row.append(f"n={n}:{c}")
            print(f"Beta({a0},{b0}) rate={rate}: " + " ".join(row))
    # assertions — свойства §6
    assert ci(1 + 10, 1 + 0)[0] > ci(1 + 5, 1 + 0)[0], "монотонность по n при чистой доле"
    assert ci(1.0, 1.0)[0] < 50, "n=0 -> ниже порога показа"
    assert ci(1 + 400, 1 + 0)[0] == 100, "n->inf с чистой долей -> 100"
    assert ci(1 + 5, 1 + 5)[1] == "выполнял около половины"
    assert ci(1.0, 1.0)[0] == 20, "uniform prior -> масса окна ширины 0.2 = 20"
    assert ci(1 + 8, 1 + 32)[0] >= 60, "доля 0.2 на границе band больше не штрафуется (sliding window)"
    print("OK")


if __name__ == "__main__":
    demo()
