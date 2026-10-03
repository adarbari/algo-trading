"""Implementations of ``algotrade-ingest`` commands and the vendor source factories.

Each command takes the parsed arguments plus a reader and writer and returns an exit code.
Source factories are module-level so tests can replace them with fakes (no network in CI).
"""

import argparse
import csv
import json
import sys
import time
from datetime import date, timedelta

from algotrade.config.user import UserContext
from algotrade.services.jobs import JobRecord, JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_config_store
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.env import massive_key, sec_contact
from algotrade_ingestion.jobs.bars import (
    ingest_corporate_actions,
    ingest_daily_bars,
    sessions_between,
)
from algotrade_ingestion.jobs.company_details import CompanySources, ingest_company_details
from algotrade_ingestion.jobs.earnings import ingest_earnings
from algotrade_ingestion.jobs.golden import load_golden
from algotrade_ingestion.jobs.quality import run_quality
from algotrade_ingestion.jobs.universe_build import UniverseSources, build_universe, review_rows
from algotrade_ingestion.pipeline import nightly_job, universe_settings
from algotrade_ingestion.settings import SourcesSettings, load_sources
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import (
    BROWSER_USER_AGENT,
    MinInterval,
    Transport,
    urllib_transport,
)
from algotrade_ingestion.sources.massive import (
    MassiveCorporateActions,
    MassiveDailyBars,
    MassiveTickers,
)
from algotrade_ingestion.sources.nasdaq_earnings import NasdaqEarningsSource
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.sec_edgar import SecSubmissions, SecTickerMap, user_agent
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
from algotrade_ingestion.sources.synthetic.catalog import build_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles


def sources_settings(args: argparse.Namespace) -> SourcesSettings:
    return load_sources(open_config_store(getattr(args, "config_dir", None)))


def cboe_source(settings: SourcesSettings | None = None) -> CboeOptionsSource:
    return CboeOptionsSource(urllib_transport(), time.sleep)


def earnings_source(settings: SourcesSettings | None = None) -> NasdaqEarningsSource:
    pause = (settings or SourcesSettings()).earnings_pause_s
    return NasdaqEarningsSource(urllib_transport(BROWSER_USER_AGENT), time.sleep, pause_s=pause)


def earnings(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    settings = sources_settings(args)
    record = ingest_earnings(
        writer, earnings_source(settings), session, args.start, args.days or settings.earnings_days
    )
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def company_sources(
    settings: SourcesSettings | None = None, required: bool = True
) -> CompanySources | None:
    """SEC EDGAR sources sharing one rate limiter. ``None`` when the contact email is unset
    and not ``required`` (the nightly step is then skipped)."""
    s = settings or SourcesSettings()
    contact = sec_contact(required)
    if contact is None:
        return None
    transport = urllib_transport(user_agent(contact))
    limiter = MinInterval(s.sec_min_interval_s, time.sleep)
    return CompanySources(
        SecTickerMap(transport, time.sleep, limiter=limiter),
        SecSubmissions(transport, time.sleep, limiter=limiter),
        s.sec_refresh_days,
    )


def company_details(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    sources = company_sources(sources_settings(args))
    assert sources is not None  # required=True raises instead
    record = ingest_company_details(writer, reader, sources, session, args.force, args.limit)
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def massive_transport() -> Transport:
    return urllib_transport(headers={"Authorization": f"Bearer {massive_key()}"})


def massive_sources(settings: SourcesSettings | None = None) -> dict[str, object]:
    """Nightly bars + corporate actions, only when enabled and a Massive key is configured."""
    s = settings or SourcesSettings()
    if not s.massive_enabled or massive_key(required=False) is None:
        return {}
    transport = massive_transport()
    return {
        "bars_source": MassiveDailyBars(
            transport, time.sleep, min_interval_s=s.massive_min_interval_s
        ),
        "actions_source": MassiveCorporateActions(
            transport, time.sleep, min_interval_s=s.massive_min_interval_s
        ),
    }


def quality(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    record = run_quality(reader, writer, session, sources_settings(args))
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def bars(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date) -> int:
    sessions = sessions_between(args.start or session, args.end or session)
    source = MassiveDailyBars(massive_transport(), time.sleep)
    record = ingest_daily_bars(writer, reader, source, sessions, force=args.force)
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def corporate_actions(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    start, end = args.start or session - timedelta(7), args.end or session + timedelta(30)
    source = MassiveCorporateActions(massive_transport(), time.sleep)
    record = ingest_corporate_actions(writer, source, session, start, end)
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def universe_sources() -> UniverseSources:
    transport = urllib_transport()
    tickers = None
    if massive_key(required=False) is not None:  # FIGI / CIK / vendor types need the key
        tickers = MassiveTickers(massive_transport(), time.sleep)
    return UniverseSources(
        NasdaqTraderSource(transport, time.sleep), SpyHoldingsSource(transport, time.sleep), tickers
    )


def universe_build(
    args: argparse.Namespace, reader: StoreReader, writer: StoreWriter, session: date
) -> int:
    _, settings = universe_settings(open_config_store(args.config_dir))
    record = build_universe(writer, reader, universe_sources(), settings, session)
    if args.review_out:
        reference = reader.table("instruments/reference", session)
        rows = review_rows(reference) if reference is not None else []
        args.review_out.parent.mkdir(parents=True, exist_ok=True)
        with args.review_out.open("w", newline="") as fh:
            out = csv.DictWriter(fh, fieldnames=["symbol", "leverage", "tracks", "notes"])
            out.writeheader()
            out.writerows(rows)
        record.stats["review_out"] = str(args.review_out)
    print_json({"run_id": record.run_id, "status": record.status, **record.stats})
    return 0 if record.status == "complete" else 1


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def golden(args: argparse.Namespace, writer: StoreWriter) -> int:
    files = GoldenFiles(args.golden_dir)
    if args.action == "build":
        print_json({"built": build_golden(files)})
        return 0
    if args.action == "verify":
        problems = files.verify()
        print_json({"ok": not problems, "problems": problems})
        return 1 if problems else 0
    print_json(load_golden(writer, files).stats)
    return 0


def run_job(
    args: argparse.Namespace,
    reader: StoreReader,
    writer: StoreWriter,
    kind: str,
    params: dict[str, object],
    user: str,
) -> JobRecord:
    """Run one job to completion through the local runner (an explicit re-run: force=True)."""
    settings = sources_settings(args)
    resources: dict[str, object] = {
        "reader": reader,
        "writer": writer,
        "source": cboe_source(settings),
        "configs": open_config_store(args.config_dir),
        "sources_settings": settings,
        **massive_sources(settings),
    }
    if settings.universe_enabled:
        resources["universe_sources"] = universe_sources()
    if settings.earnings_enabled:
        resources["earnings_source"] = earnings_source(settings)
    if settings.sec_enabled:
        resources["company_sources"] = company_sources(settings, required=False)
    runner = LocalJobRunner(
        writer.runs_backend, {**LIBRARY_HANDLERS, "nightly": nightly_job}, resources
    )
    try:
        return runner.wait(runner.submit(kind, params, UserContext(user), force=True))
    finally:
        runner.shutdown()


def report(job: JobRecord) -> int:
    if job.status is JobStatus.FAILED:
        print(f"error: {job.error}", file=sys.stderr)
        return 2
    print_json({"job_id": job.job_id, "status": job.status, **job.result})
    return 0 if job.status is JobStatus.COMPLETE else 1
