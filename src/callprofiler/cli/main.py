# -*- coding: utf-8 -*-
"""
main.py — точка входа CLI для CallProfiler.

Использование:
  python -m callprofiler watch                         # watchdog + обработка
  python -m callprofiler process <file> --user ID      # обработать один файл
  python -m callprofiler reprocess                     # повторить ошибки
  python -m callprofiler add-user ID ...               # добавить пользователя
  python -m callprofiler digest <user> [--days N]      # дайджест звонков
  python -m callprofiler search <query> --user ID      # FTS5 поиск
  python -m callprofiler promises --user ID            # показать открытые promises
  python -m callprofiler inspect-schema                # вывести схему БД
  python -m callprofiler analytics --user ID           # статистика
  python -m callprofiler status                        # состояние очереди
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

from callprofiler.cli.utils import setup_logging as _setup_logging
from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo  # noqa: F811


# ── Команды ────────────────────────────────────────────────────────────────
# T-01: НЕ импортировать command-модули на верхнем уровне — они тянут
# torch/pyannote/transformers транзитивно (через orchestrator/watcher/etc),
# что делает `--help`/`doctor` медленными и ломает их на окружении без ML-стека.
# Импорт — лениво, внутри dispatch (module, func) в main().

_DISPATCH: dict[str, tuple[str, str]] = {
    "watch": ("callprofiler.cli.commands.admin", "cmd_watch"),
    "process": ("callprofiler.cli.commands.admin", "cmd_process"),
    "reprocess": ("callprofiler.cli.commands.admin", "cmd_reprocess"),
    "bootstrap": ("callprofiler.cli.commands.admin", "cmd_bootstrap"),
    "add-user": ("callprofiler.cli.commands.admin", "cmd_add_user"),
    "status": ("callprofiler.cli.commands.admin", "cmd_status"),
    "dashboard": ("callprofiler.cli.commands.admin", "cmd_dashboard"),
    "bot": ("callprofiler.cli.commands.admin", "cmd_bot"),

    "extract-names": ("callprofiler.cli.commands.bulk", "cmd_extract_names"),
    "bulk-load": ("callprofiler.cli.commands.bulk", "cmd_bulk_load"),
    "bulk-enrich": ("callprofiler.cli.commands.bulk", "cmd_bulk_enrich"),
    "audio-migrate": ("callprofiler.cli.commands.bulk", "cmd_audio_migrate"),
    "canary-analyze": ("callprofiler.cli.commands.bulk", "cmd_canary_analyze"),

    "digest": ("callprofiler.cli.commands.query", "cmd_digest"),
    "search": ("callprofiler.cli.commands.query", "cmd_search"),
    "promises": ("callprofiler.cli.commands.query", "cmd_promises"),
    "inspect-schema": ("callprofiler.cli.commands.query", "cmd_inspect_schema"),
    "backfill-events": ("callprofiler.cli.commands.query", "cmd_backfill_events"),
    "backfill-calltypes": ("callprofiler.cli.commands.query", "cmd_backfill_calltypes"),
    "analytics": ("callprofiler.cli.commands.query", "cmd_analytics"),

    "rebuild-summaries": ("callprofiler.cli.commands.contacts", "cmd_rebuild_summaries"),
    "rebuild-cards": ("callprofiler.cli.commands.contacts", "cmd_rebuild_cards"),
    "book-chapter": ("callprofiler.cli.commands.contacts", "cmd_book_chapter"),
    "person-profile": ("callprofiler.cli.commands.contacts", "cmd_person_profile"),
    "profile-all": ("callprofiler.cli.commands.contacts", "cmd_profile_all"),

    "biography-run": ("callprofiler.cli.commands.biography", "cmd_biography_run"),
    "biography-status": ("callprofiler.cli.commands.biography", "cmd_biography_status"),
    "biography-export": ("callprofiler.cli.commands.biography", "cmd_biography_export"),

    "graph-backfill": ("callprofiler.cli.commands.graph", "cmd_graph_backfill"),
    "reenrich-v2": ("callprofiler.cli.commands.graph", "cmd_reenrich_v2"),
    "graph-stats": ("callprofiler.cli.commands.graph", "cmd_graph_stats"),
    "graph-replay": ("callprofiler.cli.commands.graph", "cmd_graph_replay"),
    "entity-merge": ("callprofiler.cli.commands.graph", "cmd_entity_merge"),
    "entity-unmerge": ("callprofiler.cli.commands.graph", "cmd_entity_unmerge"),
    "graph-audit": ("callprofiler.cli.commands.graph", "cmd_graph_audit"),
    "graph-health": ("callprofiler.cli.commands.graph", "cmd_graph_health"),

    "features-build": ("callprofiler.cli.commands.insight", "cmd_features_build"),
    "archetypes-fit": ("callprofiler.cli.commands.insight", "cmd_archetypes_fit"),
    "person-archetype": ("callprofiler.cli.commands.insight", "cmd_person_archetype"),
    "person-link": ("callprofiler.cli.commands.insight", "cmd_person_link"),
    "mentions-build": ("callprofiler.cli.commands.insight", "cmd_mentions_build"),
    "quarterly-report": ("callprofiler.cli.commands.insight", "cmd_quarterly_report"),
    "promise-outcomes": ("callprofiler.cli.commands.insight", "cmd_promise_outcomes"),
    "age-estimate": ("callprofiler.cli.commands.insight", "cmd_age_estimate"),
    "age-style": ("callprofiler.cli.commands.insight", "cmd_age_style"),
    "spotcheck-sample": ("callprofiler.cli.commands.insight", "cmd_spotcheck_sample"),
    "calibrate-risk": ("callprofiler.cli.commands.insight", "cmd_calibrate_risk"),
    "mirror-build": ("callprofiler.cli.commands.insight", "cmd_mirror_build"),
    "tiers-recompute": ("callprofiler.cli.commands.insight", "cmd_tiers_recompute"),
    "deep-extract": ("callprofiler.cli.commands.insight", "cmd_deep_extract"),

    "doctor": ("callprofiler.cli.commands.doctor", "cmd_doctor"),

    "daily-report": ("callprofiler.cli.commands.deliver", "cmd_daily_report"),
    "obligations-digest": ("callprofiler.cli.commands.deliver", "cmd_obligations_digest"),
    "on-this-day": ("callprofiler.cli.commands.deliver", "cmd_on_this_day"),
    "reminders-due": ("callprofiler.cli.commands.deliver", "cmd_reminders_due"),

    "ask": ("callprofiler.cli.commands.ask", "cmd_ask"),

    "backup": ("callprofiler.cli.commands.backup", "cmd_backup"),
    "verify-backup": ("callprofiler.cli.commands.backup", "cmd_verify_backup"),
    "restore": ("callprofiler.cli.commands.backup", "cmd_restore"),
}


def _build_parser() -> argparse.ArgumentParser:
    """Построить argparse парсер со всеми подкомандами."""
    parser = argparse.ArgumentParser(
        prog="callprofiler",
        description="CallProfiler — локальная система анализа телефонных звонков",
    )
    parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Путь к конфигурационному файлу (по умолчанию: configs/base.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Подробное логирование (DEBUG)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        metavar="PATH",
        help="Путь к файлу лога (переопределяет cfg.log_file)",
    )

    sub = parser.add_subparsers(dest="command", metavar="КОМАНДА")
    sub.required = True

    # ── watch ────────────────────────────────────────────────
    p_watch = sub.add_parser(
        "watch",
        help="Запустить watchdog: мониторинг папок + автообработка",
    )
    p_watch.add_argument(
        "--once", action="store_true",
        help="Один цикл (scan→обработка→cleanup) и выход — для тестового прогона",
    )

    # ── process ──────────────────────────────────────────────
    p_process = sub.add_parser(
        "process",
        help="Обработать один аудиофайл",
    )
    p_process.add_argument("file", help="Путь к аудиофайлу")
    p_process.add_argument(
        "--user", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_process.add_argument(
        "--force", action="store_true",
        help="Переобработать, даже если файл уже в БД (заменит транскрипт)",
    )

    # ── reprocess ────────────────────────────────────────────
    sub.add_parser(
        "reprocess",
        help="Повторить звонки с ошибками (retry_count < max_retries)",
    )

    # ── bootstrap ────────────────────────────────────────────
    p_boot = sub.add_parser(
        "bootstrap",
        help="Создать папки/БД и завести пользователя по умолчанию (чистая машина)",
    )
    p_boot.add_argument("--user-id", dest="user_id", default="me", help="ID пользователя (default: me)")
    p_boot.add_argument("--display-name", default="Сергей Медведев", help="Отображаемое имя")
    p_boot.add_argument("--incoming", default="C:\\calls\\in", metavar="DIR", help="Папка входящих аудио")
    p_boot.add_argument("--sync-dir", default="C:\\calls\\sync", metavar="DIR", help="Папка caller cards")
    p_boot.add_argument("--ref-audio", default="C:\\pro\\mbot\\ref\\manager.wav", metavar="FILE", help="Эталон голоса (для будущей диаризации)")
    p_boot.add_argument("--telegram-chat-id", default=None, metavar="ID", help="Telegram chat_id")

    # ── add-user ─────────────────────────────────────────────
    p_add = sub.add_parser(
        "add-user",
        help="Добавить нового пользователя",
    )
    p_add.add_argument("user_id", help="Уникальный ID пользователя (латиница)")
    p_add.add_argument("--display-name", help="Отображаемое имя")
    p_add.add_argument(
        "--incoming", required=True, metavar="DIR",
        help="Папка для входящих аудиофайлов",
    )
    p_add.add_argument(
        "--ref-audio", required=True, metavar="FILE",
        help="Эталонная запись голоса (.wav) для диаризации",
    )
    p_add.add_argument(
        "--sync-dir", required=True, metavar="DIR",
        help="Папка для caller cards (FolderSync → телефон)",
    )
    p_add.add_argument(
        "--telegram-chat-id", metavar="ID",
        help="Telegram chat_id для уведомлений",
    )

    # ── digest ───────────────────────────────────────────────
    p_digest = sub.add_parser(
        "digest",
        help="Показать дайджест звонков по priority",
    )
    p_digest.add_argument("user_id", help="Идентификатор пользователя")
    p_digest.add_argument(
        "--days", type=int, default=7,
        help="Период дайджеста в днях (по умолчанию: 7)",
    )

    # ── status ───────────────────────────────────────────────
    sub.add_parser(
        "status",
        help="Показать состояние очереди обработки",
    )

    # ── extract-names ─────────────────────────────────────────
    p_extract = sub.add_parser(
        "extract-names",
        help="Угадать имена собеседников из транскриптов (для контактов без display_name)",
    )
    p_extract.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_extract.add_argument(
        "--dry-run", action="store_true",
        help="Показать результат без записи в БД",
    )

    # ── bulk-load ──────────────────────────────────────────────
    p_bulk = sub.add_parser(
        "bulk-load",
        help="Массовая загрузка .txt транскриптов в БД",
    )
    p_bulk.add_argument(
        "folder", help="Папка с .txt файлами транскриптов",
    )
    p_bulk.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── bulk-enrich ────────────────────────────────────────────
    p_enrich = sub.add_parser(
        "bulk-enrich",
        help="LLM-анализ для всех звонков без анализа",
    )
    p_enrich.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_enrich.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум файлов для обработки (0 = все)",
    )

    # ── rebuild-summaries ──────────────────────────────────────
    p_rebuild_sum = sub.add_parser(
        "rebuild-summaries",
        help="Пересчитать contact_summaries (взвешенный риск, события, совет)",
    )
    p_rebuild_sum.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── rebuild-cards ──────────────────────────────────────────
    p_rebuild_cards = sub.add_parser(
        "rebuild-cards",
        help="Пересоздать caller cards (<=512 байт) в sync_dir",
    )
    p_rebuild_cards.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── search ────────────────────────────────────────────────────
    p_search = sub.add_parser(
        "search",
        help="FTS5 поиск по транскриптам",
    )
    p_search.add_argument(
        "query", help="Текст для поиска",
    )
    p_search.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── promises ───────────────────────────────────────────────────
    p_promises = sub.add_parser(
        "promises",
        help="Показать открытые promises, сгруппированные по контакту",
    )
    p_promises.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── inspect-schema ─────────────────────────────────────────────
    sub.add_parser(
        "inspect-schema",
        help="Вывести реальную схему всех таблиц БД (PRAGMA table_info)",
    )

    # ── backfill-events ────────────────────────────────────────────
    p_backfill = sub.add_parser(
        "backfill-events",
        help="Заполнить пропущенные события из существующих анализов",
    )
    p_backfill.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── backfill-calltypes ─────────────────────────────────────────
    p_backfill_ct = sub.add_parser(
        "backfill-calltypes",
        help="Заполнить call_type в analyses из raw_response JSON",
    )
    p_backfill_ct.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── analytics ──────────────────────────────────────────────────
    p_analytics = sub.add_parser(
        "analytics",
        help="Аналитика по контактам, звонкам, событиям и promises",
    )
    p_analytics.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── bot ────────────────────────────────────────────────────────
    sub.add_parser(
        "bot",
        help="Запустить Telegram-бот (long polling, requires TELEGRAM_BOT_TOKEN)",
    )

    # ── biography-run ──────────────────────────────────────────────
    p_bio_run = sub.add_parser(
        "biography-run",
        help="Запустить многодневный 8-проходный конвейер построения биографии",
    )
    p_bio_run.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_bio_run.add_argument(
        "--passes", default="", metavar="p1,p2,...",
        help="Список проходов через запятую; пусто = все 8 по порядку "
             "(p1_scene,p2_entities,p3_threads,p4_arcs,"
             "p5_portraits,p6_chapters,p7_book,p8_editorial)",
    )
    p_bio_run.add_argument(
        "--max-retries", type=int, default=5, dest="max_retries",
        help="Максимум попыток LLM-запроса перед отказом (по умолчанию: 5)",
    )

    # ── graph-backfill ─────────────────────────────────────────────
    p_graph_bf = sub.add_parser(
        "graph-backfill",
        help="Наполнить Knowledge Graph из существующих v2 analyses",
    )
    p_graph_bf.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_graph_bf.add_argument(
        "--schema", default="v2", metavar="VERSION",
        help="Фильтр по schema_version: v2 (по умолчанию) или all",
    )

    # ── reenrich-v2 ────────────────────────────────────────────────
    p_reenrich = sub.add_parser(
        "reenrich-v2",
        help="Переобогатить v1 analyses через LLM для получения v2 (entities/facts)",
    )
    p_reenrich.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_reenrich.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум записей (0 = все)",
    )

    # ── graph-replay ───────────────────────────────────────────────
    p_graph_replay = sub.add_parser(
        "graph-replay",
        help="Пересоздать Knowledge Graph из v2 analyses (идемпотентно)",
    )
    p_graph_replay.add_argument(
        "--user", dest="user", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_graph_replay.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Максимум calls для обработки (для тестирования)",
    )

    # ── entity-merge ───────────────────────────────────────────────
    p_entity_merge = sub.add_parser(
        "entity-merge",
        help="Слить дублирующую сущность в каноническую (Knowledge Graph)",
    )
    p_entity_merge.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_entity_merge.add_argument(
        "--canonical", dest="canonical_id", type=int, required=True,
        metavar="ID", help="ID канонической сущности",
    )
    p_entity_merge.add_argument(
        "--duplicate", dest="duplicate_id", type=int, required=True,
        metavar="ID", help="ID дублирующей сущности (будет архивирована)",
    )
    p_entity_merge.add_argument(
        "--score", type=float, default=0.0, help="Оценка схожести (0-1)",
    )
    p_entity_merge.add_argument(
        "--reason", default="", help="Комментарий к слиянию",
    )
    p_entity_merge.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Показать предпросмотр без записи",
    )
    p_entity_merge.add_argument(
        "--loop", action="store_true",
        help="Продолжать слияние пока есть кандидаты для canonical_id",
    )

    # ── entity-unmerge ─────────────────────────────────────────────
    p_entity_unmerge = sub.add_parser(
        "entity-unmerge",
        help="Отменить слияние сущностей (восстановить дубликат из snapshot)",
    )
    p_entity_unmerge.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_entity_unmerge.add_argument(
        "--canonical", dest="canonical_id", type=int, required=True, metavar="ID",
    )
    p_entity_unmerge.add_argument(
        "--duplicate", dest="duplicate_id", type=int, required=True, metavar="ID",
    )

    # ── graph-audit ────────────────────────────────────────────────
    p_graph_audit = sub.add_parser(
        "graph-audit",
        help="9 проверок целостности Knowledge Graph",
    )
    p_graph_audit.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )

    # ── book-chapter ────────────────────────────────────────────────
    p_book_chapter = sub.add_parser(
        "book-chapter",
        help="Структурированный граф-профиль сущности для главы биографии",
    )
    p_book_chapter.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_book_chapter.add_argument(
        "entity_id", type=int, metavar="ENTITY_ID",
        help="ID сущности из Knowledge Graph",
    )

    # ── person-profile ─────────────────────────────────────────────
    p_person_profile = sub.add_parser(
        "person-profile",
        help="Сгенерировать психологический профиль для одной сущности",
    )
    p_person_profile.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_person_profile.add_argument(
        "entity_id", type=int, metavar="ENTITY_ID",
    )
    p_person_profile.add_argument(
        "--json", action="store_true", dest="json",
        help="Выводить полный профиль в JSON",
    )

    # ── profile-all ────────────────────────────────────────────────
    p_profile_all = sub.add_parser(
        "profile-all",
        help="Сгенерировать профили для всех сущностей пользователя",
    )
    p_profile_all.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
    )
    p_profile_all.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум сущностей (0 = все)",
    )

    # ── graph-health ───────────────────────────────────────────────
    p_graph_health = sub.add_parser(
        "graph-health",
        help="4 stability checks: replay rejection, audit, entity_metrics, bs_thresholds",
    )
    p_graph_health.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── dashboard ──────────────────────────────────────────────────
    p_dashboard = sub.add_parser(
        "dashboard",
        help="Запустить real-time web dashboard для мониторинга pipeline",
    )
    p_dashboard.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_dashboard.add_argument(
        "--port", type=int, default=8765, metavar="PORT",
        help="Порт веб-сервера (по умолчанию: 8765)",
    )
    p_dashboard.add_argument(
        "--host", default="127.0.0.1", metavar="HOST",
        help="Хост веб-сервера (по умолчанию: 127.0.0.1)",
    )

    # ── graph-stats ────────────────────────────────────────────────
    p_graph_stats = sub.add_parser(
        "graph-stats",
        help="Статистика Knowledge Graph: entities, relations, facts",
    )
    p_graph_stats.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── insight: features-build / archetypes-fit ───────────────────
    p_feat = sub.add_parser(
        "features-build",
        help="Insight: посчитать по-контактные поведенческие фичи",
    )
    p_feat.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_arch = sub.add_parser(
        "archetypes-fit",
        help="Insight: кластеризовать контакты в архетипы",
    )
    p_arch.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_arch.add_argument(
        "--version", default="arch-v1", metavar="VER",
        help="Версия модели архетипов (по умолчанию: arch-v1)",
    )
    p_person_link = sub.add_parser(
        "person-link",
        help="Insight: перестроить связку graph-entity ↔ contact (entity_contact_map)",
    )
    p_person_link.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_person_link.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Посчитать связки без записи",
    )
    p_mentions_build = sub.add_parser(
        "mentions-build",
        help="Insight: перестроить граф упоминаний contact->contact (mention_edges)",
    )
    p_mentions_build.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_qreport = sub.add_parser(
        "quarterly-report",
        help="D3: квартальный LLM-отчёт о социальной вселенной (только агрегаты в промпте)",
    )
    p_qreport.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_qreport.add_argument(
        "--quarter", dest="quarter", required=True, metavar="YYYY-Qn",
        help="Квартал, например 2026-Q2",
    )
    p_qreport.add_argument(
        "--force", action="store_true",
        help="Игнорировать кэш insight_reports и пересчитать",
    )
    p_promise_out = sub.add_parser(
        "promise-outcomes",
        help="B3: исход каждого обещания kept/late/broken/unknown (det; --llm донасыщает unknown)",
    )
    p_promise_out.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_promise_out.add_argument(
        "--llm", action="store_true",
        help="Добавить LLM-пасс для unknown (llama-server должен быть жив, ASR не идти)",
    )
    p_promise_out.add_argument(
        "--llm-limit", dest="llm_limit", type=int, default=200, metavar="N",
        help="Максимум LLM-вызовов за прогон (по умолчанию 200)",
    )
    p_person_arch = sub.add_parser(
        "person-archetype",
        help="Insight: карточка архетипа контакта",
    )
    p_person_arch.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_person_arch.add_argument(
        "--contact", dest="contact_id", required=True, type=int, metavar="CONTACT_ID",
        help="ID контакта",
    )
    p_person_arch.add_argument(
        "--json", action="store_true", help="Вывести как JSON",
    )
    p_age = sub.add_parser(
        "age-estimate",
        help="Insight: оценить возраст контактов (маркеры+якоря; --llm в LLM-окне)",
    )
    p_age.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_age.add_argument(
        "--contact", dest="contact_id", type=int, default=None, metavar="CONTACT_ID",
        help="Только один контакт (по умолчанию: все)",
    )
    p_age.add_argument(
        "--llm", action="store_true",
        help="Добавить LLM-пасс (llama-server должен быть жив, ASR не идти)",
    )
    p_age_style = sub.add_parser(
        "age-style",
        help="Insight: стилометрическая оценка возраста (no-ML, без GPU/LLM)",
    )
    p_age_style.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_age_style.add_argument(
        "--stale-only", dest="stale_only", action="store_true",
        help="Только контакты со звонками новее последнего пересчёта",
    )

    # ── biography-status ───────────────────────────────────────────
    p_bio_status = sub.add_parser(
        "biography-status",
        help="Состояние checkpoint'ов всех 8 проходов биографии",
    )
    p_bio_status.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── audio-migrate ──────────────────────────────────────────────
    p_audio_migrate = sub.add_parser(
        "audio-migrate",
        help="Мигрировать оригиналы из flat originals/ в originals/YYYY/MM/ (идемпотентно)",
    )
    p_audio_migrate.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_audio_migrate.add_argument(
        "--dry-run", action="store_true",
        help="Показать что будет перемещено без реальных изменений",
    )
    p_audio_migrate.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Максимум файлов (0 = все)",
    )

    # ── biography-export ───────────────────────────────────────────
    p_bio_export = sub.add_parser(
        "biography-export",
        help="Экспортировать последний собранный book в markdown-файл",
    )
    p_bio_export.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_bio_export.add_argument(
        "--out", required=True, metavar="FILE",
        help="Путь к выходному .md файлу",
    )

    # ── spotcheck-sample ─────────────────────────────────────────
    p_spotcheck = sub.add_parser(
        "spotcheck-sample",
        help="Стратифицированная выборка звонков для ручной проверки WER/ролей/обещаний",
    )
    p_spotcheck.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_spotcheck.add_argument(
        "--n", type=int, default=25, metavar="N",
        help="Размер выборки (по умолчанию 25)",
    )
    p_spotcheck.add_argument(
        "--seed", type=int, default=0, metavar="SEED",
        help="Seed случайной выборки (для воспроизводимости)",
    )
    p_spotcheck.add_argument(
        "--out", default=None, metavar="FILE",
        help="Путь к выходному .md файлу (по умолчанию C:\\calls\\spotcheck.md)",
    )

    # ── doctor ───────────────────────────────────────────────────
    p_doctor = sub.add_parser(
        "doctor",
        help="Преполётная проверка окружения/схемы/моделей (M1)",
    )
    p_doctor.add_argument(
        "--user", dest="user_id", required=False, default=None, metavar="USER_ID",
        help="Не используется напрямую — чеки покрывают всех users в БД",
    )
    p_doctor.add_argument(
        "--send", action="store_true",
        help="F6: отправить отчёт (🟢/🔴 + чеки) в Telegram всем users с telegram_chat_id",
    )

    # ── canary-analyze ─────────────────────────────────────────────
    p_canary = sub.add_parser(
        "canary-analyze",
        help="M4: сравнить json_mode=False vs True на выборке звонков (ничего не пишет в БД)",
    )
    p_canary.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_canary.add_argument(
        "--n", type=int, default=50, metavar="N",
        help="Размер выборки (по умолчанию 50)",
    )
    p_canary.add_argument(
        "--seed", type=int, default=0, metavar="SEED",
        help="Seed случайной выборки (для воспроизводимости)",
    )
    p_canary.add_argument(
        "--out", default=None, metavar="FILE",
        help="Путь к выходному .md файлу (по умолчанию C:\\calls\\canary-json.md)",
    )

    # ── obligations-digest ───────────────────────────────────────────
    p_oblig = sub.add_parser(
        "obligations-digest",
        help="A1: реестр обязательств — просроченные/открытые promise+debt в обе стороны",
    )
    p_oblig.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_oblig.add_argument(
        "--out", default=None, metavar="FILE",
        help="Путь к выходному .md файлу (по умолчанию — вывод в консоль)",
    )

    # ── reminders-due (F2) ───────────────────────────────────────────
    p_remdue = sub.add_parser(
        "reminders-due",
        help="F2: печать ждущих/просроченных напоминаний (ручной прогон без бота)",
    )
    p_remdue.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── daily-report (F5) ──────────────────────────────────────────────
    p_daily = sub.add_parser(
        "daily-report",
        help="F5: вечерний отчёт дня (звонки/обязательства/завтра/ошибки/воспоминание)",
    )
    p_daily.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_daily.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="Дата отчёта (по умолчанию — сегодня)",
    )
    p_daily.add_argument(
        "--send", action="store_true",
        help="Отправить в Telegram (иначе — печать в stdout)",
    )

    # ── on-this-day (D1) ─────────────────────────────────────────────
    p_otd = sub.add_parser(
        "on-this-day",
        help="D1: годовщины — сцены той же даты в прошлые годы (importance>70)",
    )
    p_otd.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_otd.add_argument(
        "--send", action="store_true",
        help="Отправить в Telegram (иначе — печать в stdout)",
    )

    # ── ask ──────────────────────────────────────────────────────────
    p_ask = sub.add_parser(
        "ask",
        help="A2: вопрос к архиву звонков (FTS5 + LLM-синтез со ссылками [n])",
    )
    p_ask.add_argument("question", help="Вопрос на русском языке")
    p_ask.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_ask.add_argument(
        "--k", type=int, default=8, metavar="K",
        help="Число фрагментов для синтеза (по умолчанию 8)",
    )

    # ── calibrate-risk ───────────────────────────────────────────────
    p_calib_risk = sub.add_parser(
        "calibrate-risk",
        help="A4: перцентильные пороги risk_score (p50/p85), отдельно от BS-index",
    )
    p_calib_risk.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── mirror-build ───────────────────────────────────────────────
    p_mirror = sub.add_parser(
        "mirror-build",
        help="A3: досье владельца — обещания/риск-тренд/зависимость/регистр речи",
    )
    p_mirror.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── tiers-recompute (F8) ─────────────────────────────────────────
    p_tiers = sub.add_parser(
        "tiers-recompute",
        help="F8: Эббингауз-тиры контактов (core/active/warm/cold/archive)",
    )
    p_tiers.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )

    # ── deep-extract (M8) ────────────────────────────────────────────
    p_deep = sub.add_parser(
        "deep-extract",
        help="M8: map-reduce извлечение обязательств/фактов по длинным звонкам (LLM-окно)",
    )
    p_deep.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
    )
    p_deep.add_argument(
        "--min-duration", dest="min_duration", type=int, default=600, metavar="SEC",
        help="Минимальная длительность звонка в секундах (по умолчанию 600)",
    )
    p_deep.add_argument(
        "--min-priority", dest="min_priority", type=int, default=None, metavar="N",
        help="Только звонки с analyses.priority >= N (по умолчанию — без фильтра)",
    )
    p_deep.add_argument(
        "--limit", type=int, default=100, metavar="N",
        help="Максимум звонков за прогон (по умолчанию 100)",
    )
    p_deep.add_argument(
        "--force", action="store_true",
        help="Пересканировать звонки, уже пройденные текущей версией промпта",
    )

    # ── backup / verify-backup / restore (T-20) ─────────────────────
    p_backup = sub.add_parser(
        "backup",
        help="T-20: верифицированный снимок БД (online backup API)",
    )
    p_backup.add_argument(
        "--out", dest="out", default=None, metavar="DIR",
        help="Каталог снимков (по умолчанию: <data_dir>/backups)",
    )
    p_backup.add_argument(
        "--kind", default="manual", choices=("manual", "daily", "weekly"),
        help="Метка снимка в манифесте (по умолчанию: manual)",
    )
    p_backup.add_argument(
        "--retention-daily", dest="retention_daily", type=int, default=7, metavar="N",
        help="Сколько последних снимков хранить безусловно (по умолчанию 7)",
    )
    p_backup.add_argument(
        "--retention-weekly", dest="retention_weekly", type=int, default=4, metavar="N",
        help="Сколько недельных снимков хранить сверх daily (по умолчанию 4)",
    )

    p_verify = sub.add_parser(
        "verify-backup",
        help="T-20: проверить снимок (quick_check + foreign_key_check + sha256 + счётчики)",
    )
    p_verify.add_argument("path", help="Путь к файлу снимка .db")

    p_restore = sub.add_parser(
        "restore",
        help="T-20: восстановить снимок в указанный путь",
    )
    p_restore.add_argument(
        "--to", required=True, metavar="PATH",
        help="Куда восстановить БД",
    )
    p_restore.add_argument(
        "--from", dest="from_path", default=None, metavar="PATH",
        help="Какой снимок восстанавливать (по умолчанию — самый свежий из --out/<data_dir>/backups)",
    )
    p_restore.add_argument(
        "--out", dest="out", default=None, metavar="DIR",
        help="Каталог снимков для поиска --from по умолчанию и для авто-снимка при --overwrite",
    )
    p_restore.add_argument(
        "--overwrite", action="store_true",
        help="Разрешить перезапись существующего файла назначения (снимет его состояние перед заменой)",
    )

    return parser


def main() -> None:
    """Главная функция CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    entry = _DISPATCH.get(args.command)
    if entry is None:
        parser.print_help()
        sys.exit(1)

    module_name, func_name = entry
    handler = getattr(importlib.import_module(module_name), func_name)

    try:
        exit_code = handler(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
    except Exception as exc:
        logging.getLogger(__name__).error("Неожиданная ошибка: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
