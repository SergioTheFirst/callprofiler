"""CLI-обёртки insight: features-build, archetypes-fit."""
import argparse
import logging

from callprofiler.cli.utils import load_config_and_repo, setup_logging
from callprofiler.insight import cli_ops
from callprofiler.insight.cards import build_card

log = logging.getLogger(__name__)


def cmd_features_build(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()
    n = cli_ops.run_features_build(conn, args.user_id)
    print(f"insight features: записано {n} (user={args.user_id})")
    return 0


def cmd_archetypes_fit(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()
    res = cli_ops.run_archetypes_fit(conn, args.user_id,
                                     version=getattr(args, "version", "arch-v1"))
    print(f"archetypes: k={res['k']} silhouette={res['silhouette']:.2f} "
          f"assigned={res['n_assigned']} (user={args.user_id})")
    return 0


def cmd_person_link(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()
    from callprofiler.insight.person_link import build_entity_contact_map
    stats = build_entity_contact_map(conn, args.user_id,
                                     dry_run=getattr(args, "dry_run", False))
    mode = "dry-run, БЕЗ записи" if getattr(args, "dry_run", False) else "записано"
    print(f"person-link ({mode}): links={stats['links']} "
          f"(name={stats['name']}, cooccur={stats['cooccur']}) user={args.user_id}")
    return 0


def cmd_person_archetype(args: argparse.Namespace) -> int:
    setup_logging(verbose=getattr(args, "verbose", False))
    cfg, repo = load_config_and_repo(args.config)
    conn = repo._get_conn()
    card = build_card(conn, args.user_id, args.contact_id)
    if card is None:
        print(f"Нет архетипа для contact={args.contact_id} — сначала "
              f"archetypes-fit --user {args.user_id}")
        return 0
    if getattr(args, "json", False):
        import json
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0
    mem = card["membership"] or 0.0
    print(f"\n=== {card['name']} (#{card['contact_id']}) ===")
    print(f"Архетип: {card['archetype']}  |  близость {mem:.0%}  |  уверенность {card['confidence']}")
    if card["traits"]:
        print("Отличительное: " + "; ".join(card["traits"]))
    if card["topics"]:
        print("Темы: " + ", ".join(card["topics"]))
    if card["last_seen"]:
        print(f"Последний контакт: {card['last_seen']}")
    if card["note"]:
        print(f"Заметка: {card['note'][:200]}")
    return 0
