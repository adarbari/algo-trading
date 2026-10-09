"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest universe-build [--date YYYY-MM-DD] [--review-out leveraged_candidates.csv]
                                    [--figi-review-out var/figi_review.csv] [--accept-sp500]
    algotrade-ingest company-details [--date D] [--force] [--limit N]   (SEC EDGAR)
    algotrade-ingest earnings [--date D] [--start D] [--days 60] | [--from D --to D] (backfill)
    algotrade-ingest bars [--date D | --from D --to D] [--force]   (needs a Massive API key)
    algotrade-ingest corporate-actions [--date D] [--from D --to D]
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers N] [--symbols SPY,AAPL]
    algotrade-ingest rollups  [--date D | --from D --to D] [--only price_stats@v2,earnings@v1]
                              (alias: features)
    algotrade-ingest retire-features --group price_stats@v1 [--dry-run]
                              (delete a superseded group's tables once its replacement covers them)
    algotrade-ingest screen   [--date YYYY-MM-DD] [--config ID] [--user U] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/] [--force]
                              [--waive STEP --reason TEXT]
                              (no --date: catch up; a quiet no-op when up to date; a failed
                              session resumes; --force reruns every step; --waive accepts a
                              step that cannot succeed, e.g. chains past their day: ADR 0039)
    algotrade-ingest report   [--date D] [--out report.html] [--send] [--max-examples N]
                              (the nightly summary email for a past session; read-only)
    algotrade-ingest arrivals [--sessions N]
                              (when bars / chains first appeared after the close: p50 / p90 minutes)
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

