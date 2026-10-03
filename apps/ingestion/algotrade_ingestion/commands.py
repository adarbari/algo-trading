"""Implementations of ``algotrade-ingest`` commands and the vendor source factories.

Task commands are generic: ``run_task_command`` builds the sources a registry task declares
and runs it (``tasks/registry.py``). Nightly and screens run as jobs (``run_job``). Source
factories are module-level so tests can replace them with fakes (no network in CI).
"""

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.jobs import JobRecord, JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_config_store
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.env import massive_key, sec_contact
from algotrade_ingestion.pipeline import NIGHTLY, nightly_job
from algotrade_ingestion.settings import SourcesSettings, load_sources
from algotrade_ingestion.sources.base import Source
from algotrade_ingestion.sources.cboe import CboeOptionsSource
from algotrade_ingestion.sources.http import BROWSER_USER_AGENT, MinInterval, urllib_transport
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
from algotrade_ingestion.tasks.framework import TaskContext, run_summary
from algotrade_ingestion.tasks.registry import TASKS, Task, run_task, task


def sources_settings(args: argparse.Namespace) -> SourcesSettings:
    return load_sources(open_config_store(getattr(args, "config_dir", None)))


# ----------------------------------------------------------------------------- sources
# Source construction stays here until the source registry (roadmap R4). Each factory returns
# the sources of one vendor by name; ``required`` vendors raise on missing credentials,
# optional ones (nightly) are left out when disabled in sources.toml or not configured.


def cboe_sources(settings: SourcesSettings, required: bool = True) -> dict[str, Source]:
    return {"cboe": CboeOptionsSource(urllib_transport(), time.sleep)}


def earnings_sources(settings: SourcesSettings, required: bool = True) -> dict[str, Source]:
    if not required and not settings.earnings_enabled:
        return {}
    transport = urllib_transport(BROWSER_USER_AGENT)
    source = NasdaqEarningsSource(transport, time.sleep, pause_s=settings.earnings_pause_s)
    return {"nasdaq_earnings": source}


def sec_sources(settings: SourcesSettings, required: bool = True) -> dict[str, Source]:
    """SEC EDGAR sources sharing one rate limiter; nothing without a contact email."""
    contact = sec_contact(required) if required or settings.sec_enabled else None
    if contact is None:
        return {}
    transport = urllib_transport(user_agent(contact))
    limiter = MinInterval(settings.sec_min_interval_s, time.sleep)
    return {
        "sec_tickers": SecTickerMap(transport, time.sleep, limiter=limiter),
        "sec_submissions": SecSubmissions(transport, time.sleep, limiter=limiter),
    }


def massive_sources(settings: SourcesSettings, required: bool = True) -> dict[str, Source]:
    """Bars, corporate actions and the ticker list, paced by ``[massive] min_interval_s``."""
    key = massive_key(required) if required or settings.massive_enabled else None
    if key is None:
        return {}
    transport = urllib_transport(headers={"Authorization": f"Bearer {key}"})
    pace = settings.massive_min_interval_s
    return {
        "massive_bars": MassiveDailyBars(transport, time.sleep, min_interval_s=pace),
        "massive_corporate_actions": MassiveCorporateActions(
            transport, time.sleep, min_interval_s=pace
        ),
        "massive_tickers": MassiveTickers(transport, time.sleep, min_interval_s=pace),
    }


def universe_sources(settings: SourcesSettings, required: bool = True) -> dict[str, Source]:
    if not required and not settings.universe_enabled:
        return {}
    transport = urllib_transport()
    return {
        "nasdaq_trader": NasdaqTraderSource(transport, time.sleep),
        "spy_holdings": SpyHoldingsSource(transport, time.sleep),
    }


VENDOR = {
    "cboe": "cboe",
    "nasdaq_earnings": "earnings",
    "sec_tickers": "sec",
    "sec_submissions": "sec",
    "massive_bars": "massive",
    "massive_corporate_actions": "massive",
    "massive_tickers": "massive",
    "nasdaq_trader": "universe",
    "spy_holdings": "universe",
}


def _vendor(vendor: str, settings: SourcesSettings, required: bool) -> dict[str, Source]:
    factories = {
        "cboe": cboe_sources,
        "earnings": earnings_sources,
        "sec": sec_sources,
        "massive": massive_sources,
        "universe": universe_sources,
    }
    return factories[vendor](settings, required)


def build_sources(
    names: Iterable[str], settings: SourcesSettings, required: bool = True
) -> dict[str, Source]:
    """The named sources (see ``VENDOR``); with ``required=False`` unavailable ones are left
    out instead of raising."""
    wanted = list(dict.fromkeys(names))
    built: dict[str, Source] = {}
    for vendor in dict.fromkeys(VENDOR[n] for n in wanted):
        built.update(_vendor(vendor, settings, required))
    return {n: built[n] for n in wanted if n in built}


def task_sources(spec: Task, settings: SourcesSettings) -> dict[str, Source]:
    """An explicit run: required sources must be configured, optional ones may be missing."""
    return {
        **build_sources(spec.optional_sources, settings, required=False),
        **build_sources(spec.sources, settings, required=True),
    }


# ----------------------------------------------------------------------------- tasks


def task_context(
    args: argparse.Namespace,
    reader: StoreReader,
    writer: StoreWriter,
    sources: Mapping[str, Source] | None = None,
) -> TaskContext:
    return TaskContext(
        reader,
        writer,
        sources or {},
        sources_settings(args),
        open_config_store(getattr(args, "config_dir", None)),
    )


def run_task_command(
    args: argparse.Namespace,
    reader: StoreReader,
    writer: StoreWriter,
    name: str,
    params: Mapping[str, Any],
) -> int:
    """Run one registry task with the sources it declares; print its run summary."""
    spec = task(name)
    ctx = task_context(args, reader, writer)
    ctx.sources = task_sources(spec, ctx.settings)
    record = run_task(name, ctx, params)
    print_json(run_summary(record))
    return 0 if record.status == "complete" else 1


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def golden(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    """``golden build|verify`` (files only); ``golden load`` is the ``golden-load`` task."""
    files = GoldenFiles(args.golden_dir)
    if args.action == "build":
        print_json({"built": build_golden(files)})
        return 0
    if args.action == "verify":
        problems = files.verify()
        print_json({"ok": not problems, "problems": problems})
        return 1 if problems else 0
    return run_task_command(args, reader, writer, "golden-load", {"golden_dir": args.golden_dir})


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
    names = [
        n for t in NIGHTLY if t in TASKS for n in (*task(t).sources, *task(t).optional_sources)
    ]
    resources: dict[str, object] = {
        "reader": reader,
        "writer": writer,
        "configs": open_config_store(args.config_dir),
        "sources_settings": settings,
        "sources": build_sources(names, settings, required=False),
    }
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
