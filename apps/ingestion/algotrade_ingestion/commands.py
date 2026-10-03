"""Implementations of ``algotrade-ingest`` commands.

Task commands are generic: ``run_task_command`` asks the source registry
(``sources/registry.py``) for the sources a registry task declares and runs it
(``tasks/registry.py``). Nightly and screens run as jobs (``run_job``). Tests replace sources
through ``sources.registry.SOURCES`` (no network in CI).
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.jobs import JobRecord, JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_config_store
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.env import credential
from algotrade_ingestion.pipeline import NIGHTLY, nightly_job
from algotrade_ingestion.settings import SourcesSettings, load_sources
from algotrade_ingestion.sources.base import Source
from algotrade_ingestion.sources.registry import Built, build_sources
from algotrade_ingestion.sources.synthetic.catalog import build_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from algotrade_ingestion.tasks.framework import TaskContext, run_summary
from algotrade_ingestion.tasks.registry import TASKS, Task, run_task, task

# Job kinds this app runs under the ingest run lock: safe to recover at once (see cli.main).
LOCKED_KINDS = ("nightly", "screen")


def sources_settings(args: argparse.Namespace) -> SourcesSettings:
    return load_sources(open_config_store(getattr(args, "config_dir", None)))


def sources_for(names: Iterable[str], settings: SourcesSettings) -> Built:
    """The named sources from the registry (credentials from the environment)."""
    return build_sources(settings, credential, names)


def task_sources(spec: Task, settings: SourcesSettings) -> Built:
    """An explicit run: every required source must be available, else a clear error."""
    built = sources_for((*spec.sources, *spec.optional_sources), settings)
    missing = [s for s in spec.sources if s not in built.sources]
    if missing:
        reasons = sorted({built.skipped[s] for s in missing})
        raise ConfigurationError(f"{spec.name} skipped: {'; '.join(reasons)}")
    return built


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
    built = task_sources(spec, ctx.settings)
    ctx.sources, ctx.unavailable = built.sources, built.skipped
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
    built = sources_for(names, settings)
    resources: dict[str, object] = {
        "reader": reader,
        "writer": writer,
        "configs": open_config_store(args.config_dir),
        "sources_settings": settings,
        "sources": built.sources,
        "unavailable": built.skipped,
    }
    runner = LocalJobRunner(
        writer.runs_backend, {**LIBRARY_HANDLERS, "nightly": nightly_job}, resources
    )
    # The caller holds the ingest run lock, so a queued/running job of these kinds was left
    # by a crashed process: mark it failed now, or it would block this re-run.
    runner.recover(timedelta(0), LOCKED_KINDS)
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
