"""A small merge-mode store for the ``compact-runs`` tests (``events/dividend``: days of runs
that rewrite the same rows), the context over it, and the entry points the real-process tests
start in another process (a function a ``spawn`` child can import)."""

import os
import signal
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.compaction import task
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import T0, stamped

TABLE = "events/dividend"
SESSION = date(2026, 10, 20)
BASE = {"EQ:A": 1.0, "EQ:B": 1.0, "EQ:C": 1.0}


def days_from(n: int) -> list[date]:
    return [date(2026, 9, 1) + timedelta(days=i) for i in range(n)]


def put(backend: LocalBackend, day: date, run: str, amounts: dict[str, float], k: int) -> None:
    """A committed run ``run`` of ``day`` (known at hour ``k``) writing ``amounts``."""
    ts = pd.Timestamp(day, tz="UTC")
    rows = [{"instrument_id": i, "ts": ts, "cash_amount": v} for i, v in amounts.items()]
    frame = stamped(rows, day, run, T0 + timedelta(hours=k))
    backend.tables.write(TABLE, day, run, frame, pending=True)
    backend.tables.commit_run(run, T0 + timedelta(days=30, hours=k))


def fill(backend: LocalBackend, days: list[date], runs: int = 4) -> None:
    """``runs`` identical rewrites per day: the middle ones are redundant."""
    for n, day in enumerate(days):
        for k in range(1, runs + 1):
            put(backend, day, f"{day:%m%d}r{k}", BASE, 10 * n + k)


def context(backend: LocalBackend, **keys: Any) -> TaskContext:
    document = {"compaction": {"tables": [TABLE], **keys}, "resources": {"min_free_gb": 0}}
    configs = MemoryConfigStore({("site", "settings", "nightly"): document})
    return replace(task_ctx(StoreWriter(backend)), configs=configs)


def partition_dir(root: Path, day: date) -> Path:
    return root / "tables" / TABLE / f"date={day.isoformat()}"


def rows_of(backend: LocalBackend, days: list[date]) -> dict[str, dict[str, float]]:
    """Day -> instrument -> amount, as a read sees it now."""
    out: dict[str, dict[str, float]] = {}
    for day in days:
        frame = backend.tables.read(TABLE, day)
        assert frame is not None
        out[day.isoformat()] = dict(zip(frame["instrument_id"], frame["cash_amount"], strict=True))
    return out


def leftovers(root: Path) -> list[str]:
    """Temp files of a write that never finished."""
    return sorted(p.name for p in root.rglob("*.tmp"))


def die_before_the_swap(root: str, day: str) -> None:
    """A child process: write and verify a compaction of ``day``, then be killed at the swap."""

    def kill(*args: object, **kwargs: object) -> bool:
        os.kill(os.getpid(), signal.SIGKILL)
        return False

    backend = LocalBackend(Path(root))
    backend.tables.commits.swap_runs = kill  # type: ignore[method-assign]
    backend.tables.compact_runs(TABLE, date.fromisoformat(day))


def run_job(root: str, workers: int, started: Any) -> None:
    """A child process: the whole job with real worker processes; ``started`` is set at the
    first progress line (partitions are in flight)."""
    backend = LocalBackend(Path(root))
    ctx = context(backend)

    def progress(line: str) -> None:
        if line.startswith("compact-runs [w"):
            started.set()

    task.compact(ctx, SESSION, TABLE, workers=workers, progress=progress, swap_grace_s=0.0)
