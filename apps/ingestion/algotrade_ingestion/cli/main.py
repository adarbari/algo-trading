"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest universe-build [--date YYYY-MM-DD] [--review-out leveraged_candidates.csv]
                                    [--figi-review-out var/figi_review.csv]
    algotrade-ingest company-details [--date D] [--force] [--limit N]   (SEC EDGAR)
    algotrade-ingest earnings [--date D] [--start D] [--days 60]
    algotrade-ingest bars [--date D | --from D --to D] [--force]   (needs a Massive API key)
    algotrade-ingest corporate-actions [--date D] [--from D --to D]
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers N] [--symbols SPY,AAPL]
    algotrade-ingest rollups  [--date D | --from D --to D] [--only price_stats@v1,earnings@v1]
                              (alias: features)
    algotrade-ingest screen   [--date YYYY-MM-DD] [--config ID] [--user U] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/]   (no --date: catch up)
    algotrade-ingest purge-raw [--keep-days 90] [--staging-keep-days 14]
    algotrade-ingest migrate-ids [--dry-run]   (symbol ids -> FIGI ids, append-only)
    algotrade-ingest golden build|verify|load [--golden-dir datasets/golden]
    algotrade-ingest run <task> [--date D | --from D --to D] [task flags]   (any registry task)

Without ``--date`` a command uses the last closed exchange session (``core/time/calendar.py``:
holidays and early closes known; a session counts once its close plus the settle margin in
``config/site/nightly.toml`` has passed). ``nightly`` without ``--date`` also catches up the
sessions missed since the last nightly. Storage location comes from ALGOTRADE_DATA_URL
(default file://./var/data). Every command that writes to the store takes the store's ingest
run lock: a second concurrent run exits with code 3 unless it was given ``--wait`` (then it
queues behind the first).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from algotrade.config.env import data_url, load_dotenv
from algotrade.config.site.settings import load_nightly
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.time.calendar import last_closed_session
from algotrade.data import StoreReader
from algotrade.services.configs import default_user
from algotrade.services.jobs import RunLockedError, exclusive_run
from algotrade.storage.factory import open_backend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.cli.commands import (
    config_store,
    golden,
    print_json,
    report,
    run_job,
    run_task_command,
)
from algotrade_ingestion.ops.schedule import LABEL, nightly_plist
from algotrade_ingestion.tasks.framework.registry import TASKS, Task
from algotrade_ingestion.tasks.framework.run import recover_unpublished

# Task commands kept under their own names (``algotrade-ingest bars ...``); every registry
# task is also ``algotrade-ingest run <task>``. ``golden load`` runs the ``golden-load`` task.
TASK_COMMANDS = tuple(name for name in TASKS if name != "golden-load")
# Former command names kept working: ``features`` computed option_liquidity before 2b.2.
ALIASES = {"rollups": ["features"]}
LOCKED_EXIT = 3  # another run holds the store's ingest lock


def add_wait(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--wait", action="store_true", help="queue behind a running ingest instead of exiting 3"
    )


def writes(args: argparse.Namespace) -> bool:
    """Whether the command writes to the store (and so takes the run lock)."""
    if args.command == "schedule":
        return False
    return not (args.command == "golden" and args.action in ("build", "verify"))


def default_session(args: argparse.Namespace, now: datetime) -> date:
    """The last closed exchange session at ``now`` (settle margin from nightly.toml)."""
    settings = load_nightly(config_store(args))
    return last_closed_session(now, timedelta(minutes=settings.settle_minutes))


def add_task_arguments(parser: argparse.ArgumentParser, spec: Task) -> None:
    """A task's parameters as flags (``dest`` = the parameter name)."""
    for param in spec.params:
        if param.kind is None:
            parser.add_argument(*param.flags, dest=param.name, action="store_true", help=param.help)
        else:
            parser.add_argument(
                *param.flags,
                dest=param.name,
                type=param.kind,
                required=param.required,
                default=param.default,
                help=param.help,
            )
    add_wait(parser)
    parser.set_defaults(task=spec.name)


def _job_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Commands that run as jobs (screen, nightly) and admin commands."""
    for name in ("screen", "nightly"):
        s = sub.add_parser(name)
        s.add_argument("--date", type=date.fromisoformat)
        s.add_argument("--export-dir", type=Path)
        add_wait(s)
        if name == "nightly":
            s.add_argument("--workers", type=int, help="chain workers (default: sources.toml)")
        else:
            s.add_argument("--config", default="short_premium_liquidity", help="config id")
            s.add_argument("--user", help="config owner (default: $ALGOTRADE_USER or site)")
    sc = sub.add_parser(
        "schedule", help="write a launchd agent for the nightly job (not installed)"
    )
    sc.add_argument("--time", default="23:30", help="local time HH:MM on weekdays (default 23:30)")
    sc.add_argument("--export-dir", type=Path, default=Path("out"))
    sc.add_argument("--out", type=Path, default=Path("var") / f"{LABEL}.plist")
    g = sub.add_parser(
        "golden", help="golden test datasets: build CSVs, verify, load into the store"
    )
    g.add_argument("action", choices=["build", "verify", "load"])
    g.add_argument("--golden-dir", type=Path, default=Path("datasets/golden"))
    add_wait(g)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="algotrade-ingest", description=__doc__.splitlines()[0])
    p.add_argument(
        "--config-dir", help="site/user configs (default: $ALGOTRADE_CONFIG_DIR or ./config)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in TASK_COMMANDS:
        parser = sub.add_parser(name, aliases=ALIASES.get(name, []), help=TASKS[name].description)
        add_task_arguments(parser, TASKS[name])
    run = sub.add_parser("run", help="run any ingestion task: run <task> [--date | --from/--to]")
    tasks = run.add_subparsers(dest="task_name", required=True)
    for name, spec in TASKS.items():
        add_task_arguments(tasks.add_parser(name, help=spec.description), spec)
    _job_parsers(sub)
    return p


def write_schedule(args: argparse.Namespace) -> int:
    hour, minute = (int(x) for x in args.time.split(":"))
    repo = Path.cwd().resolve()
    export_dir = (repo / args.export_dir) if not args.export_dir.is_absolute() else args.export_dir
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(nightly_plist(repo, hour, minute, export_dir))
    target = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    print_json(
        {
            "written": str(args.out),
            "weekdays_at": args.time,
            "install": [
                f"mkdir -p {repo / 'var' / 'logs'}",
                f"cp {args.out.resolve()} {target}",
                f"launchctl load {target}",
            ],
            "uninstall": [f"launchctl unload {target}", f"rm {target}"],
        }
    )
    return 0


def task_params(args: argparse.Namespace, session: date) -> dict[str, Any]:
    """Parsed flags -> registry task parameters (``session`` defaults to the last session)."""
    params = {p.name: getattr(args, p.name, None) for p in TASKS[args.task].params}
    return {**params, "session": session}


def _dispatch(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    if args.command == "schedule":
        return write_schedule(args)
    explicit = getattr(args, "date", None) or getattr(args, "session", None)
    session = explicit or default_session(args, datetime.now(UTC))
    if args.command == "golden":
        return golden(args, reader, writer)
    if getattr(args, "task", None):
        return run_task_command(args, reader, writer, args.task, task_params(args, session))
    if args.command == "screen":
        params = {
            "config": args.config,
            "session": session.isoformat(),
            "export_dir": str(args.export_dir) if args.export_dir else None,
        }
        user = args.user or default_user(SITE_USER).user_id
        return report(run_job(args, reader, writer, "screen", params, user))
    params = {
        "session": session.isoformat(),
        "catch_up": explicit is None,  # no --date: also the sessions missed since the last run
        "workers": args.workers,
        "export_dir": str(args.export_dir) if args.export_dir else None,
    }
    return report(run_job(args, reader, writer, "nightly", params, SITE_USER))


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    backend = open_backend(data_url())
    try:
        if not writes(args):
            return _dispatch(args, StoreReader(backend), StoreWriter(backend))
        with exclusive_run(backend, wait=args.wait):
            writer = StoreWriter(backend)
            recover_unpublished(writer, datetime.now(UTC))  # no ingest run is in flight now
            return _dispatch(args, StoreReader(backend), writer)
    except RunLockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return LOCKED_EXIT
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
