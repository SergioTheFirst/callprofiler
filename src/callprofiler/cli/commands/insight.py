"""CLI-обёртки insight: features-build, archetypes-fit."""
import argparse
import logging

from callprofiler.cli.utils import load_config_and_repo, setup_logging
from callprofiler.insight import cli_ops

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
