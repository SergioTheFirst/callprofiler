# -*- coding: utf-8 -*-
"""output_budget.py — динамический бюджет выходных токенов для анализа звонка.

`max_tokens` — это ПОТОЛОК запроса, а не цель. У llama-server KV-кэш на весь
контекст выделяется один раз при старте (``-c N``), поэтому per-call
``max_tokens`` тратит ВРЕМЯ декодирования, а не VRAM. Единственное жёсткое
ограничение:

    prompt_tokens + max_tokens <= n_ctx

Длинные/насыщенные разговоры несут больше фактов → им нужно больше места под
вывод (иначе JSON обрезается на ``finish_reason="length"`` и теряются
promises/facts, что по blast-radius из decisions.md рушит граф и biography).
Короткие звонки перестают резервировать место, которое всё равно не используют.

Сигнал ценности v1 — длина транскрипта (дёшево, без отдельного вызова LLM).
Параллельный модулю ``biography/prompts.py`` (там CRS-множитель) подход, но для
основного call-analysis пути (orchestrator + bulk enricher).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

__all__ = [
    "output_budget",
    "OUTPUT_FLOOR",
    "OUTPUT_ABS_MAX",
    "CTX_SAFETY_MARGIN",
]

# Никогда не ниже: хватает на минимальный валидный JSON-ответ.
OUTPUT_FLOOR = 400
# Policy-потолок: ограничивает wall-clock на больших прогонах (17k).
OUTPUT_ABS_MAX = 4096
# Запас под n_ctx на дрейф токенизатора/шаблона (system-токены считаем грубо).
CTX_SAFETY_MARGIN = 512

# (верхняя граница длины транскрипта в символах, базовый бюджет вывода в токенах)
# Тиры подобраны так, что 1500 = прежний статический дефолт для «обычного» звонка.
_TIERS: tuple[tuple[int, int], ...] = (
    (800, 700),     # рутина / меньше минуты
    (3000, 1500),   # обычный — прежний статический дефолт
    (8000, 2600),   # содержательный
)
_LONG_TIER = 3600   # >= 8000 символов: длинный / высокоценный хвост

_PRIORITY_BUMP = 1.2
_PRIORITY_THRESHOLD = 70


def _base_for_length(transcript_chars: int) -> int:
    """Базовый бюджет по длине транскрипта (сигнал ценности v1)."""
    for upper, base in _TIERS:
        if transcript_chars < upper:
            return base
    return _LONG_TIER


def output_budget(
    transcript_chars: int,
    prompt_tokens: int,
    n_ctx: int,
    *,
    priority: int = 0,
    abs_max: int = OUTPUT_ABS_MAX,
    floor: int = OUTPUT_FLOOR,
    margin: int = CTX_SAFETY_MARGIN,
) -> int:
    """Адаптивный ``max_tokens`` для одного вызова анализа.

    Ограничен двумя потолками:
      * hardware/context: ``n_ctx - prompt_tokens - margin`` — против обрезки KV;
      * policy:           ``abs_max`` — против раздувания wall-clock на прогоне.

    Параметры:
        transcript_chars — длина текста транскрипта (символы).
        prompt_tokens    — оценка токенов всего промпта (system + user).
        n_ctx            — окно модели на старте llama-server (``-c``).
        priority         — приоритет контакта (>=70 → бюджет ×1.2).

    Возвращает целое число токенов в диапазоне [floor, abs_max], не нарушающее
    ``prompt_tokens + max_tokens <= n_ctx`` (кроме вырожденного случая, когда
    промпт сам почти заполняет окно — тогда вернётся усечённый потолок и это
    должно решаться более жёстким клипом ВХОДА выше по стеку).
    """
    base = _base_for_length(max(0, transcript_chars))
    if priority >= _PRIORITY_THRESHOLD:
        base = int(base * _PRIORITY_BUMP)

    hardware_ceiling = n_ctx - max(0, prompt_tokens) - margin
    ceiling = min(abs_max, hardware_ceiling)

    if ceiling <= floor:
        # Промпт теснит окно — вход надо клипать жёстче выше по стеку.
        if ceiling < base:
            log.warning(
                "output_budget: промпт теснит окно (n_ctx=%d, prompt~%d) → "
                "потолок вывода %d < базы %d; клипуйте вход",
                n_ctx, prompt_tokens, ceiling, base,
            )
        return max(0, ceiling)

    return max(floor, min(base, ceiling))
