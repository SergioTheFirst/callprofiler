# -*- coding: utf-8 -*-
"""contacts.py — команды работы с контактами и профилями."""

from __future__ import annotations

import argparse
import json as _json
import logging
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo, setup_logging as _setup_logging


def cmd_rebuild_summaries(args: argparse.Namespace) -> int:
    """rebuild-summaries --user ID — пересчитать contact_summaries."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.aggregate.summary_builder import SummaryBuilder

    log.info("Пересчет contact_summaries для пользователя '%s'...", args.user_id)

    builder = SummaryBuilder(repo)
    builder.rebuild_all(args.user_id)

    log.info("✓ Contact_summaries пересчитаны для пользователя '%s'", args.user_id)
    return 0


def cmd_rebuild_cards(args: argparse.Namespace) -> int:
    """rebuild-cards --user ID — пересоздать caller cards."""
    cfg, repo = _load_config_and_repo(args.config)
    _setup_logging(cfg.log_file, args.verbose)

    log = logging.getLogger(__name__)

    user = repo.get_user(args.user_id)
    if not user:
        log.error("Пользователь '%s' не найден", args.user_id)
        return 1

    from callprofiler.aggregate.summary_builder import SummaryBuilder
    from callprofiler.deliver.card_generator import CardGenerator

    log.info("Пересчёт summaries + запись карточек для '%s'...", args.user_id)

    SummaryBuilder(repo).rebuild_all(args.user_id)
    CardGenerator(repo).update_all_cards(args.user_id)

    log.info("✓ Caller cards обновлены для пользователя '%s'", args.user_id)
    return 0


def cmd_book_chapter(args: argparse.Namespace) -> int:
    """book-chapter — show structured graph profile for one entity."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import apply_graph_schema
    from callprofiler.biography.data_extractor import (
        get_entity_profile_from_graph,
        get_behavioral_patterns,
        get_social_position,
    )

    conn = repo._get_conn()
    apply_graph_schema(conn)

    import json as _json

    profile = get_entity_profile_from_graph(args.entity_id, conn)
    if not profile:
        log.error("[book-chapter] entity_id=%d not found", args.entity_id)
        return 1

    patterns = get_behavioral_patterns(args.entity_id, conn)
    social = get_social_position(args.entity_id, conn)

    output = {
        "entity_id": args.entity_id,
        "canonical_name": profile.get("canonical_name"),
        "entity_type": profile.get("entity_type"),
        "aliases": profile.get("aliases", []),
        "metrics": profile.get("metrics", {}),
        "behavioral_patterns": patterns.get("patterns", []),
        "behavioral_raw": patterns.get("raw", {}),
        "top_relations": profile.get("top_relations", []),
        "org_links": social.get("org_links", []),
        "open_promises": social.get("open_promises", 0),
        "conflict_count": social.get("conflict_count", 0),
        "centrality": social.get("centrality", 0),
        "timeline": profile.get("timeline", []),
        "top_facts": profile.get("top_facts", [])[:10],
    }

    print(_json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_person_profile(args: argparse.Namespace) -> int:
    """person-profile — generate psychology profile for one graph entity."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.biography.psychology_profiler import PsychologyProfiler
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)

    llm_url = getattr(cfg, "llm_url", "http://127.0.0.1:8080/v1/chat/completions")
    profiler = PsychologyProfiler(conn, llm_url=llm_url)
    profile = profiler.build_profile(args.entity_id, args.user_id)

    if not profile:
        print(f"Entity {args.entity_id} not found for user {args.user_id}.")
        return 1

    import json as _json

    if getattr(args, "json", False):
        print(_json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== Psychology Profile: {profile['canonical_name']} ===")
        print(f"Type: {profile['entity_type']}  |  Aliases: {', '.join(profile['aliases']) or 'none'}")
        print(f"BS-index: {profile['metrics'].get('bs_index', 'n/a')}  |  avg_risk: {profile['metrics'].get('avg_risk', 'n/a')}")
        print(f"Temporal: {profile['temporal']['avg_calls_per_week']} calls/week  |  trend: {profile['temporal']['frequency_trend']}")
        print("\nPatterns:")
        for p in profile["patterns"]:
            print(f"  [{p['severity']}] {p['name']}: {p['label']}")
        print(f"\nSocial: centrality={profile['social']['centrality']}, open_promises={profile['social']['open_promises']}, conflicts={profile['social']['conflict_count']}")
        if profile.get("interpretation"):
            print(f"\n--- Interpretation ---\n{profile['interpretation']}")
        else:
            print("\n(LLM interpretation unavailable)")
    return 0


def cmd_profile_all(args: argparse.Namespace) -> int:
    """profile-all — generate psychology profiles for all entities of a user."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    from callprofiler.biography.psychology_profiler import PsychologyProfiler
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)

    limit = getattr(args, "limit", 0) or 0

    query = """
        SELECT e.id
          FROM entities e
          LEFT JOIN entity_metrics em ON em.entity_id = e.id
         WHERE e.user_id=? AND e.archived=0
         ORDER BY
           CASE
             WHEN UPPER(e.entity_type) = 'PERSON' THEN 0
             WHEN UPPER(e.entity_type) IN ('COMPANY', 'ORG', 'PROJECT') THEN 1
             ELSE 2
           END,
           COALESCE(em.total_calls, 0) DESC,
           (
             COALESCE(em.total_promises, 0)
             + COALESCE(em.contradictions, 0)
             + COALESCE(em.emotional_spikes, 0)
           ) DESC,
           e.id
    """
    params: list = [args.user_id]
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print(f"No entities found for user {args.user_id}.")
        return 0

    llm_url = getattr(cfg, "llm_url", "http://127.0.0.1:8080/v1/chat/completions")
    profiler = PsychologyProfiler(conn, llm_url=llm_url)

    success = 0
    failed = 0
    for row in rows:
        eid = row[0]
        try:
            profile = profiler.build_profile(eid, args.user_id)
            if profile:
                name = profile.get("canonical_name", str(eid))
                interp = profile.get("interpretation")
                status = "cached" if profile.get("_cache_hit") else ("ok" if interp else "no-llm")
                print(f"  [{status}] {eid}: {name}")
                success += 1
            else:
                print(f"  [skip] {eid}: not found")
        except Exception as exc:
            logging.getLogger(__name__).error("profile-all entity %d failed: %s", eid, exc)
            failed += 1

    print(f"\nDone: {success} profiled, {failed} failed.")
    return 0 if failed == 0 else 1



def register_subparsers(sub):
    """Register contacts subparsers — defined in _build_parser()."""
    pass  # parsers remain in main.py: _build_parser()