``nightly`` without ``--date`` is what the launchd agent runs (``schedule``: weekdays at
15:00, at login and hourly), so it must be cheap to repeat: when every session up to the last
closed one already has a done nightly (SUCCEEDED; COMPLETE / PARTIAL before ADR 0039) it
prints ``nothing to do: <session>
already ingested`` and exits 0 without taking the lock, writing a run record or notifying;
while another ingest run holds the lock it prints one line and exits 3, also without
notifying. ``--force`` runs anyway (the last closed session again when nothing is missing).
``nightly`` refuses to start (exit 2) on code imported from a git worktree
(``ops/checkout.py``).
"""

import argparse
import subprocess
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
    arrivals_command,
    config_store,
    golden,
    nightly_report,
    print_json,
    report,
    run_job,
    run_task_command,
)
from algotrade_ingestion.ops.checkout import ensure_main_checkout
from algotrade_ingestion.ops.hold import hold
from algotrade_ingestion.ops.schedule import (
    DEFAULT_TIME,
    DEFAULT_WATCHDOG_MINUTES,
    LABEL,
    MONTHLY_LABEL,
    WAKE_COMMAND,
    monthly_fill_plist,
    nightly_plist,
)
from algotrade_ingestion.tasks.framework.registry import TASKS, Task
from algotrade_ingestion.tasks.framework.run import recover_unpublished
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from algotrade_ingestion.workflows.nightly.sessions import last_done
from algotrade_ingestion.workflows.nightly.timing import DEFAULT_SESSIONS

# Task commands kept under their own names (``algotrade-ingest bars ...``); every registry
# task is also ``algotrade-ingest run <task>``. ``golden load`` runs the ``golden-load`` task.
TASK_COMMANDS = tuple(name for name in TASKS if name != "golden-load")
# Former command names kept working: ``features`` computed option_liquidity before 2b.2.
ALIASES = {"rollups": ["features"]}
LOCKED_EXIT = 3  # another run holds the store's ingest lock
STEP_NAMES = tuple(s.name for s in NIGHTLY)  # what --waive accepts


def positive(text: str) -> int:
    """An argparse type: an integer of at least 1."""
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def add_wait(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--wait", action="store_true", help="queue behind a running ingest instead of exiting 3"
    )


def writes(args: argparse.Namespace) -> bool:
    """Whether the command writes to the store (and so takes the run lock)."""
    if args.command in ("schedule", "report", "arrivals"):
        return False
    return not (args.command == "golden" and args.action in ("build", "verify"))


def default_session(args: argparse.Namespace, now: datetime) -> date:
    """The last closed exchange session at ``now`` (settle margin from nightly.toml)."""
    settings = load_nightly(config_store(args))
    return last_closed_session(now, timedelta(minutes=settings.settle_minutes))


def scheduled_nightly(args: argparse.Namespace) -> bool:
    """``nightly`` with neither ``--date`` nor ``--force``: the scheduled catch-up, which is a
    no-op when there is nothing to ingest."""
    return args.command == "nightly" and args.date is None and not args.force


def ingested_through(args: argparse.Namespace, writer: StoreWriter, now: datetime) -> date | None:
    """The last closed session when every session up to it has a COMPLETE / PARTIAL nightly
    (nothing to catch up), else ``None``. Reads run records only: fast, writes nothing."""
    session = default_session(args, now)
    done = last_done(writer)
    return session if done is not None and done >= session else None


def nothing_to_do(session: date) -> int:
    print(f"nothing to do: {session} already ingested")
    return 0


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
            s.add_argument(
                "--force",
                action="store_true",
                help="run even when every closed session is already ingested, and rerun every "
                "step (no resume from an earlier attempt)",
            )
            s.add_argument(
                "--waive",
                action="append",
                default=[],
                metavar="STEP",
                help="with --date and --reason: accept STEP for that session without it "
                "succeeding (recorded in the run record); repeatable",
            )
            s.add_argument("--reason", help="why the --waive steps are accepted")
        else:
            s.add_argument("--config", default="short_premium_liquidity", help="config id")
            s.add_argument("--user", help="config owner (default: $ALGOTRADE_USER or site)")
    dh = sub.add_parser(
        "deploy-hold", help="run a command under the deploy and ingest locks (exit 75: busy)"
    )
    dh.add_argument("--deploy-only", action="store_true", help="take the deploy lock alone")
    dh.add_argument("cmd", nargs=argparse.REMAINDER)
    sc = sub.add_parser(
        "schedule",
        help="write the launchd agents of the nightly job and the monthly Tiingo fill "
        "(not installed)",
    )
    sc.add_argument(
        "--time",
        default=DEFAULT_TIME,
        help=f"local time HH:MM on weekdays (default {DEFAULT_TIME}, for Pacific time)",
    )
    sc.add_argument(
        "--watchdog-minutes",
        type=int,
        default=DEFAULT_WATCHDOG_MINUTES,
        help=f"also start every N minutes to heal missed runs; 0: off "
        f"(default {DEFAULT_WATCHDOG_MINUTES})",
    )
    sc.add_argument("--export-dir", type=Path, default=Path("out"))
    sc.add_argument("--out", type=Path, default=Path("var") / f"{LABEL}.plist")
    sc.add_argument(
        "--monthly-out", type=Path, default=Path("var") / f"{MONTHLY_LABEL}.plist",
        help="where to write the monthly `bars-history --fill` agent (2nd of the month, 19:00)",
    )  # fmt: skip
    r = sub.add_parser(
        "report", help="render (and --send) the nightly summary email for a past session"
    )
    r.add_argument("--date", type=date.fromisoformat, help="session (default: last session)")
    r.add_argument("--out", type=Path, help="also write the HTML version to this file")
    r.add_argument("--send", action="store_true", help="email it ([notify.email] + .env)")
    r.add_argument("--max-examples", type=int, help="examples per failure group")
    a = sub.add_parser("arrivals", help="when each source's data first appeared after the close")
    a.add_argument(
        "--sessions", type=positive, default=DEFAULT_SESSIONS, help="last N sessions (>= 1)"
    )
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
    watchdog_s = args.watchdog_minutes * 60
    args.out.write_bytes(nightly_plist(repo, hour, minute, export_dir, watchdog_s))
    args.monthly_out.parent.mkdir(parents=True, exist_ok=True)
    args.monthly_out.write_bytes(monthly_fill_plist(repo))
    target = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    monthly_target = Path.home() / "Library" / "LaunchAgents" / f"{MONTHLY_LABEL}.plist"
    print_json(
        {
            "written": str(args.out),
            "monthly_written": str(args.monthly_out),
            "monthly_install": [
                f"mkdir -p {repo / 'var' / 'logs'}",
                f"launchctl unload {monthly_target} 2>/dev/null || true",
                f"cp {args.monthly_out.resolve()} {monthly_target}",
                f"launchctl load {monthly_target}",
            ],
            "monthly_uninstall": [f"launchctl unload {monthly_target}", f"rm {monthly_target}"],
            "weekdays_at": args.time,
            "run_at_load": True,
            "watchdog_minutes": args.watchdog_minutes or None,
            # Replaces an installed agent too (unloading one that is not loaded only warns).
            "install": [
                f"mkdir -p {repo / 'var' / 'logs'}",
                f"launchctl unload {target} 2>/dev/null || true",
                f"cp {args.out.resolve()} {target}",
                f"launchctl load {target}",
            ],
            "uninstall": [f"launchctl unload {target}", f"rm {target}"],
            "optional_wake": {
                "command": WAKE_COMMAND,
                "note": "run it yourself (needs sudo): wakes or powers on the Mac on weekdays "
                "before the run; `sudo pmset repeat cancel` removes it",
            },
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
    if args.command in ("report", "arrivals"):
        read_only = {"report": nightly_report, "arrivals": arrivals_command}
        return read_only[args.command](args, reader, session)
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
    return nightly(args, reader, writer, session, explicit is None)


def nightly(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date, auto: bool
) -> int:
    """The nightly job; ``auto`` (no ``--date``): catch up, a no-op unless ``--force``."""
    through = ingested_through(args, writer, datetime.now(UTC)) if auto else None
    if through is not None and not args.force:
        return nothing_to_do(through)  # finished by another run since main() checked
    params = {
        "session": session.isoformat(),
        # No --date: also the sessions missed since the last run. --force when nothing is
        # missing: the last closed session again.
        "catch_up": auto and through is None,
        "resume": not args.force,
        "waive": dict.fromkeys(args.waive, args.reason),
        "workers": args.workers,
        "export_dir": str(args.export_dir) if args.export_dir else None,
    }
    return report(run_job(args, reader, writer, "nightly", params, SITE_USER))


def check_waive(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """``--waive`` needs ``--date`` (the session) and ``--reason``, and names workflow steps."""
    if args.command != "nightly" or not args.waive:
        return
    if args.date is None or not (args.reason or "").strip():
        parser.error("--waive needs --date (the session) and --reason")
    unknown = sorted(set(args.waive) - set(STEP_NAMES))
    if unknown:
        parser.error(
            f"--waive: unknown step(s) {', '.join(unknown)}; steps: {', '.join(STEP_NAMES)}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = _parser()
    args = parser.parse_args(argv)
    check_waive(parser, args)
    backend = open_backend(data_url())
    if args.command == "deploy-hold":  # not an ingest run: before the writes / lock path
        cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
        if not cmd:
            parser.error("deploy-hold needs a command after --")
        return hold(
            backend,
            lambda: subprocess.run(cmd, check=False).returncode,
            ingest=not args.deploy_only,
        )
    try:
        if args.command == "nightly":  # never an unmerged branch against the real store
            ensure_main_checkout()
        if not writes(args):
            return _dispatch(args, StoreReader(backend), StoreWriter(backend))
        if scheduled_nightly(args):  # before the lock: a no-op must not wait or write
            through = ingested_through(args, StoreWriter(backend), datetime.now(UTC))
            if through is not None:
                return nothing_to_do(through)
        with exclusive_run(backend, wait=args.wait):
            writer = StoreWriter(backend)
            recover_unpublished(writer, datetime.now(UTC))  # no ingest run is in flight now
            return _dispatch(args, StoreReader(backend), writer)
    except RunLockedError as exc:
        if scheduled_nightly(args):  # e.g. the nightly itself is still running: not an error
            print("busy: another ingest run holds the lock; a later start catches up")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return LOCKED_EXIT
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
