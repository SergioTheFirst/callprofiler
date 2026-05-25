from typing import Dict

# ── Dashboard v3.0.0 — Glass-Industrial Command Center ───────────────

VERSION = "3.0.0"

# Polling / SSE
POLL_INTERVAL_SEC = 5
SSE_KEEPALIVE_SEC = 30

# Pagination / limits
HISTORY_PAGE_SIZE = 50
MAX_HISTORY_ITEMS = 1000
DB_QUERY_TIMEOUT_SEC = 5

THEME: Dict[str, str] = {
    "version": VERSION,
    "name": "Glass-Industrial Command Center",

    # Base backgrounds
    "bg_primary": "#060B16",
    "bg_secondary": "#0A1225",
    "bg_tertiary": "#0D1528",
    "bg_panel": "rgba(10, 18, 37, 0.70)",
    "bg_card": "rgba(6, 11, 22, 0.85)",
    "bg_hover": "rgba(255, 255, 255, 0.04)",

    # Text
    "text_primary": "#E8ECF1",
    "text_secondary": "#8B95A5",
    "text_muted": "#4A5568",
    "text_inverse": "#060B16",

    # Accent palette
    "accent_primary": "#00D4C8",
    "accent_secondary": "#00A8FF",
    "accent_tertiary": "#7B61FF",

    # Borders / glass
    "border": "rgba(255, 255, 255, 0.06)",
    "border_strong": "rgba(255, 255, 255, 0.12)",
    "shadow_glow": "rgba(0, 212, 200, 0.15)",

    # Status
    "success": "#00D4C8",
    "warning": "#FFB800",
    "danger": "#FF4757",
    "info": "#00A8FF",
}

# ── UI label maps (retained from v2) ──────────────────────────────────

EVENT_TYPE_LABELS: Dict[str, str] = {
    "call_started": "Начало звонка",
    "call_ended": "Завершение",
    "entity_detected": "Сущность",
    "promise_made": "Обещание",
    "risk_flag": "Риск",
    "mood_shift": "Смена тональности",
    "biography_updated": "Биография",
}

ENTITY_TYPE_ICONS: Dict[str, str] = {
    "person": "👤",
    "organization": "🏢",
    "location": "📍",
    "event": "📅",
    "product": "📦",
    "topic": "🏷️",
    "promise": "🤝",
    "risk": "⚠️",
    "mood": "🎭",
}

TEMPERAMENT_LABELS: Dict[str, str] = {
    "analytical": "Аналитик",
    "driver": "Драйвер",
    "amiable": "Амиабельный",
    "expressive": "Экспрессивный",
    "neutral": "Нейтральный",
}

BIG_FIVE_LABELS: Dict[str, str] = {
    "openness": "Открытость",
    "conscientiousness": "Сознательность",
    "extraversion": "Экстраверсия",
    "agreeableness": "Доброжелательность",
    "neuroticism": "Нейротизм",
}

MOTIVATION_LABELS: Dict[str, str] = {
    "achievement": "Достижение",
    "affiliation": "Привязанность",
    "power": "Власть",
    "security": "Безопасность",
    "autonomy": "Автономия",
    "purpose": "Целеустремлённость",
    "growth": "Рост",
    "recognition": "Признание",
    "stability": "Стабильность",
    "variety": "Разнообразие",
}
