#!/usr/bin/env python3
"""Rewrite users' edge files from the old ``[follow]`` states to one status and a bookmark (ADR 0053
amendment 2026-10-10): a site edge's follow-only file keeps ``[follow] since`` (a followed edge) or
is archived (a rejected or retired one); an own edge's ``[follow]`` becomes its ``status`` and its
``[audit]``. Idempotent; each write is atomic (``ConfigWriter``). It goes with ``follow.LEGACY``.

Usage: python scripts/migrate_edge_follows.py (--user U | --all) [--dry-run] [--config-dir DIR]
``--dry-run`` runs the same migration over an in-memory copy and writes nothing."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from algotrade.config.edges.loading import KIND, SITE
from algotrade.config.env import config_dir
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.edges import migrate_follows
from algotrade.services.authoring.scope import open_writer
from algotrade.storage.configs.writer import ConfigWriter, MemoryConfigWriter


def _copy_of(writer: ConfigWriter, users: Sequence[str]) -> MemoryConfigWriter:
    """The edge documents of the site and ``users`` in memory: what a dry run migrates."""
    documents: dict[tuple[str, str, str], Any] = {}
    for scope in (SITE, *users):
        for name in writer.names(scope, KIND):
            documents[(scope, KIND, name)] = writer.load(scope, KIND, name)
    return MemoryConfigWriter(documents)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--user", help="migrate this user's edge files")
    who.add_argument("--all", action="store_true", help="migrate every user's edge files")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--config-dir", help="the config root (default: the usual one)")
    args = parser.parse_args(argv)
    writer = open_writer(config_dir(args.config_dir and Path(args.config_dir)))
    users = [u for u in writer.users() if u != SITE] if args.all else [args.user]
    target: ConfigWriter = _copy_of(writer, users) if args.dry_run else writer
    failed = 0
    for user in users:
        try:
            done = migrate_follows(target, user)
        except ConfigurationError as exc:
            print(f"{user}: {exc}")
            failed += 1
            continue
        for edge_id, what in sorted(done.items()):
            print(f"{user}/{edge_id}: {what}{' (dry run)' if args.dry_run else ''}")
        failed += sum(1 for what in done.values() if what.startswith("skipped"))
        if not done:
            print(f"{user}: nothing to migrate")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
