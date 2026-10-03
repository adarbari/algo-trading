"""Implementations of ``algotrade-ingest`` commands.

Task commands are generic: ``run_task_command`` asks the source registry
(``sources/registry.py``) for the sources a registry task declares and runs it
(``tasks/registry.py``). Nightly and screens run as jobs through the job service
(``run_job``; apps never build a runner). Tests replace sources
through ``sources.registry.SOURCES`` (no network in CI).
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.jobs import JobHandler, JobKind, JobRecord, JobStatus
from algotrade.services.jobs import run_job as run_service_job
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_config_store
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.env import credential
from algotrade_ingestion.settings import SourcesSettings, load_sources
from algotrade_ingestion.sources.base import Source
from algotrade_ingestion.sources.registry import Built, build_sources
from algotrade_ingestion.sources.synthetic.catalog import build_golden
from algotrade_ingestion.sources.synthetic.files import GoldenFiles
from algotrade_ingestion.tasks.framework import TaskContext, run_summary
from algotrade_ingestion.tasks.registry import TASKS, Task, run_task, task
from algotrade_ingestion.workflows.nightly import FINALLY, NIGHTLY, nightly_job

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
    """Run one job to completion through the job service (an explicit re-run: force=True).
    The caller holds the ingest run lock, so a queued/running job of ``LOCKED_KINDS`` was
    left by a crashed process: it is marked failed first, or it would block this re-run."""
    settings = sources_settings(args)
    steps = [s.name for s in (*NIGHTLY, *FINALLY) if s.name in TASKS]
    names = [n for t in steps for n in (*task(t).sources, *task(t).optional_sources)]
    built = sources_for(names, settings)
    resources: dict[str, object] = {
        "reader": reader,
        "writer": writer,
        "configs": open_config_store(args.config_dir),
        "sources_settings": settings,
        "sources": built.sources,
        "unavailable": built.skipped,
    }
    handlers: dict[str, JobKind | JobHandler] = {**LIBRARY_HANDLERS, "nightly": nightly_job}
    user_ctx = UserContext(user)
    return run_service_job(
        writer.runs_backend, handlers, resources, kind, params, user_ctx, recover=LOCKED_KINDS
    )


def report(job: JobRecord) -> int:
    if job.status is JobStatus.FAILED:
        print(f"error: {job.error}", file=sys.stderr)
        return 2
    print_json({"job_id": job.job_id, "status": job.status, "job_status": job.status, **job.result})
    if job.result.get("status") == "FAILED":  # a workflow none of whose steps succeeded
        return 2
    return 0 if job.status is JobStatus.COMPLETE else 1
