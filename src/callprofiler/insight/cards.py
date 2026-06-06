"""Карточка контакта-архетипа: читаемый профиль из уже посчитанных фич.

Все данные из contact_archetypes / contacts / calls / analyses. Фильтр по user_id.
Черты — фразами (FEATURE_LABELS), без сырых counts/durations в заголовке (домен-правило).
"""
import json
import sqlite3
from collections import Counter


def build_card(conn, user_id, contact_id):
    """Собрать карточку контакта. None если архетип не посчитан (нет archetypes-fit)."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT archetype_label, membership, confidence, distinctive_dims "
        "FROM contact_archetypes WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchone()
    if row is None:
        return None

    name_row = conn.execute(
        "SELECT COALESCE(display_name, guessed_name, 'неизвестный') AS nm "
        "FROM contacts WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchone()
    name = name_row["nm"] if name_row else "неизвестный"

    try:
        _dims = json.loads(row["distinctive_dims"] or "[]")
    except (ValueError, TypeError):
        _dims = []
    traits = [d.get("phrase") for d in _dims if isinstance(d, dict) and d.get("phrase")]

    last_seen = conn.execute(
        "SELECT MAX(call_datetime) FROM calls WHERE user_id = ? AND contact_id = ?",
        (user_id, contact_id),
    ).fetchone()[0]

    topic_counter = Counter()
    for (kt,) in conn.execute(
        "SELECT a.key_topics FROM analyses a JOIN calls c ON c.call_id = a.call_id "
        "WHERE c.user_id = ? AND c.contact_id = ?",
        (user_id, contact_id),
    ).fetchall():
        try:
            for t in json.loads(kt or "[]"):
                topic_counter[t] += 1
        except (ValueError, TypeError):
            continue
    topics = [t for t, _ in topic_counter.most_common(3)]

    note_row = conn.execute(
        "SELECT COALESCE(a.hook, '') AS hook, COALESCE(a.summary, '') AS summary "
        "FROM analyses a JOIN calls c ON c.call_id = a.call_id "
        "WHERE c.user_id = ? AND c.contact_id = ? "
        "AND (COALESCE(a.hook,'') != '' OR COALESCE(a.summary,'') != '') "
        "ORDER BY a.call_id DESC LIMIT 1",
        (user_id, contact_id),
    ).fetchone()
    note = (note_row["hook"] or note_row["summary"]) if note_row else ""

    return {
        "contact_id": contact_id,
        "name": name,
        "archetype": row["archetype_label"],
        "membership": row["membership"],
        "confidence": row["confidence"],
        "traits": traits,
        "topics": topics,
        "last_seen": last_seen,
        "note": note,
    }
