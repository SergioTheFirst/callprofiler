# -*- coding: utf-8 -*-
"""
summary_builder.py — построение и обновление contact_summaries.

SummaryBuilder синтезирует полный профиль контакта на основе:
- Всех анализов его звонков (с взвешиванием по свежести)
- Открытых событий (обещания, долги, факты)
- Последних личных взаимодействий
- Выявленных паттернов поведения
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callprofiler.db.repository import Repository

log = logging.getLogger(__name__)


class SummaryBuilder:
    """Синтезирует и обновляет профили контактов (contact_summaries)."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def rebuild_contact(self, contact_id: int) -> None:
        """Пересчитать summary одного контакта.

        Агрегирует данные из:
        1. Анализов звонков (риск, BS-score, top_hook)
        2. Событий (обещания, долги, факты)
        3. Истории взаимодействий (дата, роль, компания)
        """
        contact = self.repo.get_contact(contact_id)
        if not contact:
            log.warning("[summary] Contact %d not found", contact_id)
            return

        user_id = contact.get("user_id")
        if not user_id:
            log.error("[summary] Contact %d has no user_id", contact_id)
            return

        # Получить все звонки этого контакта
        calls = self.repo.get_calls_for_contact(user_id, contact_id)
        if not calls:
            log.debug("[summary] Contact %d has no calls", contact_id)
            return

        # Получить анализы для расчёта risk/bs_score
        analyses = []
        for call in calls:
            analysis = self.repo.get_analysis(call["call_id"])
            if analysis:
                analyses.append({
                    "call_id": call["call_id"],
                    "call_datetime": call.get("call_datetime"),
                    "analysis": analysis,
                })

        # 1. global_risk = взвешенный avg risk_score (свежие важнее, half-life 90 дней)
        global_risk = self._compute_weighted_risk(analyses)

        # 2. avg_bs_score аналогично (из raw_response если есть)
        avg_bs_score = self._compute_weighted_bs_score(analyses)

        # 3. open_promises = JSON из events type='promise' status='open'
        open_promises = self._extract_open_promises(user_id, contact_id)

        # 4. open_debts = JSON из events type='debt' status='open'
        open_debts = self._extract_open_debts(user_id, contact_id)

        # 5. personal_facts = JSON из events type='smalltalk' последние 5
        personal_facts = self._extract_personal_facts(user_id, contact_id)

        # 6. top_hook = hook из последнего business-analysis (если есть)
        top_hook = self._extract_top_hook(analyses)

        # 7. advice = по правилам
        advice = self._generate_advice(global_risk, avg_bs_score, open_debts)

        # 8. contact_role = contact_company_guess из последнего analysis
        contact_role = self._extract_contact_role(analyses)

        # Последняя дата звонка
        last_call_date = None
        if calls:
            last_call = max(calls, key=lambda c: c.get("call_datetime") or "")
            last_call_date = last_call.get("call_datetime")

        # Сохранить summary
        self.repo.save_contact_summary(
            contact_id=contact_id,
            user_id=user_id,
            total_calls=len(calls),
            last_call_date=last_call_date,
            global_risk=global_risk,
            avg_bs_score=avg_bs_score,
            top_hook=top_hook,
            open_promises=open_promises,
            open_debts=open_debts,
            personal_facts=personal_facts,
            contact_role=contact_role,
            advice=advice,
        )

        log.info(
            "[summary] Rebuilt contact_id=%d: risk=%d, bs=%d, calls=%d",
            contact_id, global_risk, avg_bs_score, len(calls),
        )

    def rebuild_all(self, user_id: str) -> None:
        """Пересчитать все контакты пользователя."""
        contacts = self.repo.get_all_contacts_for_user(user_id)
        log.info("[summary] Rebuilding %d contacts for user %s", len(contacts), user_id)

        for contact in contacts:
            try:
                self.rebuild_contact(contact["contact_id"])
            except Exception as e:
                log.error(
                    "[summary] Error rebuilding contact_id=%d: %s",
                    contact["contact_id"], e,
                )
                continue

        log.info("[summary] Completed rebuilding all contacts for %s", user_id)

    def generate_card_text(self, contact_id: int) -> str:
        """Сгенерировать текст карточки ≤512 байт для Android overlay.

        Формат:
            {name} — {role}
            Risk: {score} {emoji}
            Hook: {top_hook}
            • {bullet1}
            • {bullet2}
            • {bullet3}
            💡 {advice}
        """
        summary = self.repo.get_contact_summary(contact_id)
        if not summary:
            return ""

        contact = self.repo.get_contact(contact_id)
        if not contact:
            return ""

        name = contact.get("display_name") or "?"
        role = summary.get("contact_role") or ""
        risk = summary.get("global_risk") or 0
        hook = summary.get("top_hook") or ""
        advice = summary.get("advice") or ""

        # Risk emoji
        risk_emoji = "🟢" if risk < 30 else "🟡" if risk < 70 else "🔴"

        # Bullets (обещания, долги, факты)
        bullets = []
        promises_str = summary.get("open_promises") or ""
        debts_str = summary.get("open_debts") or ""
        facts_str = summary.get("personal_facts") or ""

        if debts_str:
            try:
                debts = json.loads(debts_str)
                if debts and len(debts) > 0:
                    bullets.append(f"💰 {debts[0].get('payload', 'Долг')}")
            except (json.JSONDecodeError, TypeError):
                pass

        if promises_str:
            try:
                promises = json.loads(promises_str)
                if promises and len(promises) > 0:
                    bullets.append(f"🤝 {promises[0].get('payload', 'Обещание')}")
            except (json.JSONDecodeError, TypeError):
                pass

        if facts_str:
            try:
                facts = json.loads(facts_str)
                if facts and len(facts) > 0:
                    bullets.append(f"📝 {facts[0].get('payload', 'Факт')}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Собрать текст
        lines = []
        header = f"{name}"
        if role:
            header += f" — {role}"
        lines.append(header)
        lines.append(f"Risk: {risk} {risk_emoji}")

        if hook:
            lines.append(f"Hook: {hook}")

        for bullet in bullets[:3]:
            lines.append(bullet)

        if advice:
            lines.append(f"💡 {advice}")

        text = "\n".join(lines)

        # Обрезать до 512 байт
        if len(text.encode("utf-8")) > 512:
            text = text[:400] + "..."

        return text

    def write_card(self, contact_id: int, sync_dir: str) -> None:
        """Записать карточку {phone}.txt в sync_dir."""
        contact = self.repo.get_contact(contact_id)
        if not contact:
            log.warning("[summary] Contact %d not found for card write", contact_id)
            return

        phone = contact.get("phone_e164")
        if not phone:
            log.warning("[summary] Contact %d has no phone_e164", contact_id)
            return

        from pathlib import Path

        card_text = self.generate_card_text(contact_id)
        if not card_text:
            log.warning("[summary] No card text for contact_id=%d", contact_id)
            return

        card_path = Path(sync_dir) / f"{phone}.txt"
        card_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            card_path.write_text(card_text, encoding="utf-8")
            log.debug("[summary] Wrote card: %s", card_path)
        except Exception as e:
            log.error("[summary] Failed to write card %s: %s", card_path, e)

    def write_all_cards(self, user_id: str) -> None:
        """Написать все карточки контактов пользователя."""
        user = self.repo.get_user(user_id)
        if not user:
            log.error("[summary] User %s not found", user_id)
            return

        sync_dir = user.get("sync_dir")
        if not sync_dir:
            log.error("[summary] User %s has no sync_dir", user_id)
            return

        contacts = self.repo.get_all_contacts_for_user(user_id)
        log.info("[summary] Writing %d cards for user %s", len(contacts), user_id)

        for contact in contacts:
            try:
                self.write_card(contact["contact_id"], sync_dir)
            except Exception as e:
                log.error(
                    "[summary] Error writing card for contact_id=%d: %s",
                    contact["contact_id"], e,
                )
                continue

    # ── Вспомогательные методы ──────────────────────────────────────────────

    def _compute_weighted_risk(self, analyses: list[dict]) -> int:
        """Взвешенное среднее risk_score (свежие важнее, half-life 90 дней)."""
        if not analyses:
            return 0

        now = datetime.now()
        half_life_days = 90
        weights = []
        risks = []

        for item in analyses:
            call_datetime = item.get("call_datetime")
            if not call_datetime:
                weight = 1.0
            else:
                try:
                    call_dt = datetime.fromisoformat(call_datetime)
                    days_ago = (now - call_dt).days
                    # Exponential decay: weight = 2^(-days_ago / half_life)
                    weight = 2 ** (-days_ago / half_life_days)
                except ValueError:
                    weight = 1.0

            analysis = item.get("analysis", {})
            risk = analysis.get("risk_score", 0)

            weights.append(weight)
            risks.append(risk)

        total_weight = sum(weights)
        if total_weight == 0:
            return int(sum(risks) / len(risks)) if risks else 0

        weighted_sum = sum(w * r for w, r in zip(weights, risks))
        return int(weighted_sum / total_weight)

    def _compute_weighted_bs_score(self, analyses: list[dict]) -> int:
        """Взвешенное среднее BS-score из raw_response."""
        if not analyses:
            return 0

        now = datetime.now()
        half_life_days = 90
        weights = []
        scores = []

        for item in analyses:
            call_datetime = item.get("call_datetime")
            if not call_datetime:
                weight = 1.0
            else:
                try:
                    call_dt = datetime.fromisoformat(call_datetime)
                    days_ago = (now - call_dt).days
                    weight = 2 ** (-days_ago / half_life_days)
                except ValueError:
                    weight = 1.0

            analysis = item.get("analysis", {})
            raw_response = analysis.get("raw_response", "")

            bs_score = 0
            if raw_response:
                try:
                    parsed = json.loads(raw_response)
                    bs_score = parsed.get("bs_score", 0)
                except (json.JSONDecodeError, TypeError):
                    pass

            weights.append(weight)
            scores.append(bs_score)

        total_weight = sum(weights)
        if total_weight == 0:
            return int(sum(scores) / len(scores)) if scores else 0

        weighted_sum = sum(w * s for w, s in zip(weights, scores))
        return int(weighted_sum / total_weight)

    def _extract_open_promises(self, user_id: str, contact_id: int) -> str:
        """JSON из events type='promise' status='open'."""
        events = self.repo.get_open_events(
            user_id, contact_id=contact_id, event_type="promise"
        )
        promises = [
            {
                "id": e.get("id"),
                "who": e.get("who"),
                "payload": e.get("payload"),
                "deadline": e.get("deadline"),
            }
            for e in events
        ]
        return json.dumps(promises, ensure_ascii=False)

    def _extract_open_debts(self, user_id: str, contact_id: int) -> str:
        """JSON из events type='debt' status='open'."""
        events = self.repo.get_open_events(
            user_id, contact_id=contact_id, event_type="debt"
        )
        debts = [
            {
                "id": e.get("id"),
                "payload": e.get("payload"),
                "deadline": e.get("deadline"),
            }
            for e in events
        ]
        return json.dumps(debts, ensure_ascii=False)

    def _extract_personal_facts(self, user_id: str, contact_id: int) -> str:
        """JSON из events type='smalltalk' последние 5."""
        events = self.repo.get_open_events(
            user_id, contact_id=contact_id, event_type="smalltalk"
        )
        # Взять последние 5 (уже отсортированы по created_at DESC)
        facts = [
            {"payload": e.get("payload")}
            for e in events[:5]
        ]
        return json.dumps(facts, ensure_ascii=False)

    def _extract_top_hook(self, analyses: list[dict]) -> str:
        """Hook из последнего business-analysis (если есть)."""
        if not analyses:
            return ""

        # Взять последний анализ
        last_item = analyses[-1]
        analysis = last_item.get("analysis", {})
        raw_response = analysis.get("raw_response", "")

        if not raw_response:
            return ""

        try:
            parsed = json.loads(raw_response)
            hook = parsed.get("hook")
            if hook:
                return str(hook)[:100]  # Макс 100 символов
        except (json.JSONDecodeError, TypeError):
            pass

        return ""

    def _extract_contact_role(self, analyses: list[dict]) -> str:
        """Contact_company_guess из последнего analysis."""
        if not analyses:
            return ""

        last_item = analyses[-1]
        analysis = last_item.get("analysis", {})
        raw_response = analysis.get("raw_response", "")

        if not raw_response:
            return ""

        try:
            parsed = json.loads(raw_response)
            role = parsed.get("contact_company_guess") or parsed.get("contact_role")
            if role:
                return str(role)[:50]
        except (json.JSONDecodeError, TypeError):
            pass

        return ""

    def _generate_advice(self, risk: int, bs_score: int, debts_json: str) -> str:
        """Рекомендации по правилам."""
        advice_list = []

        if risk > 70:
            advice_list.append("Говори первым")

        if bs_score > 60:
            advice_list.append("Осторожно: размытые обещания")

        if debts_json and debts_json != "[]":
            try:
                debts = json.loads(debts_json)
                if debts:
                    advice_list.append("Начни с долга")
            except (json.JSONDecodeError, TypeError):
                pass

        if risk < 30 and bs_score < 30:
            advice_list.append("Надёжный партнёр")

        return "; ".join(advice_list[:2]) if advice_list else "Стандартный контакт"
