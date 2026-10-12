"""Retention and erasure of the personal text of the drafting feedback (ADR 0066, 2026-10-11).

Two owner-run commands (``algotrade-api feedback retain | erase``) over two tables:
``feedback/drafting_events`` (the trader's ``sentence`` and the ``payload``, which holds the
criteria snapshots) and the failure rows of ``usage/llm_calls`` (``sentence``, ``answer``,
``error``).

- **retain**: every row of a partition older than the window (by ``session_date``) loses that
  text, unless it was curated into the golden set (its ``event_id`` is a ``source_event`` of a
  golden case; a usage row is curated when a curated event lists its ``call_id``).
- **erase**: every row of one user loses the same text and the user id itself (the feedback
  ``user`` and ``doc_id`` become a placeholder, the usage ``user`` one random token per erase so
  per-user keys stay distinct); a curated row is erased too. The skeleton (``ts``, ``event``,
  hashes, call ids, token counts, cost) stays, so counts still add up.

**Mechanism.** A rewrite is a new run that *restates* each partition it touches with the merged
view, personal fields nulled, all partitions committed together (ADR 0022); reads see it at
once. A restating run does not delete the older run files, so each rewritten partition then goes
through ``TableStore.purge_superseded``, which removes the superseded runs and their files: the
old Parquet is physically gone. A crash between the commit and the purge leaves reads clean; the
next run purges (it purges every scanned partition). The command refuses while any run has
pending writes (the API's recorder holds one for milliseconds; a crashed one is dropped by the
store's retention) and while another retention command runs; it takes no lock the recorder
takes. Idempotent: a second run finds nothing to change. Dry run (the default) only reads.

**Backups.** Copies of the store taken before the command (``docs/hosting.md``) still hold the
text: erasing those is the owner's manual step, and the CLI prints the reminder.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import exchange_date
from algotrade.services.feedback.recorder import TABLE as FEEDBACK
from algotrade.services.text_model.usage import TABLE as USAGE
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import start_run
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import validate_frame

__all__ = ["open_backend"]  # the API opens the store through this module

JOB = "retention_feedback"  # sorts after the recorders' run ids (drafting_feedback, llm_usage)
LOCK = "feedback-retention"
RETAIN_DAYS = 365
PLACEHOLDER = "erased"
AUDIT_LOG = Path("var") / "logs" / "feedback-retention.log"
BACKUP_REMINDER = (
    "backups and snapshots of the store taken before this run still hold the text: erasing "
    "them is a manual step (docs/hosting.md)"
)
GOLDEN_CASES = Path("tests") / "fixtures" / "drafting" / "golden" / "cases"

Redact = Callable[[pd.DataFrame], tuple[pd.DataFrame, int]]  # -> (frame, rows changed)


@dataclass(frozen=True)
class Redaction:
    """What one command does to one table: the partitions it looks at and the row edit."""

    table: str
    wanted: Callable[[date], bool]
    redact: Redact


@dataclass(frozen=True)
class Change:
    table: str
    day: date
    rows: int


@dataclass
class Outcome:
    """What a run found (a dry run) or did; counts only, never content."""

    command: str
    applied: bool
    changes: list[Change] = field(default_factory=list)
    scanned: int = 0  # partitions read
    superseded_runs: int = 0  # old runs (files) deleted after the rewrite
    run_id: str | None = None

    def rows(self, table: str | None = None) -> int:
        return sum(c.rows for c in self.changes if table in (None, c.table))

    def lines(self) -> list[str]:
        verb = "rewrote" if self.applied else "would rewrite"
        out = [f"{c.table} {c.day.isoformat()}: {c.rows} row(s)" for c in self.changes]
        out.append(
            f"{self.command}: {verb} {self.rows()} row(s) in {len(self.changes)} partition(s) "
            f"of {self.scanned} scanned"
            + (f"; deleted {self.superseded_runs} superseded run(s); run {self.run_id}"
               if self.applied and self.changes else "")
        )  # fmt: skip
        if not self.applied:
            out.append("dry run: nothing was written; add --yes to apply")
        return out


def _text_cols(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    """Rows where any of ``columns`` still holds text."""
    return frame[list(columns)].notna().any(axis=1)


def _nulled(frame: pd.DataFrame, mask: pd.Series, columns: Iterable[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        out[column] = out[column].astype("object")
        out.loc[mask, column] = None
    return out


FEEDBACK_TEXT = ("sentence", "payload")
USAGE_TEXT = ("sentence", "answer", "error")


def retain_redactions(
    cutoff: date, curated_events: frozenset[str], curated_calls: frozenset[str]
) -> list[Redaction]:
    """Rows of partitions before ``cutoff`` lose their text but those curated."""

    def feedback(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        mask = ~frame["event_id"].isin(curated_events) & _text_cols(frame, FEEDBACK_TEXT)
        return _nulled(frame, mask, FEEDBACK_TEXT), int(mask.sum())

    def usage(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        mask = ~frame["call_id"].isin(curated_calls) & _text_cols(frame, USAGE_TEXT)
        return _nulled(frame, mask, USAGE_TEXT), int(mask.sum())

    def old(day: date) -> bool:
        return day < cutoff

    return [Redaction(FEEDBACK, old, feedback), Redaction(USAGE, old, usage)]


def erase_redactions(user: str, token: str) -> list[Redaction]:
    """Every row of ``user``, any date, loses its text and its id."""

    def everywhere(_: date) -> bool:
        return True

    def feedback(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        mask = frame["user"] == user
        out = _nulled(frame, mask, FEEDBACK_TEXT)
        out.loc[mask, ["user", "doc_id"]] = PLACEHOLDER
        return out, int(mask.sum())

    def usage(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        mask = frame["user"] == user
        out = _nulled(frame, mask, USAGE_TEXT)
        out.loc[mask, "user"] = token
        return out, int(mask.sum())

    return [Redaction(FEEDBACK, everywhere, feedback), Redaction(USAGE, everywhere, usage)]


def curated_events(golden_cases: Path) -> frozenset[str]:
    """The ``source_event`` ids the golden cases under ``golden_cases`` name (none: no folder)."""
    found: set[str] = set()
    for path in sorted(golden_cases.glob("*.json")) if golden_cases.is_dir() else []:
        case = json.loads(path.read_text())
        if isinstance(case, dict) and case.get("source_event"):
            found.add(str(case["source_event"]))
    return frozenset(found)


def curated_call_ids(backend: Backend, events: frozenset[str]) -> frozenset[str]:
    """The ``usage/llm_calls`` call ids that curated events list."""
    calls: set[str] = set()
    if not events:
        return frozenset()
    for day in backend.tables.dates(FEEDBACK):
        frame = backend.tables.read(FEEDBACK, day)
        if frame is None:
            continue
        listed = frame.loc[frame["event_id"].isin(events), "call_ids"].dropna()
        calls.update(c for text in listed for c in str(text).split(",") if c)
    return frozenset(calls)


def _plan(
    backend: Backend, redactions: list[Redaction], outcome: Outcome
) -> list[tuple[Redaction, date, pd.DataFrame]]:
    """The partitions that change, with their rewritten frames (reads only)."""
    todo = []
    for redaction in redactions:
        for day in backend.tables.dates(redaction.table):
            if not redaction.wanted(day):
                continue
            frame = backend.tables.read(redaction.table, day)
            outcome.scanned += 1
            if frame is None:
                continue
            rewritten, rows = redaction.redact(frame)
            if rows:
                outcome.changes.append(Change(redaction.table, day, rows))
                todo.append((redaction, day, rewritten))
    return todo


def _run(
    backend: Backend, command: str, redactions: list[Redaction], now: datetime, apply: bool
) -> Outcome:
    outcome = Outcome(command, apply)
    if not apply:
        _plan(backend, redactions, outcome)
        return outcome
    lock = backend.lock(LOCK)
    if not lock.acquire(wait=False):
        raise ConfigurationError("another feedback retain / erase is running")
    try:
        if backend.tables.pending_runs():
            raise ConfigurationError(
                "a run has pending writes (the API's recorder, or a crashed run the store drops "
                "after its retention): try again in a moment"
            )
        todo = _plan(backend, redactions, outcome)
        if todo:
            _rewrite(backend, todo, now, outcome)
        for redaction in redactions:  # also finishes what a crashed run left behind
            for day in backend.tables.dates(redaction.table):
                if redaction.wanted(day):
                    outcome.superseded_runs += backend.tables.purge_superseded(redaction.table, day)
        return outcome
    finally:
        lock.release()


def _rewrite(
    backend: Backend,
    todo: list[tuple[Redaction, date, pd.DataFrame]],
    now: datetime,
    outcome: Outcome,
) -> None:
    """One restating run for every changed partition, committed together; then checked."""
    run_id = start_run(JOB, exchange_date(now), now).run_id
    with ResultWriter(backend).publishing(run_id, now):  # commits together, drops if it raises
        for redaction, day, frame in todo:
            rows = frame.assign(run_id=run_id)
            validate_frame(redaction.table, rows)
            backend.tables.write(redaction.table, day, run_id, rows, restates=True, pending=True)
    outcome.run_id = run_id
    for redaction, day, _ in todo:  # what a read sees now holds nothing left to redact
        stored = backend.tables.read(redaction.table, day)
        if stored is None or redaction.redact(stored)[1]:
            raise RuntimeError(f"{redaction.table} {day}: personal text survived the rewrite")


def retain(
    backend: Backend,
    now: datetime,
    older_than_days: int = RETAIN_DAYS,
    golden_cases: Path = GOLDEN_CASES,
    apply: bool = False,
) -> Outcome:
    """Null the text of rows older than ``older_than_days`` (exchange dates) but the curated."""
    events = curated_events(golden_cases)
    redactions = retain_redactions(
        exchange_date(now) - timedelta(days=older_than_days), events,
        curated_call_ids(backend, events),
    )  # fmt: skip
    return _run(backend, "retain", redactions, now, apply)


def erase(
    backend: Backend,
    user: str,
    now: datetime,
    token: str | None = None,
    apply: bool = False,
) -> Outcome:
    """Remove ``user``'s text and id from both tables (the skeleton stays)."""
    if not user or user == PLACEHOLDER:
        raise ConfigurationError("name the user to erase")
    return _run(
        backend, "erase", erase_redactions(user, token or f"{PLACEHOLDER}-{token_hex(6)}"), now,
        apply,
    )  # fmt: skip


def audit_record(outcome: Outcome, now: datetime, params: Mapping[str, Any]) -> dict[str, Any]:
    """The audit line of a run: counts and parameters, never content (no sentence, no user id)."""
    return {
        "ts": now.astimezone(UTC).isoformat(),
        "command": outcome.command,
        "applied": outcome.applied,
        "params": dict(params),
        "run_id": outcome.run_id,
        "scanned": outcome.scanned,
        "partitions": len(outcome.changes),
        "rows": {t: outcome.rows(t) for t in (FEEDBACK, USAGE)},
        "superseded_runs": outcome.superseded_runs,
    }


def append_audit(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
