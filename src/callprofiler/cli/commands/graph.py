# -*- coding: utf-8 -*-
"""graph.py — команды Knowledge Graph."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from callprofiler.cli.utils import load_config_and_repo as _load_config_and_repo, setup_logging as _setup_logging


def cmd_graph_backfill(args: argparse.Namespace) -> int:
    """graph-backfill — populate Knowledge Graph from v2 analyses."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.builder import GraphBuilder
    from callprofiler.graph.calibration import BSCalibrator
    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    builder = GraphBuilder(conn)
    grepo = GraphRepository(conn)

    schema_filter = getattr(args, "schema", "v2")
    rows = conn.execute(
        """SELECT a.call_id FROM analyses a
           JOIN calls c ON c.call_id = a.call_id
           WHERE c.user_id = ? AND (a.schema_version = ? OR ? = 'all')
           ORDER BY a.call_id""",
        (args.user_id, schema_filter, schema_filter),
    ).fetchall()

    total = len(rows)
    log.info("[graph-backfill] %d analyses to process (schema=%s)", total, schema_filter)
    ok = fail = skip = 0
    for i, row in enumerate(rows, 1):
        call_id = row[0]
        try:
            transcript_text = None
            try:
                segments = repo.get_transcript(call_id)
                if segments:
                    transcript_text = " ".join(seg.text for seg in segments if seg.text)
            except Exception as exc:
                log.debug("[graph-backfill] call_id=%d transcript unavailable: %s", call_id, exc)

            updated = builder.update_from_call(call_id, transcript_text=transcript_text)
            if updated:
                ok += 1
            else:
                skip += 1
        except Exception as exc:
            log.error("[graph-backfill] call_id=%d failed: %s", call_id, exc)
            fail += 1
        if i % 100 == 0:
            log.info("[graph-backfill] %d/%d  ok=%d skip=%d fail=%d", i, total, ok, skip, fail)

    bstats = builder.get_stats()
    entities_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE user_id=? AND archived=0",
        (args.user_id,),
    ).fetchone()[0]
    avg_bs_raw = conn.execute(
        "SELECT AVG(bs_index) FROM entity_metrics WHERE user_id=?",
        (args.user_id,),
    ).fetchone()[0]
    avg_bs_index = round(float(avg_bs_raw), 2) if avg_bs_raw is not None else None

    auditor = GraphAuditor(conn)
    audit_result = auditor.run_checks(args.user_id)
    audit_critical = 1 if audit_result.get("has_critical") else 0
    grepo.save_replay_run(
        user_id=args.user_id,
        calls_processed=ok + skip,
        facts_total=bstats["facts_total"],
        facts_inserted=bstats["facts_inserted"],
        facts_rejected=bstats["facts_rejected"],
        entities_count=entities_count,
        avg_bs_index=avg_bs_index,
        audit_critical=audit_critical,
    )
    calibration = BSCalibrator(grepo).analyze(args.user_id)
    if calibration.get("ok"):
        log.info(
            "[graph-backfill] BS thresholds calibrated on %d entities",
            calibration["entity_count"],
        )
    else:
        log.warning(
            "[graph-backfill] BS thresholds not calibrated: entity_count=%d",
            calibration["entity_count"],
        )

    log.info("[graph-backfill] done: ok=%d skip=%d fail=%d / total=%d", ok, skip, fail, total)
    return 0


