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
  an exception escaping the ``with`` block -> FAILED, saved, then re-raised; an explicit
  ``failed`` (a workflow whose every step failed) -> FAILED; else COMPLETE;
- atomic publication (ADR 0022): every table write is pending until the run finishes; a
  COMPLETE or PARTIAL run commits all of them at once (``knowledge_ts`` stays the write
  time; reads pinned at ``as_of`` see the run from its commit time), a FAILED run drops
  them. ``run.reader`` also sees the run's own pending writes. ``recover_unpublished``
  (CLI start, under the ingest lock) completes interrupted commits and drops what crashed
  runs left;
- the run's staging (per-item scratch): dropped right after a successful commit when nothing
  is left for a resume to refetch (COMPLETE, or PARTIAL without ``RETRYABLE`` items); kept
  otherwise (retryable items, FAILED runs) so a resume can publish it, until
  ``staging_retention_days`` (``purge-raw``).

Tasks keep only their own logic: what to fetch, how to combine frames, task-specific stats.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Self

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.config.user import SITE_USER
from algotrade.data import StoreReader
from algotrade.data.reference import resolver as reference_resolver
from algotrade.data.reference import snapshot
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.runs import RunRecord, RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.base import FetchRequest, Normalized, Source

REFERENCE = "instruments/reference"
FETCH_ERROR = "FETCH_ERROR"
# Item statuses that make a run PARTIAL. ``RETRYABLE`` items are refetched on resume.
FAILURES = (FETCH_ERROR, "STALE_DATA", "FAILED")
RETRYABLE = (FETCH_ERROR,)
# Run statuses whose table writes are published (ADR 0022); FAILED publishes nothing.
PUBLISHED = (RunStatus.COMPLETE, RunStatus.PARTIAL)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TaskContext:
    """What a task runs against: storage, built sources (by name), settings and a clock.
    ``unavailable``: why each source the registry left out is missing (disabled, no key).
    ``raw_sections``: raw source name -> its ``sources.toml`` section (the source registry's
    ``RAW_SECTIONS``, passed in by the entry point: tasks never import the registry)."""

    reader: StoreReader
    writer: StoreWriter
    sources: Mapping[str, Source] = field(default_factory=dict)
    settings: SourcesSettings = field(default_factory=SourcesSettings)
    configs: ConfigStore | None = None
    clock: Callable[[], datetime] = utc_now
    user: str = SITE_USER
    unavailable: Mapping[str, str] = field(default_factory=dict)
    raw_sections: Mapping[str, str] = field(default_factory=dict)


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
        self._failed: list[str] = []
        self._resolvers: dict[date | None, SymbolResolver] = {}
        resumed = self._resume() if resume else None
        now = self.clock()
        self.record = resumed or start_run(task, session, now)
        self.reader = ctx.reader.including(self.record.run_id)  # sees its own pending writes

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
        record.items = {k: v for k, v in record.items.items() if status_label(v) not in RETRYABLE}
        record.status, record.finished_at = RunStatus.RUNNING, None
        return record

    def __enter__(self) -> Self:
        self.checkpoint()  # a RUNNING record: recovery knows the run's pending writes as ours
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
        """The status rule, in one place: explicit failed -> FAILED; failed items or explicit
        partial -> PARTIAL; else COMPLETE."""
        if self._failed:
            return RunStatus.FAILED
        return RunStatus.PARTIAL if self.failures() or self._partial else RunStatus.COMPLETE

    def _finish(self, status: RunStatus) -> None:
        self.record.status, self.record.finished_at = status, self.clock()
        if self._resolved:
            self.stats.setdefault("unresolved", self.unresolved)
        if self._partial:
            self.stats["partial"] = self._partial
        if self._failed:
            self.stats["failed_because"] = self._failed
        self.record.stats = self.stats
        try:
            self._publish_or_drop(status)
        finally:
            if self._save:
                self.writer.save_run(self.record)

    def _publish_or_drop(self, status: RunStatus) -> None:
        """Commit every table the run wrote at once (COMPLETE / PARTIAL), else drop them. A
        commit that fails marks the run FAILED; startup recovery settles what it left."""
        if status not in PUBLISHED:
            self.writer.abort_run(self.run_id)
            return
        try:
            self.writer.commit_run(self.run_id, self.record.finished_at or self.clock())
        except Exception as exc:
            self.record.status = RunStatus.FAILED
            self.stats["error"] = f"commit failed: {type(exc).__name__}: {exc}"
            raise
        if not self.retryable():
            self._drop_staging()

    def retryable(self) -> list[str]:
        """Items a resume would refetch (``RETRYABLE`` statuses), in item order."""
        return [k for k, v in self.items.items() if status_label(v) in RETRYABLE]

    def _drop_staging(self) -> None:
        """Nothing left to resume: the scratch is spent. Failing to delete it never fails a
        committed run; retention removes it later."""
        try:
            self.writer.staging.clear(self.run_id)
        except OSError as exc:
            self.stats["staging_kept"] = f"{type(exc).__name__}: {exc}"

    def checkpoint(self) -> None:
        """Save the record so far (resumable runs, long backfills)."""
        if self._save:
            self.writer.save_run(self.record)

    def partial(self, reason: str) -> None:
        """Mark the run PARTIAL for a reason that is not one item's failure."""
        self._partial.append(reason)

    def failed(self, reason: str) -> None:
        """Mark the whole run FAILED without raising (e.g. a workflow none of whose steps
        succeeded); the record is still saved on exit."""
        self._failed.append(reason)

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
        frame = self.stamped(frame, source, day)
        self.writer.write_table(table, day, self.run_id, frame, pending=True)

    def rewrite(self, table: str, day: date, frame: pd.DataFrame) -> None:
        """Re-publish a partition's rows as this run (new ``knowledge_ts`` and ``run_id``).

        ``frame`` must be the whole partition as read now: the run is written as restating,
        so for merge tables (events) the runs before it stop being read (``TableStore``)."""
        out = frame.assign(knowledge_ts=pd.Timestamp(self.clock()), run_id=self.run_id)
        self.writer.write_table(table, day, self.run_id, out, restates=True, pending=True)

    def stage(self, table: str, key: str, frame: pd.DataFrame, source: str) -> None:
        """Stamp one item's rows into run scratch; ``publish`` writes them as one partition."""
        self.writer.staging.put(self.run_id, table, key, self.stamped(frame, source))

    def publish(self, table: str, sort_by: str = "instrument_id") -> int:
        """Write a staged table as one partition (``knowledge_ts`` = publish time). The
        staging is dropped when the run finishes with nothing left to retry."""
        frame = self.writer.staging.collect(self.run_id, table)
        if frame is None:
            return 0
        frame = frame.sort_values(sort_by, kind="stable").reset_index(drop=True)
        frame["knowledge_ts"] = pd.Timestamp(self.clock())
        self.writer.write_table(table, self.session, self.run_id, frame, pending=True)
        return len(frame)


