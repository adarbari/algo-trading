"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest universe-build [--date YYYY-MM-DD] [--review-out leveraged_candidates.csv]
    algotrade-ingest company-details [--date D] [--force] [--limit N]   (SEC EDGAR)
    algotrade-ingest earnings [--date D] [--start D] [--days 60]
    algotrade-ingest bars [--date D | --from D --to D] [--force]   (needs a Massive API key)
    algotrade-ingest corporate-actions [--date D] [--from D --to D]
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers N] [--symbols SPY,AAPL]
    algotrade-ingest features [--date YYYY-MM-DD]
    algotrade-ingest screen   [--date YYYY-MM-DD] [--config ID] [--user U] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/]
    algotrade-ingest purge-raw --keep-days 90 [--staging-keep-days 14]
    algotrade-ingest migrate-ids [--dry-run]   (symbol ids -> FIGI ids, append-only)
    algotrade-ingest golden build|verify|load [--golden-dir datasets/golden]
    algotrade-ingest run <task> [--date D | --from D --to D] [task flags]   (any registry task)

Storage location comes from ALGOTRADE_DATA_URL (default file://./var/data).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from algotrade.config.user import SITE_USER
from algotrade.core.errors import AlgoTradeError
from algotrade.data import StoreReader
from algotrade.services.configs import default_user
from algotrade.storage.factory import open_backend
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.commands import golden, print_json, report, run_job, run_task_command
from algotrade_ingestion.env import load_dotenv
from algotrade_ingestion.schedule import LABEL, nightly_plist
from algotrade_ingestion.tasks.registry import TASKS, Task

EXCHANGE_TZ = ZoneInfo("America/New_York")
# Task commands kept under their own names (``algotrade-ingest bars ...``); every registry
# task is also ``algotrade-ingest run <task>``. ``golden load`` runs the ``golden-load`` task.
TASK_COMMANDS = tuple(name for name in TASKS if name != "golden-load")


def last_session(now: datetime) -> date:
    """Most recent weekday in exchange time. Pass --date explicitly on exchange holidays."""
    day = now.astimezone(EXCHANGE_TZ).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


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
    parser.set_defaults(task=spec.name)


def _job_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Commands that run as jobs (screen, nightly) and admin commands."""
    for name in ("screen", "nightly"):
        s = sub.add_parser(name)
        s.add_argument("--date", type=date.fromisoformat)
        s.add_argument("--export-dir", type=Path)
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
    r = sub.add_parser(
        "purge-raw", help="delete raw vendor responses and unfinished-run scratch older than N days"
    )
    r.add_argument("--keep-days", type=int, default=90)
    r.add_argument("--staging-keep-days", type=int, default=14, help="unfinished-run scratch")
    r.add_argument("--date", type=date.fromisoformat, help="reference date (default: today)")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="algotrade-ingest", description=__doc__.splitlines()[0])
    p.add_argument(
        "--config-dir", help="site/user configs (default: $ALGOTRADE_CONFIG_DIR or ./config)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in TASK_COMMANDS:
        add_task_arguments(sub.add_parser(name, help=TASKS[name].description), TASKS[name])
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
    session = args.date if getattr(args, "date", None) else last_session(datetime.now(UTC))
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
    if args.command == "nightly":
        params = {
            "session": session.isoformat(),
            "workers": args.workers,
            "export_dir": str(args.export_dir) if args.export_dir else None,
        }
        return report(run_job(args, reader, writer, "nightly", params, SITE_USER))
    removed = writer.raw.purge_before(session - timedelta(days=args.keep_days))
    staged = writer.staging.purge_before(session - timedelta(days=args.staging_keep_days))
    print_json({"raw_files_removed": removed, "staging_runs_removed": staged})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    backend = open_backend()
    try:
        return _dispatch(args, StoreReader(backend), StoreWriter(backend))
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