def cmd_reenrich_v2(args: argparse.Namespace) -> int:
    """reenrich-v2 — re-run LLM analysis on v1 calls to produce v2 schema_version."""
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    log.info(
        "[reenrich-v2] Re-enriching v1 analyses for user=%s limit=%s",
        args.user_id, args.limit,
    )
    # Delegate to bulk_enrich — it always uses the current prompt (v2).
    # We filter for calls that have v1 analysis so they get re-processed.
    from callprofiler.bulk.enricher import bulk_enrich

    conn = repo._get_conn()
    # Mark v1 analyses as needing reenrichment by deleting them (idempotent via MD5 dedup).
    limit = args.limit or 0
    rows = conn.execute(
        """SELECT a.call_id FROM analyses a
           JOIN calls c ON c.call_id = a.call_id
           WHERE c.user_id = ? AND (a.schema_version IS NULL OR a.schema_version = 'v1')
           ORDER BY a.call_id LIMIT ?""",
        (args.user_id, limit if limit else -1),
    ).fetchall()

    call_ids = [r[0] for r in rows]
    if not call_ids:
        log.info("[reenrich-v2] No v1 analyses found.")
        return 0

    log.info("[reenrich-v2] Deleting %d v1 analyses to trigger re-enrichment", len(call_ids))
    placeholders = ",".join("?" * len(call_ids))
    conn.execute(f"DELETE FROM analyses WHERE call_id IN ({placeholders})", call_ids)
    conn.commit()

    db_path = str(Path(cfg.data_dir) / "db" / "callprofiler.db")
    stats = bulk_enrich(
        user_id=args.user_id,
        db_path=db_path,
        config_path=args.config,
        limit=limit,
    )
    log.info("[reenrich-v2] bulk_enrich result: %s", stats)
    return 0


def cmd_graph_stats(args: argparse.Namespace) -> int:
    """graph-stats — show Knowledge Graph statistics for a user."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = _load_config_and_repo(args.config)
    log = logging.getLogger(__name__)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    grepo = GraphRepository(conn)
    stats = grepo.stats(args.user_id)

    print(f"\nKnowledge Graph — user: {args.user_id}")
    print("─" * 40)
    print("Entities:")
    for etype, cnt in sorted(stats["entities"].items()):
        print(f"  {etype:<20} {cnt:>6}")
    if not stats["entities"]:
        print("  (none)")

    print("Relations:")
    for rtype, cnt in sorted(stats["relations"].items()):
        print(f"  {rtype:<20} {cnt:>6}")
    if not stats["relations"]:
        print("  (none)")

    print("Facts (graph-linked events):")
    for ftype, cnt in sorted(stats["facts"].items()):
        print(f"  {ftype:<20} {cnt:>6}")
    if not stats["facts"]:
        print("  (none)")

    print(f"Entities with metrics: {stats['entities_with_metrics']}")
    print()
    return 0


def cmd_graph_replay(args: argparse.Namespace) -> int:
    """graph-replay — rebuild graph layer from v2 analyses."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema
    from callprofiler.graph.replay import GraphReplayer

    conn = repo._get_conn()
    apply_graph_schema(conn)

    graph_repo = GraphRepository(conn)
    replayer = GraphReplayer(repo, graph_repo)

    user_id = args.user
    limit = getattr(args, "limit", None)

    log.info("[graph-replay] starting for user_id=%s, limit=%s", user_id, limit)
    stats = replayer.replay(user_id, limit=limit)

    print("\n=== GRAPH REPLAY STATS ===\n")
    print(f"Calls processed:    {stats['calls_processed']}")
    print(f"Entities:           {stats['entities_count']}")
    print(f"Relations:          {stats['relations_count']}")
    print(f"Facts:              {stats['facts_count']}")
    print(f"Avg BS-index:       {stats['avg_bs_index']}")
    print()

    if stats["warnings"]:
        print("WARNINGS:")
        for w in stats["warnings"]:
            print(f"  ⚠️  {w}")
        return 2 if any("ASSERT FAILED" in w for w in stats["warnings"]) else 1

    return 0


