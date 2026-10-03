"""``algotrade-ingest`` command line.

    algotrade-ingest universe --stocks optionable_us_stock_universe.csv \\
                              --etfs optionable_us_etf_universe.csv --version 2026-10
    algotrade-ingest universe-build [--date YYYY-MM-DD] [--review-out leveraged_candidates.csv]
    algotrade-ingest chains   [--date YYYY-MM-DD] [--workers 4] [--symbols SPY,AAPL]
    algotrade-ingest features [--date YYYY-MM-DD]
    algotrade-ingest screen   [--date YYYY-MM-DD] [--config ID] [--user U] [--export-dir out/]
    algotrade-ingest nightly  [--date YYYY-MM-DD] [--export-dir out/]
    algotrade-ingest purge-raw --keep-days 90
    algotrade-ingest golden build|verify|load [--golden-dir datasets/golden]

Storage location comes from ALGOTRADE_DATA_URL (default file://./var/data).
"""

import argparse
import csv
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.errors import AlgoTradeError
from algotrade.services.configs import default_user
from algotrade.services.jobs import JobRecord, JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.features import compute_option_liquidity
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.jobs.option_chains import ChainJobConfig, ingest_option_chains
from algotrade_ingestion.jobs.universe import UniverseFile, import_universe
from algotrade_ingestion.jobs.universe_build import UniverseSources, build_universe, review_rows
from algotrade_ingestion.pipeline import nightly_job, universe_settings, universe_underlyings
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import urllib_transport
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
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
    r = sub.add_parser("purge-raw", help="delete raw vendor responses older than N days")
    r.add_argument("--keep-days", type=int, default=90)
    r.add_argument("--date", type=date.fromisoformat, help="reference date (default: today)")
    return p


def _source() -> CboeOptionsSource:
    return CboeOptionsSource(urllib_transport(), time.sleep)


def _universe_sources() -> UniverseSources:
    transport = urllib_transport()
    return UniverseSources(
        NasdaqTraderSource(transport, time.sleep), SpyHoldingsSource(transport, time.sleep)
    )


def _universe_build(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    _, settings = universe_settings(open_config_store(args.config_dir))
    record = build_universe(writer, reader, _universe_sources(), settings, session)
    if args.review_out:
        reference = reader.table("instruments/reference", session)
        rows = review_rows(reference) if reference is not None else []
        args.review_out.parent.mkdir(parents=True, exist_ok=True)
        with args.review_out.open("w", newline="") as fh:
            out = csv.DictWriter(fh, fieldnames=["symbol", "leverage", "tracks", "notes"])
            out.writeheader()
            out.writerows(rows)
        record.stats["review_out"] = str(args.review_out)
    _print({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


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


def _run_job(
    args: argparse.Namespace,
    reader: StoreReader,
    writer: StoreWriter,
    kind: str,
    params: dict[str, object],
    user: str,
) -> JobRecord:
    """Run one job to completion through the local runner (an explicit re-run: force=True)."""
    resources = {
        "reader": reader,
        "writer": writer,
        "source": _source(),
        "universe_sources": _universe_sources(),
        "configs": open_config_store(args.config_dir),
    }
    runner = LocalJobRunner(
        writer.runs_backend, {**LIBRARY_HANDLERS, "nightly": nightly_job}, resources
    )
    try:
        return runner.wait(runner.submit(kind, params, UserContext(user), force=True))
    finally:
        runner.shutdown()


def _report(job: JobRecord) -> int:
    if job.status is JobStatus.FAILED:
        print(f"error: {job.error}", file=sys.stderr)
        return 2
    _print({"job_id": job.job_id, "status": job.status, **job.result})
    return 0 if job.status is JobStatus.COMPLETE else 1


def _dispatch(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    if args.command == "golden":
        return _golden(args, writer)
    session = args.date if getattr(args, "date", None) else last_session(datetime.now(UTC))
    if args.command == "universe-build":
        return _universe_build(args, reader, writer, session)
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
        job = _run_job(
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
        return _report(job)
    elif args.command == "nightly":
        params = {
            "session": session.isoformat(),
            "workers": args.workers,
            "export_dir": str(args.export_dir) if args.export_dir else None,
        }
        return _report(_run_job(args, reader, writer, "nightly", params, SITE_USER))
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
