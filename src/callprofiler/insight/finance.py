"""Financial exposure — display-only axis (B7, ozalupennieStrategic5.md).

Reads existing `events` (promise/debt), extracts amounts from payload+quote
text. No new extraction pass, no graph/replay writes — pure display formatting
over data other passes already collected.
"""
import re

_RE_AMOUNT = re.compile(
    r"(\d[\d\s]{0,9}(?:[.,]\d{1,2})?)\s*(тыс\w*|к\b|млн|миллион\w*)?\s*"
    r"(руб\w*|₽|р\b|доллар\w*|\$|бакс\w*|евро|€)",
    re.I,
)

_MULTIPLIERS = (("тыс", 1e3), ("к", 1e3), ("млн", 1e6), ("миллион", 1e6))
_CURRENCIES = (
    ("руб", "RUB"), ("₽", "RUB"), ("р", "RUB"),
    ("доллар", "USD"), ("$", "USD"), ("бакс", "USD"),
    ("евро", "EUR"), ("€", "EUR"),
)
_CURRENCY_SIGNS = {"RUB": "₽", "USD": "$", "EUR": "€"}
_ROUND_UNITS = ((1_000_000, "млн"), (1_000, "тыс"))


def _multiplier(raw: str | None) -> float:
    if not raw:
        return 1.0
    raw = raw.lower()
    for prefix, mult in _MULTIPLIERS:
        if raw.startswith(prefix):
            return mult
    return 1.0


def _currency(raw: str) -> str:
    raw = raw.lower()
    for prefix, code in _CURRENCIES:
        if raw.startswith(prefix):
            return code
    return "RUB"  # unreachable — regex alternation уже ограничена этим же списком


def extract_amounts(text: str) -> list[tuple[float, str]]:
    """Все суммы в тексте: [(число, валюта), ...].

    Только цифрами — «сорок тысяч» словами не ловится (regex, не NLP).
    """
    out = []
    for m in _RE_AMOUNT.finditer(text or ""):
        num_raw = m.group(1).replace(" ", "").replace(",", ".")
        try:
            num = float(num_raw)
        except ValueError:
            continue
        out.append((num * _multiplier(m.group(2)), _currency(m.group(3))))
    return out


def _event_max_by_currency(payload: str, quote: str | None) -> dict[str, float]:
    """Максимум по валюте среди сумм в payload+quote ОДНОГО события.

    payload и quote часто пересказывают один и тот же факт двумя текстами —
    берём максимум, не сумму (иначе одно событие задвоило бы свой вклад).
    """
    out: dict[str, float] = {}
    for value, currency in extract_amounts(payload) + extract_amounts(quote or ""):
        out[currency] = max(out.get(currency, 0.0), value)
    return out


def finance_exposure(conn, user_id: str, contact_id: int) -> dict | None:
    """{"RUB": [low, high], ...} по открытым promise/debt контакта.

    low = крупнейшая разовая сумма среди событий, high = сумма разовых
    максимумов по всем событиям (см. _event_max_by_currency). Нет сумм в
    открытых событиях -> None.
    """
    rows = conn.execute(
        """SELECT payload, source_quote FROM events
            WHERE user_id = ? AND contact_id = ? AND event_type IN ('promise', 'debt')
              AND status = 'open'""",
        (user_id, contact_id),
    ).fetchall()

    totals: dict[str, float] = {}
    maxima: dict[str, float] = {}
    for row in rows:
        for currency, value in _event_max_by_currency(row["payload"], row["source_quote"]).items():
            totals[currency] = totals.get(currency, 0.0) + value
            maxima[currency] = max(maxima.get(currency, 0.0), value)

    if not totals:
        return None
    return {cur: [maxima[cur], totals[cur]] for cur in totals}


def _scale_pair(low: float, high: float) -> tuple[str, str, str]:
    """low/high в единицах, выбранных по high; округление до 1 знака, без «.0»."""
    threshold, suffix = 1.0, ""
    for t, s in _ROUND_UNITS:
        if high >= t:
            threshold, suffix = float(t), s
            break

    def fmt(v: float) -> str:
        scaled = v / threshold
        s = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return s or "0"

    return fmt(low), fmt(high), suffix


def format_amount_range(low: float, high: float, currency: str) -> str:
    """«~40–90 тыс ₽» (или «~2 тыс $» при low==high) — одна валюта."""
    sign = _CURRENCY_SIGNS.get(currency, currency)
    low_s, high_s, suffix = _scale_pair(low, high)
    unit = f" {suffix}" if suffix else ""
    if low_s == high_s:
        return f"~{low_s}{unit} {sign}"
    return f"~{low_s}–{high_s}{unit} {sign}"


def exposure_phrase(exp: dict | None) -> str:
    """«на нём завязано ~40–90 тыс ₽ + ~2 тыс $» — фраза для досье."""
    if not exp:
        return ""
    parts = [format_amount_range(low, high, cur) for cur, (low, high) in exp.items()]
    return "на нём завязано " + " + ".join(parts)