def cmd_entity_merge(args: argparse.Namespace) -> int:
    """entity-merge — merge duplicate entity into canonical."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import apply_graph_schema
    from callprofiler.graph.resolver import EntityResolver

    conn = repo._get_conn()
    apply_graph_schema(conn)
    resolver = EntityResolver(conn)

    loop = getattr(args, "loop", False)
    max_iterations = 50  # safety cap for --loop

    iteration = 0
    while True:
        iteration += 1
        if getattr(args, "dry_run", False):
            preview = resolver.preview_merge(args.canonical_id, args.duplicate_id)
            import json as _json
            print(_json.dumps(preview, ensure_ascii=False, indent=2))
            return 0

        try:
            resolver.execute_merge(
                canonical_id=args.canonical_id,
                duplicate_id=args.duplicate_id,
                signals={"score": getattr(args, "score", 0.0)},
                merged_by="manual",
                reason=getattr(args, "reason", "") or "",
            )
            log.info(
                "[entity-merge] merged %d → %d (iteration %d)",
                args.duplicate_id, args.canonical_id, iteration,
            )
        except Exception as exc:
            log.error("[entity-merge] failed: %s", exc)
            return 1

        if not loop:
            break

        # In --loop mode: find next candidate for the same canonical
        user_row = conn.execute(
            "SELECT user_id, entity_type FROM entities WHERE id=?", (args.canonical_id,)
        ).fetchone()
        if not user_row:
            break
        candidates = resolver.find_candidates(
            user_row[0], user_row[1], min_score=0.65, limit=1
        )
        candidates = [c for c in candidates if c.canonical_id == args.canonical_id]
        if not candidates:
            log.info("[entity-merge] no more candidates for canonical_id=%d", args.canonical_id)
            break
        if iteration >= max_iterations:
            log.warning("[entity-merge] loop safety cap reached (%d)", max_iterations)
            break
        args.duplicate_id = candidates[0].duplicate_id
        log.info(
            "[entity-merge] loop: next candidate duplicate_id=%d score=%.3f",
            args.duplicate_id, candidates[0].score,
        )

    return 0


def cmd_entity_unmerge(args: argparse.Namespace) -> int:
    """entity-unmerge — reverse a previously recorded merge."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.repository import GraphRepository, apply_graph_schema
    from callprofiler.graph.aggregator import EntityMetricsAggregator

    conn = repo._get_conn()
    apply_graph_schema(conn)

    # Fetch merge log entry
    log_row = conn.execute(
        """SELECT * FROM entity_merges_log
           WHERE canonical_id=? AND duplicate_id=? AND reversible=1
           ORDER BY merged_at DESC LIMIT 1""",
        (args.canonical_id, args.duplicate_id),
    ).fetchone()
    if not log_row:
        log.error(
            "[entity-unmerge] no reversible merge found for canonical=%d duplicate=%d",
            args.canonical_id, args.duplicate_id,
        )
        return 1

    import json as _json
    snapshot = _json.loads(log_row["snapshot_json"] or "{}")

    with conn:
        # Restore duplicate entity from snapshot
        conn.execute(
            "UPDATE entities SET archived=0, merged_into_id=NULL WHERE id=?",
            (args.duplicate_id,),
        )
        # Restore aliases from snapshot
        if "aliases" in snapshot:
            conn.execute(
                "UPDATE entities SET aliases=? WHERE id=?",
                (_json.dumps(snapshot["aliases"]), args.duplicate_id),
            )
        # Transfer events back (all events currently on canonical that came from duplicate)
        # Without per-event provenance we cannot split them perfectly;
        # we mark the merge log entry as reversed and warn the user.
        conn.execute(
            "UPDATE entity_merges_log SET unmerged_at=CURRENT_TIMESTAMP, reversible=0 "
            "WHERE id=?",
            (log_row["id"],),
        )

    # Recalculate both entities
    grepo = GraphRepository(conn)
    agg = EntityMetricsAggregator(grepo)
    for eid in (args.canonical_id, args.duplicate_id):
        try:
            agg.full_recalc_from_events(eid)
        except Exception as exc:
            log.warning("[entity-unmerge] recalc failed for %d: %s", eid, exc)

    log.info(
        "[entity-unmerge] restored entity %d from canonical %d. "
        "NOTE: event ownership cannot be split — manual review recommended.",
        args.duplicate_id, args.canonical_id,
    )
    return 0


