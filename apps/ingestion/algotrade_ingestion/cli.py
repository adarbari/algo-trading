"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers 4] [--symbols SPY,AAPL]
    algotrade-ingest features [--date YYYY-MM-DD]
    algotrade-ingest screen   [--date YYYY-MM-DD] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/]
    algotrade-ingest purge-raw --keep-days 90
    algotrade-ingest golden build|verify|load [--golden-dir datasets/golden]

Storage location comes from ALGOTRADE_DATA_URL (default file://./var/data).
"""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from algotrade.core.errors import AlgoTradeError
from algotrade.services.exports import write_legacy_exports
from algotrade.services.screening import run_screener
from algotrade.storage.factory import open_backend
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.features import compute_option_liquidity
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.jobs.option_chains import ChainJobConfig, ingest_option_chains
from algotrade_ingestion.jobs.universe import UniverseFile, import_universe
from algotrade_ingestion.pipeline import run_nightly, universe_underlyings
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import urllib_transport
from algotrade_ingestion.sources.synthetic.catalog import build_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles

EXCHANGE_TZ = ZoneInfo("America/New_York")


def last_session(now: datetime) -> date:
    """Most recent weekday in exchange time. Pass --date explicitly on exchange holidays."""
    day = now.astimezone(EXCHANGE_TZ).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="algotrade-ingest", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    u = sub.add_parser("universe", help="import the monthly master universe CSVs")
    u.add_argument("--stocks", type=Path, required=True)
    u.add_argument("--etfs", type=Path)
    u.add_argument("--version", required=True)
    u.add_argument("--date", type=date.fromisoformat)
    for name in ("chains", "features", "screen", "nightly"):
        s = sub.add_parser(name)
        s.add_argument("--date", type=date.fromisoformat)
        if name in ("chains", "nightly"):
            s.add_argument("--workers", type=int, default=4)
        if name == "chains":
            s.add_argument("--symbols", help="comma-separated subset of the universe")
        if name in ("screen", "nightly"):
            s.add_argument("--export-dir", type=Path)
    g = sub.add_parser(
        "golden", help="golden test datasets: build CSVs, verify, load into the store"
    )
    g.add_argument("action", choices=["build", "verify", "load"])
    g.add_argument("--golden-dir", type=Path, default=Path("datasets/golden"))
    r = sub.add_parser("purge-raw", help="delete raw vendor responses older than N days")
    r.add_argument("--keep-days", type=int, default=90)
    r.add_argument("--date", type=date.fromisoformat, help="reference date (default: today)")
    return p


def _source() -> CboeOptionsSource:
    return CboeOptionsSource(urllib_transport(), time.sleep)


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _golden(args: argparse.Namespace, writer: StoreWriter) -> int:
    files = GoldenFiles(args.golden_dir)
    if args.action == "build":
        _print({"built": build_golden(files)})
        return 0
    if args.action == "verify":
        problems = files.verify()
        _print({"ok": not problems, "problems": problems})
        return 1 if problems else 0
    _print(load_golden(writer, files).stats)
    return 0


def _dispatch(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    if args.command == "golden":
        return _golden(args, writer)
    session = args.date if getattr(args, "date", None) else last_session(datetime.now(UTC))
    if args.command == "universe":
        files = [UniverseFile(args.stocks, "STOCK")] + (
            [UniverseFile(args.etfs, "ETF")] if args.etfs else []
        )
        _print(import_universe(writer, files, args.version, session, datetime.now(UTC)).stats)
    elif args.command == "chains":
        underlyings = universe_underlyings(reader, session)
        if args.symbols:
            wanted = {s.strip().upper() for s in args.symbols.split(",")}
            underlyings = [u for u in underlyings if u.symbol in wanted]
        run = ingest_option_chains(
            writer, _source(), underlyings, session, ChainJobConfig(args.workers)
        )
        _print({"run_id": run.run_id, "status": run.status, **run.stats})
        return 0 if run.status == "complete" else 1
    elif args.command == "features":
        _print(compute_option_liquidity(reader, writer, session).stats)
    elif args.command == "screen":
        outcome = run_screener(reader, writer, "short_premium_liquidity", session)
        if args.export_dir:
            write_legacy_exports(outcome, args.export_dir, session.isoformat())
        _print(outcome.audit)
    elif args.command == "nightly":
        result = run_nightly(
            reader, writer, _source(), session, args.export_dir, ChainJobConfig(args.workers)
        )
        _print(
            {
                "chains": result.chains.stats,
                "features": result.features.stats,
                "screens": [s.audit for s in result.screens],
                "exports": result.exports,
            }
        )
    else:
        removed = writer.raw.purge_before(session - timedelta(days=args.keep_days))
        _print({"raw_files_removed": removed})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    backend = open_backend()
    try:
        return _dispatch(args, StoreReader(backend), StoreWriter(backend))
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
