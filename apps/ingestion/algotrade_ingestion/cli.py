"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest universe-build [--date YYYY-MM-DD] [--review-out leveraged_candidates.csv]
    algotrade-ingest company-details [--date D] [--force] [--limit N]   (SEC EDGAR)
    algotrade-ingest earnings [--date D] [--start D] [--days 60]
    algotrade-ingest bars [--date D | --from D --to D] [--force]   (needs a Massive API key)
    algotrade-ingest corporate-actions [--date D] [--from D --to D]
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers 4] [--symbols SPY,AAPL]
    algotrade-ingest features [--date YYYY-MM-DD]
    algotrade-ingest screen   [--date YYYY-MM-DD] [--config ID] [--user U] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/]
    algotrade-ingest purge-raw --keep-days 90
    algotrade-ingest migrate-ids [--dry-run]   (symbol ids -> FIGI ids, append-only)
    algotrade-ingest golden build|verify|load [--golden-dir datasets/golden]

Storage location comes from ALGOTRADE_DATA_URL (default file://./var/data).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from algotrade.config.user import SITE_USER
from algotrade.core.errors import AlgoTradeError
from algotrade.services.configs import default_user
from algotrade.storage.factory import open_backend
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.commands import (
    bars,
    cboe_source,
    company_details,
    corporate_actions,
    earnings,
    golden,
    migrate_ids,
    print_json,
    quality,
    report,
    run_job,
    universe_build,
)
from algotrade_ingestion.env import load_dotenv
from algotrade_ingestion.jobs.features import compute_option_liquidity
from algotrade_ingestion.jobs.option_chains import ChainJobConfig, ingest_option_chains
from algotrade_ingestion.jobs.universe import UniverseFile, import_universe
from algotrade_ingestion.pipeline import universe_underlyings
from algotrade_ingestion.schedule import LABEL, nightly_plist

EXCHANGE_TZ = ZoneInfo("America/New_York")


def last_session(now: datetime) -> date:
    """Most recent weekday in exchange time. Pass --date explicitly on exchange holidays."""
    day = now.astimezone(EXCHANGE_TZ).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _vendor_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Commands that pull one vendor dataset: company details and earnings."""
    cd = sub.add_parser("company-details", help="company details from SEC EDGAR (incremental)")
    cd.add_argument("--date", type=date.fromisoformat, help="session the snapshot belongs to")
    cd.add_argument("--force", action="store_true", help="refetch every company")
    cd.add_argument("--limit", type=int, help="fetch at most N companies this run")
    ea = sub.add_parser("earnings", help="store the Nasdaq earnings calendar as events")
    ea.add_argument("--date", type=date.fromisoformat, help="session the snapshot belongs to")
    ea.add_argument(
        "--start", type=date.fromisoformat, help="first calendar date (default: --date)"
    )
    ea.add_argument("--days", type=int, help="calendar days (default: sources.toml, 60)")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="algotrade-ingest", description=__doc__.splitlines()[0])
    p.add_argument(
        "--config-dir", help="site/user configs (default: $ALGOTRADE_CONFIG_DIR or ./config)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    u = sub.add_parser("universe", help="import the monthly master universe CSVs")
    u.add_argument("--stocks", type=Path, required=True)
    u.add_argument("--etfs", type=Path)
    u.add_argument("--version", required=True)
    u.add_argument("--date", type=date.fromisoformat)
    ub = sub.add_parser(
        "universe-build", help="build the universe from Nasdaq Trader + SPY holdings"
    )
    ub.add_argument("--date", type=date.fromisoformat)
    ub.add_argument("--review-out", type=Path, help="write leverage candidates to curate (CSV)")
    _vendor_parsers(sub)
    qa = sub.add_parser("quality", help="run the data-quality checks for a session")
    qa.add_argument("--date", type=date.fromisoformat)
    sc = sub.add_parser(
        "schedule", help="write a launchd agent for the nightly job (not installed)"
    )
    sc.add_argument("--time", default="23:30", help="local time HH:MM on weekdays (default 23:30)")
    sc.add_argument("--export-dir", type=Path, default=Path("out"))
    sc.add_argument("--out", type=Path, default=Path("var") / f"{LABEL}.plist")
    bb = sub.add_parser("bars", help="unadjusted daily bars from Massive (resumable backfill)")
    bb.add_argument("--date", type=date.fromisoformat, help="single session (default: last)")
    bb.add_argument("--from", dest="start", type=date.fromisoformat, help="backfill start")
    bb.add_argument("--to", dest="end", type=date.fromisoformat, help="backfill end")
    bb.add_argument("--force", action="store_true", help="re-fetch sessions already stored")
    ca = sub.add_parser("corporate-actions", help="splits and dividends from Massive")
    ca.add_argument("--date", type=date.fromisoformat)
    ca.add_argument("--from", dest="start", type=date.fromisoformat, help="default: date - 7d")
    ca.add_argument("--to", dest="end", type=date.fromisoformat, help="default: date + 30d")
    for name in ("chains", "features", "screen", "nightly"):
        s = sub.add_parser(name)
        s.add_argument("--date", type=date.fromisoformat)
        if name in ("chains", "nightly"):
            s.add_argument("--workers", type=int, default=4)
        if name == "chains":
            s.add_argument("--symbols", help="comma-separated subset of the universe")
        if name in ("screen", "nightly"):
            s.add_argument("--export-dir", type=Path)
        if name == "screen":
            s.add_argument("--config", default="short_premium_liquidity", help="config id")
            s.add_argument("--user", help="config owner (default: $ALGOTRADE_USER or site)")
    g = sub.add_parser(
        "golden", help="golden test datasets: build CSVs, verify, load into the store"
    )
    g.add_argument("action", choices=["build", "verify", "load"])
    g.add_argument("--golden-dir", type=Path, default=Path("datasets/golden"))
    mi = sub.add_parser("migrate-ids", help="rewrite stored ids per instruments/id_map (new runs)")
    mi.add_argument("--dry-run", action="store_true", help="count what would change; write nothing")
    r = sub.add_parser("purge-raw", help="delete raw vendor responses older than N days")
    r.add_argument("--keep-days", type=int, default=90)
    r.add_argument("--date", type=date.fromisoformat, help="reference date (default: today)")
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


def _dispatch(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    if args.command == "golden":
        return golden(args, writer)
    if args.command == "schedule":
        return write_schedule(args)
    if args.command == "migrate-ids":
        return migrate_ids(args, reader, writer)
    session = args.date if getattr(args, "date", None) else last_session(datetime.now(UTC))
    direct = {
        "universe-build": universe_build,
        "company-details": company_details,
        "earnings": earnings,
        "bars": bars,
        "corporate-actions": corporate_actions,
        "quality": quality,
    }
    if args.command in direct:
        return direct[args.command](args, reader, writer, session)
    return _pipeline_command(args, reader, writer, session)


def _pipeline_command(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    """universe import, chains, features, screen, nightly and purge-raw."""
    if args.command == "universe":
        files = [UniverseFile(args.stocks, "STOCK")] + (
            [UniverseFile(args.etfs, "ETF")] if args.etfs else []
        )
        record = import_universe(writer, reader, files, args.version, session, datetime.now(UTC))
        print_json(record.stats)
    elif args.command == "chains":
        underlyings = universe_underlyings(reader, session)
        if args.symbols:
            symbols = [s for s in args.symbols.split(",") if s.strip()]
            wanted = set(reader.resolver(session).ids_for(symbols).values())
            underlyings = [u for u in underlyings if u.instrument_id in wanted]
        run = ingest_option_chains(
            writer, cboe_source(), underlyings, session, ChainJobConfig(args.workers)
        )
        print_json({"run_id": run.run_id, "status": run.status, **run.stats})
        return 0 if run.status == "complete" else 1
    elif args.command == "features":
        print_json(compute_option_liquidity(reader, writer, session).stats)
    elif args.command == "screen":
        job = run_job(
            args,
            reader,
            writer,
            "screen",
            {
                "config": args.config,
                "session": session.isoformat(),
                "export_dir": str(args.export_dir) if args.export_dir else None,
            },
            args.user or default_user(SITE_USER).user_id,
        )
        return report(job)
    elif args.command == "nightly":
        params = {
            "session": session.isoformat(),
            "workers": args.workers,
            "export_dir": str(args.export_dir) if args.export_dir else None,
        }
        return report(run_job(args, reader, writer, "nightly", params, SITE_USER))
    else:
        removed = writer.raw.purge_before(session - timedelta(days=args.keep_days))
        print_json({"raw_files_removed": removed})
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
