"""Implementations of ``algotrade-ingest`` commands.

Task commands are generic: ``run_task_command`` asks the source registry
(``sources/framework/registry.py``) for the sources a registry task declares and runs it
(``tasks/framework/registry.py``). Nightly and screens run as jobs through the job service
(``run_job``; apps never build a runner). Tests replace sources
through ``sources.registry.SOURCES`` (no network in CI).
"""

import argparse
import dataclasses
import json
import sys
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.config.env import config_dir, credential
from algotrade.config.site.settings import SourcesSettings, load_nightly, load_sources
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.jobs import JobHandler, JobKind, JobRecord, JobStatus
from algotrade.services.jobs import run_job as run_service_job
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_config_store
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.base import Source
from algotrade_ingestion.sources.framework.registry import (
    RAW_SECTIONS,
    Built,
    build_sources,
    fixture_source,
)
from algotrade_ingestion.tasks.framework.registry import TASKS, Task, run_task, task
from algotrade_ingestion.tasks.framework.run import TaskContext, run_summary
from algotrade_ingestion.workflows.nightly import notify
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY, nightly_job
from algotrade_ingestion.workflows.nightly.records import stored_summary

# Job kinds this app runs under the ingest run lock: safe to recover at once (see cli.main).
LOCKED_KINDS = ("nightly", "screen")


def config_store(args: argparse.Namespace) -> ConfigStore:
    """``--config-dir``, else ``$ALGOTRADE_CONFIG_DIR``, else ./config."""
    return open_config_store(config_dir(getattr(args, "config_dir", None)))


def sources_settings(args: argparse.Namespace) -> SourcesSettings:
    return load_sources(config_store(args))


def sources_for(
    names: Iterable[str], settings: SourcesSettings, fixture_dir: Path | None = None
) -> Built:
    """The named sources from the registry (credentials from the environment)."""
    return build_sources(settings, credential, names, fixture_dir=fixture_dir)


def task_sources(spec: Task, settings: SourcesSettings, params: Mapping[str, Any]) -> Built:
    """An explicit run: every required source must be available, else a clear error.
    A fixture source reads the task's ``golden_dir`` parameter."""
    names = (*spec.sources, *spec.optional_sources)
    built = sources_for(names, settings, params.get("golden_dir"))
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
        config_store(args),
        raw_sections=RAW_SECTIONS,
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
    built = task_sources(spec, ctx.settings, params)
    ctx.sources, ctx.unavailable, ctx.pacing = built.sources, built.skipped, built.limiters
    record = run_task(name, ctx, params)
    print_json(run_summary(record))
    return 0 if record.status == "complete" else 1


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def golden(args: argparse.Namespace, reader: StoreReader, writer: StoreWriter) -> int:
    """``golden build|verify`` (files only); ``golden load`` is the ``golden-load`` task."""
    source = fixture_source("synthetic", args.golden_dir)
    if args.action == "build":
        print_json({"built": source.build()})
        return 0
    if args.action == "verify":
        problems = source.verify()
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
        "configs": config_store(args),
        "sources_settings": settings,
        "sources": built.sources,
        "unavailable": built.skipped,
        "raw_sections": RAW_SECTIONS,
        "pacing": built.limiters,
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


def nightly_report(args: argparse.Namespace, reader: StoreReader, session: date) -> int:
    """``report``: the nightly summary for a past session from its stored run records, as
    text (stdout), as HTML (``--out``) and, with ``--send``, by email (read-only)."""
    settings = load_nightly(config_store(args))
    summary = stored_summary(reader, session, [s.name for s in NIGHTLY])
    if summary is None:
        print(f"error: no nightly run record for {session}", file=sys.stderr)
        return 2
    examples = args.max_examples if args.max_examples is not None else settings.email_max_examples
    note, problem = notify.notice(
        summary, reader, dataclasses.replace(settings, email_max_examples=examples)
    )
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(note.html)
    print(note.text, end="")
    if args.send:
        sender = notify.EmailNotifier(notify.email_config(settings))
        if warning := sender.notify(note):
            print(f"warning: {warning}", file=sys.stderr)
            return 1
        print("email sent", file=sys.stderr)
    return 0