def cmd_graph_health(args: argparse.Namespace) -> int:
    """graph-health — 4 stability checks before biography generation.

    Exit 0 if all checks pass. Exit 1 if any check fails.
    """
    cfg, repo = _load_config_and_repo(args.config)
    log_file = args.log_file or cfg.log_file
    _setup_logging(log_file, getattr(args, "verbose", False))
    user_id = args.user_id

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.repository import GraphRepository, apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    grepo = GraphRepository(conn)

    checks: list[tuple[str, bool, str]] = []

    # Check 1: last replay run rejection_rate < 0.90
    last_run = grepo.get_last_replay_run(user_id)
    if last_run:
        rr = float(last_run.get("rejection_rate") or 0.0)
        ok1 = rr < 0.90
        label1 = f"rejection={rr * 100:.1f}% ({'stable' if ok1 else 'UNSTABLE'})"
    else:
        ok1 = False
        label1 = "no replay run found — run graph-replay first"
    checks.append(("replay", ok1, label1))

    # Check 2: graph-audit → no critical issues
    auditor = GraphAuditor(conn)
    audit_result = auditor.run_checks(user_id)
    ok2 = not audit_result["has_critical"]
    label2 = (
        "no critical issues"
        if ok2
        else f"{sum(1 for c in audit_result['checks'].values() if not c['ok'])} check(s) failed"
    )
    checks.append(("audit", ok2, label2))

    # Check 3: entity_metrics has rows for user
    em_count = conn.execute(
        """SELECT COUNT(*) FROM entity_metrics em
           JOIN entities e ON e.id = em.entity_id
           WHERE e.user_id = ?""",
        (user_id,),
    ).fetchone()[0]
    ok3 = em_count > 0
    label3 = f"{em_count} entity metric row(s)"
    checks.append(("entity_metrics", ok3, label3))

    # Check 4: bs_thresholds calibrated for user
    th_count = conn.execute(
        "SELECT COUNT(*) FROM bs_thresholds WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    ok4 = th_count > 0
    label4 = f"{th_count} threshold row(s)" if ok4 else "no thresholds — run graph-replay to calibrate"
    checks.append(("bs_thresholds", ok4, label4))

    print(f"\nGraph Health — user: {user_id}")
    print("─" * 50)
    all_ok = True
    for name, ok, detail in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name:<20} {detail}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("All checks passed — graph is ready for biography generation.")
        return 0
    print("Health gate FAILED — fix issues above before running book-chapter.")
    return 1


def cmd_graph_audit(args: argparse.Namespace) -> int:
    """graph-audit — run 9 sanity checks on the Knowledge Graph."""
    _setup_logging(verbose=getattr(args, "verbose", False))
    log = logging.getLogger(__name__)
    cfg, repo = _load_config_and_repo(args.config)

    from callprofiler.graph.auditor import GraphAuditor
    from callprofiler.graph.repository import apply_graph_schema

    conn = repo._get_conn()
    apply_graph_schema(conn)
    auditor = GraphAuditor(conn)
    result = auditor.run_checks(args.user_id)

    print(f"\nGraph Audit — user: {args.user_id}")
    print("─" * 50)
    for name, check in sorted(result["checks"].items()):
        status = "CRITICAL" if (not check["ok"] and name in {"owner_contamination", "orphan_events"}) \
                 else "WARN" if not check["ok"] else "OK"
        flag = "✗" if not check["ok"] else "✓"
        print(f"  {flag} {name:<40} {status}  (n={check['count']})")
        if not check["ok"] and check["details"]:
            for d in check["details"][:3]:
                print(f"      {d}")

    print()
    if result["has_critical"]:
        print("CRITICAL issues found — data integrity requires attention.")
        return 2
    if result["has_warnings"]:
        print("Warnings found.")
        return 1
    print("All checks passed.")
    return 0


def register_subparsers(sub):
    """Register graph subparsers — defined in _build_parser()."""
    pass  # parsers remain in main.py: _build_parser()
