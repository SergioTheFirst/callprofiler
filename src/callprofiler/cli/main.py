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
import logging
import sys
from pathlib import Path

from callprofiler.cli.utils import setup_logging as _setup_logging
from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo  # noqa: F811


# ── Команды ────────────────────────────────────────────────────────────────


# ---- admin commands ----
from callprofiler.cli.commands.admin import (  # noqa: E402
    cmd_watch, cmd_process, cmd_reprocess, cmd_add_user,
    cmd_status, cmd_dashboard, cmd_bot,
)

# ---- bulk commands ----
from callprofiler.cli.commands.bulk import (  # noqa: E402
    cmd_extract_names, cmd_bulk_load, cmd_bulk_enrich,
)

# ---- query commands ----
from callprofiler.cli.commands.query import (  # noqa: E402
    cmd_digest, cmd_search, cmd_promises,
    cmd_inspect_schema, cmd_backfill_events,
    cmd_backfill_calltypes, cmd_analytics,
)

# ---- contact commands ----
from callprofiler.cli.commands.contacts import (  # noqa: E402
    cmd_rebuild_summaries, cmd_rebuild_cards,
    cmd_book_chapter, cmd_person_profile, cmd_profile_all,
)

# ---- biography commands ----
from callprofiler.cli.commands.biography import (  # noqa: E402
    cmd_biography_run, cmd_biography_status, cmd_biography_export,
)

# ---- graph commands ----
from callprofiler.cli.commands.graph import (  # noqa: E402
    cmd_graph_backfill, cmd_reenrich_v2, cmd_graph_stats,
    cmd_graph_replay, cmd_entity_merge, cmd_entity_unmerge,
    cmd_graph_audit, cmd_graph_health,
)

# cmd_graph_audit -> cli/commands/graph.py


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
    sub.add_parser(
        "watch",
        help="Запустить watchdog: мониторинг папок + автообработка",
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

    # ── reprocess ────────────────────────────────────────────
    sub.add_parser(
        "reprocess",
        help="Повторить звонки с ошибками (retry_count < max_retries)",
    )

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

    # ── biography-status ───────────────────────────────────────────
    p_bio_status = sub.add_parser(
        "biography-status",
        help="Состояние checkpoint'ов всех 8 проходов биографии",
    )
    p_bio_status.add_argument(
        "--user", dest="user_id", required=True, metavar="USER_ID",
        help="Идентификатор пользователя",
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

    return parser


def main() -> None:
    """Главная функция CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "watch": cmd_watch,
        "process": cmd_process,
        "reprocess": cmd_reprocess,
        "add-user": cmd_add_user,
        "digest": cmd_digest,
        "status": cmd_status,
        "extract-names": cmd_extract_names,
        "bulk-load": cmd_bulk_load,
        "bulk-enrich": cmd_bulk_enrich,
        "rebuild-summaries": cmd_rebuild_summaries,
        "rebuild-cards": cmd_rebuild_cards,
        "search": cmd_search,
        "promises": cmd_promises,
        "inspect-schema": cmd_inspect_schema,
        "backfill-events": cmd_backfill_events,
        "backfill-calltypes": cmd_backfill_calltypes,
        "analytics": cmd_analytics,
        "bot": cmd_bot,
        "biography-run": cmd_biography_run,
        "biography-status": cmd_biography_status,
        "biography-export": cmd_biography_export,
        "graph-backfill": cmd_graph_backfill,
        "reenrich-v2": cmd_reenrich_v2,
        "graph-replay": cmd_graph_replay,
        "graph-stats": cmd_graph_stats,
        "entity-merge": cmd_entity_merge,
        "entity-unmerge": cmd_entity_unmerge,
        "graph-audit": cmd_graph_audit,
        "graph-health": cmd_graph_health,
        "dashboard": cmd_dashboard,
        "book-chapter": cmd_book_chapter,
        "person-profile": cmd_person_profile,
        "profile-all": cmd_profile_all,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

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