def recover_unpublished(writer: StoreWriter, now: datetime) -> dict[str, list[str]]:
    """Settle what crashed runs left, deterministically (ADR 0022). Call it only while
    holding the ingest run lock, so no ingest run is in flight:

    - a commit that reached its marker is completed (``recover_runs``); a run record a
      crash left RUNNING becomes PARTIAL, noted ``recovered``;
    - a run whose record is RUNNING or FAILED (an ingest run that crashed, or whose commit
      failed before its marker) has its pending writes dropped. Pending writes with no run
      record (a service's crashed run) are left to retention (``purge_pending_before``).
    """
    completed = writer.recover_runs()
    for run_id in completed:
        record = writer.load_run(run_id)
        if record is not None and record.status not in PUBLISHED:
            record.status, record.finished_at = RunStatus.PARTIAL, record.finished_at or now
            record.stats["recovered"] = "published by recovery after a crash during commit"
            writer.save_run(record)
    dropped = []
    for run_id in writer.pending_runs():
        record = writer.load_run(run_id)
        if record is not None and record.status in (RunStatus.RUNNING, RunStatus.FAILED):
            writer.abort_run(run_id)
            dropped.append(run_id)
    return {"completed": completed, "dropped": dropped}


def last_finished_session(writer: StoreWriter, task: str) -> date | None:
    """The latest session a run of ``task`` finished COMPLETE or PARTIAL for (FAILED and
    unfinished runs do not count)."""
    finished = (RunStatus.COMPLETE, RunStatus.PARTIAL)
    done = [r.session_date for r in writer.runs_for(task) if r.status in finished]
    return max(done) if done else None


def run_summary(record: RunRecord) -> Mapping[str, Any]:
    """What CLI commands print for a task run."""
    return {"run_id": record.run_id, "status": record.status, **record.stats}
