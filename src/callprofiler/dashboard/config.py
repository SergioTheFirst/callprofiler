# -*- coding: utf-8 -*-
"""
Dashboard configuration constants.
"""

# Polling
POLL_INTERVAL_SEC = 2  # Check DB every 2 seconds
SSE_KEEPALIVE_SEC = 30  # Send keepalive comment every 30s

# History pagination
HISTORY_PAGE_SIZE = 50
MAX_HISTORY_ITEMS = 1000

# Query timeouts
DB_QUERY_TIMEOUT_SEC = 5

# UI theme colors (CSS variables)
THEME = {
    "bg_primary": "#0a0e1a",
    "bg_secondary": "#1a1f2e",
    "bg_tertiary": "#2a2f3e",
    "text_primary": "#e2e8f0",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "accent_primary": "#3b82f6",
    "accent_secondary": "#8b5cf6",
    "success": "#10b981",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "border": "#334155",
}

# Event type display names
EVENT_TYPE_LABELS = {
    "call_created": "📞 Новый звонок",
    "transcription_complete": "📝 Транскрипция готова",
    "analysis_complete": "🧠 Анализ завершён",
    "entity_updated": "👤 Обновлён профиль",
}

# Entity type icons
ENTITY_TYPE_ICONS = {
    "PERSON": "👤",
    "COMPANY": "🏢",
    "PLACE": "📍",
    "PROJECT": "📋",
    "EVENT": "📅",
}

# Temperament labels (Russian)
TEMPERAMENT_LABELS = {
    "choleric": "Холерик",
    "sanguine": "Сангвиник",
    "phlegmatic": "Флегматик",
    "melancholic": "Меланхолик",
}

# Big Five trait labels
BIG_FIVE_LABELS = {
    "openness": "Открытость опыту",
    "conscientiousness": "Добросовестность",
    "extraversion": "Экстраверсия",
    "agreeableness": "Доброжелательность",
    "neuroticism": "Нейротизм",
}

# Motivation driver labels
MOTIVATION_LABELS = {
    "achievement": "Достижение",
    "power": "Власть",
    "affiliation": "Принадлежность",
    "security": "Безопасность",
}
