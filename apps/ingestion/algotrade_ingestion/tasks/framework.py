"""``IngestRun``: the ingest loop, written once (ADR 0019, "The ingest loop is written once").

Every ingestion task runs inside one ``IngestRun``, which owns:

- the run id and run record (``new_run_id``; resumable runs pick up an unfinished record);
- ``fetch``: the vendor call, the raw payload saved as received, then normalisation;
- per-item status (``attempt`` / ``record`` / ``fail``) with exception capture;
- ticker -> instrument id resolution through ``algotrade.data`` (one resolver per reference
  snapshot, unresolved tickers counted);
- point-in-time stamping (``session_date``, ``knowledge_ts``, ``source``, ``run_id``) and
  validated writes (``write``, ``stage`` / ``publish`` for per-item scratch);
- the run status, decided in one place: any failed item or explicit ``partial`` -> PARTIAL;
  an exception escaping the ``with`` block -> FAILED, saved, then re-raised; else COMPLETE.

Tasks keep only their own logic: what to fetch, how to combine frames, task-specific stats.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Self

import pandas as pd

from algotrade.config.user import SITE_USER
from algotrade.data import StoreReader
from algotrade.data.reference import resolver as reference_resolver
from algotrade.data.reference import snapshot
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.config_store import ConfigStore
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.settings import SourcesSettings
from algotrade_ingestion.sources.base import FetchRequest, Normalized, Source

REFERENCE = "instruments/reference"
FETCH_ERROR = "FETCH_ERROR"
# Item statuses that make a run PARTIAL. ``FETCH_ERROR`` items are retried on resume.
FAILURES = (FETCH_ERROR, "STALE_DATA", "FAILED")


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TaskContext:
    """What a task runs against: storage, built sources (by name), settings and a clock."""

    reader: StoreReader
    writer: StoreWriter
    sources: Mapping[str, Source] = field(default_factory=dict)
    settings: SourcesSettings = field(default_factory=SourcesSettings)
    configs: ConfigStore | None = None
    clock: Callable[[], datetime] = utc_now
    user: str = SITE_USER


class NoResponseError(LookupError):
    """The vendor had nothing for a request (``Source.fetch`` returned ``None``)."""


def stamp(
    frame: pd.DataFrame, session_date: date, now: datetime, source: str, run_id: str
) -> pd.DataFrame:
    """Add the point-in-time columns every stored row needs (ADR 0007)."""
    out = frame.copy()
    out["session_date"] = session_date
    out["knowledge_ts"] = pd.Timestamp(now)
    out["source"] = source
    out["run_id"] = run_id
    return out


def status_label(status: str) -> str:
    return status.split(":", 1)[0]


class IngestRun:
    """One run of one task. Use as a context manager; the record is saved on exit."""

    def __init__(
        self,
        ctx: TaskContext,
        task: str,
        session: date,
        *,
        resume: bool = False,
        save: bool = True,
    ) -> None:
        self.ctx, self.task, self.session, self._save = ctx, task, session, save
        self.writer, self.reader, self.clock = ctx.writer, ctx.reader, ctx.clock
        self.stats: dict[str, Any] = {}
        self.unresolved = 0
        self._resolved = False
        self._partial: list[str] = []
        self._resolvers: dict[date | None, SymbolResolver] = {}
        resumed = self._resume() if resume else None
        now = self.clock()
        self.record = resumed or RunRecord(new_run_id(task, session, now), task, session, now)

    # ------------------------------------------------------------------ lifecycle

    @property
    def run_id(self) -> str:
        return self.record.run_id

    @property
    def items(self) -> dict[str, str]:
        return self.record.items

    def _resume(self) -> RunRecord | None:
        """The last unfinished run of this task for the session, minus its retryable items."""
        runs = self.writer.runs_for(self.task, self.session)
        unfinished = [r for r in runs if r.status is not RunStatus.COMPLETE]
        if not unfinished:
            return None
        record = unfinished[-1]
        record.items = {k: v for k, v in record.items.items() if status_label(v) != FETCH_ERROR}
        record.status, record.finished_at = RunStatus.RUNNING, None
        return record

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is not None:
            self.stats["error"] = f"{type(exc).__name__}: {exc}"
            self._finish(RunStatus.FAILED)
            return  # re-raised by the interpreter
        self._finish(self.status())

    def status(self) -> RunStatus:
        """The status rule, in one place: failed items or explicit partial -> PARTIAL."""
        return RunStatus.PARTIAL if self.failures() or self._partial else RunStatus.COMPLETE

    def _finish(self, status: RunStatus) -> None:
        self.record.status, self.record.finished_at = status, self.clock()
        if self._resolved:
            self.stats.setdefault("unresolved", self.unresolved)
        if self._partial:
            self.stats["partial"] = self._partial
        self.record.stats = self.stats
        if self._save:
            self.writer.save_run(self.record)

    def checkpoint(self) -> None:
        """Save the record so far (resumable runs, long backfills)."""
        if self._save:
            self.writer.save_run(self.record)

    def partial(self, reason: str) -> None:
        """Mark the run PARTIAL for a reason that is not one item's failure."""
        self._partial.append(reason)

    # ------------------------------------------------------------------ items

    def record_item(self, key: str, status: str) -> None:
        self.items[key] = status

    def fail(self, key: str, reason: str, kind: str = FETCH_ERROR) -> None:
        assert kind in FAILURES, kind
        self.items[key] = f"{kind}: {reason}"

    def attempt(self, key: str, fn: Callable[[], str]) -> str:
        """Run one item; its return value is the item status, an exception a failure."""
        try:
            status = fn()
        except Exception as exc:
            self.fail(key, str(exc))
        else:
            self.items[key] = status
        return self.items[key]

    def failures(self) -> list[str]:
        """``"key: reason"`` for every failed item, in item order."""
        return [
            f"{k}: {v.split(': ', 1)[-1]}"
            for k, v in self.items.items()
            if status_label(v) in FAILURES
        ]

    def counts(self) -> dict[str, int]:
        """Items per status label (``OK``, ``NO_CHAIN``, ``FETCH_ERROR``...)."""
        out: dict[str, int] = {}
        for status in self.items.values():
            out[status_label(status)] = out.get(status_label(status), 0) + 1
        return out

    # ------------------------------------------------------------------ fetch

    def fetch(
        self, source: Source, request: FetchRequest, raw_key: str | None = None
    ) -> Normalized | None:
        """Fetch, save the raw payload as received, normalise. Raises ``NoResponseError``."""
        payload = source.fetch(request)
        if payload is None:
            raise NoResponseError(f"{source.name} {request.key}: no response")
        key = raw_key or request.key
        self.writer.raw.put(source.name, source.dataset, self.session, self.run_id, key, payload)
        return source.normalize(request, payload)

    # ------------------------------------------------------------------ ids

    def resolver(self, as_of: date | None = None) -> SymbolResolver:
        """The ticker -> id resolver as of ``as_of`` (default: the session), one per snapshot."""
        day = as_of or self.session
        snap = snapshot(self.reader, REFERENCE, day)
        key = snap.snapshot_date if snap else None
        if key not in self._resolvers:
            self._resolvers[key] = reference_resolver(self.reader, day)
        return self._resolvers[key]

    def resolve(
        self, frame: pd.DataFrame, as_of: date | None = None, keep_symbol: bool = True
    ) -> pd.DataFrame:
        """A vendor frame keyed by ``symbol`` -> ``instrument_id`` (ADR 0018). Frames that
        already carry ids pass; unknown tickers keep symbol ids and count as unresolved."""
        self._resolved = True
        if "instrument_id" in frame.columns or (frame.empty and "symbol" not in frame.columns):
            return frame
        out, unknown = self.resolver(as_of).resolve(frame)
        self.unresolved += unknown
        return out if keep_symbol else out.drop(columns="symbol")

    # ------------------------------------------------------------------ writes

    def stamped(
        self, frame: pd.DataFrame, source: str, session: date | None = None
    ) -> pd.DataFrame:
        return stamp(frame, session or self.session, self.clock(), source, self.run_id)

    def write(
        self, table: str, frame: pd.DataFrame, source: str, session: date | None = None
    ) -> None:
        """Stamp and write one partition (validated against the table schema)."""
        day = session or self.session
        self.writer.write_table(table, day, self.run_id, self.stamped(frame, source, day))

    def rewrite(self, table: str, day: date, frame: pd.DataFrame) -> None:
        """Re-publish already-stamped rows as this run (new ``knowledge_ts`` and ``run_id``)."""
        out = frame.assign(knowledge_ts=pd.Timestamp(self.clock()), run_id=self.run_id)
        self.writer.write_table(table, day, self.run_id, out)

    def stage(self, table: str, key: str, frame: pd.DataFrame, source: str) -> None:
        """Stamp one item's rows into run scratch; ``publish`` writes them as one partition."""
        self.writer.staging.put(self.run_id, table, key, self.stamped(frame, source))

    def publish(self, table: str, sort_by: str = "instrument_id") -> int:
        """Write a staged table as one partition (``knowledge_ts`` = publish time)."""
        frame = self.writer.staging.collect(self.run_id, table)
        if frame is None:
            return 0
        frame = frame.sort_values(sort_by, kind="stable").reset_index(drop=True)
        frame["knowledge_ts"] = pd.Timestamp(self.clock())
        self.writer.write_table(table, self.session, self.run_id, frame)
        return len(frame)

    def clear_staging(self) -> None:
        self.writer.staging.clear(self.run_id)


def run_summary(record: RunRecord) -> Mapping[str, Any]:
    """What CLI commands print for a task run."""
    return {"run_id": record.run_id, "status": record.status, **record.stats}
