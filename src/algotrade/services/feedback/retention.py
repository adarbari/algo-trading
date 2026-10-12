"""Retention and erasure of the personal text of the stored feedback (ADR 0066, 2026-10-11).

Two owner-run commands (``algotrade-api feedback retain | erase``) over the tables of
``PERSONAL`` (the registry: each table's personal-text columns and user column; a test fails
when a ``feedback/*`` or ``usage/*`` table is added without an entry): today
``feedback/drafting_events`` (``sentence``, and the ``payload`` that holds the criteria
snapshots), the failure rows of ``usage/llm_calls`` (``sentence``, ``answer``, ``error``) and
``feedback/feature_requests`` (``span``; its ``ref`` key must never hold personal text).

- **retain**: every row of a partition older than the window (by ``session_date``) loses that
  text, unless it was curated into the golden set: its ``event_id`` is a ``source_events`` (or
  ``source_event``) id of a golden case, a usage row's ``call_id`` is listed by such an event.
  The golden cases are read from the repository root, never the working directory; no folder
  or a curated case without ids refuses the command (fail closed).
- **erase**: every row of one user, any date, a curated row too, loses the same text and the
  user id (the user column becomes one random token per erase, so per-user keys stay distinct;
  ``doc_id`` becomes a placeholder). What stays: ``ts``, ids, hashes, call ids, versions, counts,
  tokens, cost (so counts add up); these can be joined by time to logs that name the user, which
  is why ADR 0066 states exactly what an erase covers.

**Mechanism.** A rewrite is a new run, *not restating*, holding the merged view with the personal
fields nulled for every changed partition, all committed together (ADR 0022). Same keys, a run id
that sorts after the recorders' and the newest ``knowledge_ts``: it wins over every older run
and anything committed later merges beside it (a restating run would hide a later run with an
older ``ts``). The runs that existed when it was planned are then deleted with their files
(``TableStore.purge_runs``): the old Parquet is physically gone. A crash between the commit and
the purge leaves reads clean; the next run (and a dry run, which reports them) finds the runs
committed before the last retention run and purges them. Only runs seen at plan time are
deleted, so a commit that lands meanwhile is never lost.

**Concurrency.** The command holds ``feedback-writers`` (``storage.locks``) from plan to purge;
the API's recorders take it for every flush, so none commits in between (their queue absorbs
the wait; a request never waits). It refuses while another retention command runs or any run has
pending writes. Idempotent; a dry run (the default) only reads.

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
from algotrade.storage.locks import FEEDBACK_WRITERS, held
from algotrade.storage.runs import start_run
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import validate_frame

__all__ = ["open_backend"]  # the API opens the store through this module

JOB = "retention_feedback"  # sorts after the recorders' run ids (drafting_feedback, llm_usage)
LOCK = "feedback-retention"
RETAIN_DAYS = 365
PLACEHOLDER = "erased"
REPO_ROOT = Path(__file__).resolve().parents[4]  # never the working directory
AUDIT_LOG = REPO_ROOT / "var" / "logs" / "feedback-retention.log"
GOLDEN_CASES = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden" / "cases"
BACKUP_REMINDER = (
    "backups and snapshots of the store taken before this run still hold the text: erasing "
    "them is a manual step (docs/hosting.md)"
)
# named by prefix until the table's owner exports a constant (feedback/feature_requests)
FEATURE_REQUESTS = "feedback/" + "feature_requests"


@dataclass(frozen=True)
class PersonalTable:
    """A stored table that holds personal text: what retain nulls and erase removes."""

    table: str
    text: tuple[str, ...]  # nulled by both commands
    user: str = "user"  # the user column (erase matches it, then writes a token)
    blanked: tuple[str, ...] = ()  # non-null columns erase replaces by PLACEHOLDER
    safe: tuple[str, ...] = ()  # the other string columns: ids, hashes, versions, enums
    curated_by: str | None = None  # the column retain compares with the curated ids ...
    curated_kind: str = "events"  # ... "events" (event ids) or "calls" (call ids)


PERSONAL = (
    PersonalTable(
        FEEDBACK, ("sentence", "payload"), blanked=("doc_id",), curated_by="event_id",
        safe=("event_id", "draft_session_id", "doc_kind", "event", "call_ids",
              "catalogue_version", "prompt_version", "draft_hash", "saved_hash"),
    ),
    PersonalTable(
        USAGE, ("sentence", "answer", "error"), curated_by="call_id", curated_kind="calls",
        safe=("provider", "model", "use_case", "cost_basis", "outcome", "fell_back_from",
              "stage", "call_id", "prompt_version", "call_stage"),
    ),
    PersonalTable(FEATURE_REQUESTS, ("span",), safe=("ref",)),  # `ref` is a key: never text
)  # fmt: skip

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
    to_purge: int = 0  # old runs still on disk (a dry run: what --yes would delete)
    run_id: str | None = None

    def rows(self, table: str | None = None) -> int:
        return sum(c.rows for c in self.changes if table in (None, c.table))

    def lines(self) -> list[str]:
        verb = "rewrote" if self.applied else "would rewrite"
        out = [f"{c.table} {c.day.isoformat()}: {c.rows} row(s)" for c in self.changes]
        out.append(
            f"{self.command}: {verb} {self.rows()} row(s) in {len(self.changes)} partition(s) "
            f"of {self.scanned} scanned"
            + (f"; run {self.run_id}" if self.run_id else "")
            + (f"; deleted {self.superseded_runs} old run(s)" if self.applied else "")
            + (f"; {self.to_purge} old run(s) still on disk" if not self.applied else "")
        )  # fmt: skip
        if not self.applied:
            out.append("dry run: nothing was written; add --yes to apply")
        return out


def _holds_text(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    """Rows where any of ``columns`` still holds text."""
    have = [c for c in columns if c in frame.columns]
    return frame[have].notna().any(axis=1) if have else pd.Series(False, index=frame.index)


def _nulled(frame: pd.DataFrame, mask: pd.Series, columns: Iterable[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in (c for c in columns if c in out.columns):
        out[column] = out[column].astype("object")
        out.loc[mask, column] = None
    return out


def retain_redactions(
    cutoff: date, curated: Mapping[str, frozenset[str]], tables: Iterable[PersonalTable] = PERSONAL
) -> list[Redaction]:
    """Rows of partitions before ``cutoff`` lose their text but those curated (``curated``:
    ids by kind, ``events`` / ``calls``)."""

    def build(t: PersonalTable) -> Redaction:
        spared = curated.get(t.curated_kind, frozenset())

        def redact(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
            mask = _holds_text(frame, t.text)
            if t.curated_by and t.curated_by in frame.columns:
                mask &= ~frame[t.curated_by].isin(spared)
            return _nulled(frame, mask, t.text), int(mask.sum())

        return Redaction(t.table, lambda day: day < cutoff, redact)

    return [build(t) for t in tables]


def erase_redactions(
    user: str, token: str, tables: Iterable[PersonalTable] = PERSONAL
) -> list[Redaction]:
    """Every row of ``user``, any date, loses its text and its id."""

    def build(t: PersonalTable) -> Redaction:
        def redact(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
            if t.user not in frame.columns:
                return frame, 0
            mask = frame[t.user] == user
            out = _nulled(frame, mask, t.text)
            out.loc[mask, t.user] = token
            for column in (c for c in t.blanked if c in out.columns):
                out.loc[mask, column] = PLACEHOLDER
            return out, int(mask.sum())

        return Redaction(t.table, lambda _day: True, redact)

    return [build(t) for t in tables]


def curated_events(golden_cases: Path) -> frozenset[str]:
    """The event ids the golden cases under ``golden_cases`` name: the union of ``source_events``
    (every event of a curated chain) and ``source_event``. Refuses (fail closed, nothing is
    nulled) a folder that is missing, a file that is not a JSON object and a curated case (one
    with a ``chain_id``) that names no event; a hand-written case names none and is skipped."""
    if not golden_cases.is_dir():
        raise ConfigurationError(f"the golden cases folder is missing: {golden_cases}")
    found: set[str] = set()
    for path in sorted(golden_cases.glob("*.json")):
        try:
            case = json.loads(path.read_text())
        except ValueError as exc:
            raise ConfigurationError(f"{path.name} is not JSON: {exc}") from exc
        if not isinstance(case, dict):
            raise ConfigurationError(f"{path.name} is not a JSON object")
        named = case.get("source_events") or []
        ids = {str(e) for e in ([named] if isinstance(named, str) else named)}
        if case.get("source_event"):
            ids.add(str(case["source_event"]))
        if case.get("chain_id") and not ids:
            raise ConfigurationError(f"{path.name} is a curated case with no source events")
        found |= ids
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


@dataclass
class _Part:
    redaction: Redaction
    day: date
    runs: list[str]  # the committed runs now, oldest commit first
    frame: pd.DataFrame | None  # the rewritten view; None: nothing to change

    def stale(self) -> list[str]:
        """Runs a retention run already superseded and a crash left on disk: those committed
        before the last retention run (by commit order, never by ``ts``)."""
        last = max((i for i, r in enumerate(self.runs) if r.startswith(JOB)), default=-1)
        return self.runs[:last]

    def doomed(self) -> list[str]:
        """What to delete once the rewrite committed: every run seen at plan time."""
        return self.runs if self.frame is not None else self.stale()


def _plan(backend: Backend, redactions: list[Redaction], outcome: Outcome) -> list[_Part]:
    """Every wanted partition, with its rewritten frame when it changes (reads only)."""
    parts = []
    for redaction in redactions:
        for day in backend.tables.dates(redaction.table):
            if not redaction.wanted(day):
                continue
            runs = backend.tables.partition_runs(redaction.table, day)
            frame = backend.tables.read(redaction.table, day)
            outcome.scanned += 1
            rewritten = None
            if frame is not None:
                changed, rows = redaction.redact(frame)
                if rows:
                    outcome.changes.append(Change(redaction.table, day, rows))
                    rewritten = changed
            part = _Part(redaction, day, runs, rewritten)
            outcome.to_purge += len(part.stale())
            parts.append(part)
    return parts


def _run(
    backend: Backend, command: str, redactions: list[Redaction], now: datetime, apply: bool
) -> Outcome:
    outcome = Outcome(command, apply)
    if not apply:
        _plan(backend, redactions, outcome)
        return outcome
    with held(backend.lock(LOCK), wait=False) as alone:
        if not alone:
            raise ConfigurationError("another feedback retain / erase is running")
        with held(backend.lock(FEEDBACK_WRITERS)):  # no recorder commits from plan to purge
            if backend.tables.pending_runs():
                raise ConfigurationError(
                    "a run has pending writes (a crashed run the store drops after its "
                    "retention): try again in a moment"
                )
            parts = _plan(backend, redactions, outcome)
            outcome.to_purge = 0
            changed = [p for p in parts if p.frame is not None]
            if changed:
                outcome.run_id = _rewrite(backend, changed, now)
            for part in parts:  # also finishes what a crashed run left behind
                outcome.superseded_runs += backend.tables.purge_runs(
                    part.redaction.table, part.day, part.doomed()
                )
            _verify(backend, parts, outcome.run_id)
    return outcome


def _rewrite(backend: Backend, changed: list[_Part], now: datetime) -> str:
    """One run for every changed partition, committed together; -> its id."""
    taken = {r for part in changed for r in part.runs}
    run_id = start_run(JOB, exchange_date(now), now).run_id
    while run_id in taken:  # ids have one-second resolution: never replace a run still planned
        now += timedelta(seconds=1)
        run_id = start_run(JOB, exchange_date(now), now).run_id
    with ResultWriter(backend).publishing(run_id, now):  # commits together, drops if it raises
        for part in changed:
            assert part.frame is not None
            table = part.redaction.table
            rows = part.frame.assign(run_id=run_id)
            validate_frame(table, rows)
            backend.tables.write(table, part.day, run_id, rows, pending=True)
    return run_id


def _verify(backend: Backend, parts: list[_Part], run_id: str | None) -> None:
    """After the purge: a read holds nothing left to redact and no planned run remains on disk.
    Raises (a non-zero exit) otherwise: never a reported success with text on disk."""
    for part in parts:
        table = part.redaction.table
        left = set(backend.tables.partition_runs(table, part.day)) & set(part.doomed())
        if left - {run_id}:
            raise RuntimeError(f"{table} {part.day}: {len(left)} old run(s) are still on disk")
        if part.frame is not None:
            stored = backend.tables.read(table, part.day)
            if stored is None or part.redaction.redact(stored)[1]:
                raise RuntimeError(f"{table} {part.day}: personal text survived the rewrite")


def retain(
    backend: Backend,
    now: datetime,
    older_than_days: int = RETAIN_DAYS,
    golden_cases: Path = GOLDEN_CASES,
    apply: bool = False,
) -> Outcome:
    """Null the text of rows older than ``older_than_days`` (exchange dates) but the curated."""
    events = curated_events(golden_cases)
    curated = {"events": events, "calls": curated_call_ids(backend, events)}
    cutoff = exchange_date(now) - timedelta(days=older_than_days)
    return _run(backend, "retain", retain_redactions(cutoff, curated), now, apply)


def erase(
    backend: Backend,
    user: str,
    now: datetime,
    token: str | None = None,
    apply: bool = False,
) -> Outcome:
    """Remove ``user``'s text and id from every personal table (the skeleton stays)."""
    if not user or user == PLACEHOLDER:
        raise ConfigurationError("name the user to erase")
    redactions = erase_redactions(user, token or f"{PLACEHOLDER}-{token_hex(6)}")
    return _run(backend, "erase", redactions, now, apply)


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
        "rows": {t.table: outcome.rows(t.table) for t in PERSONAL},
        "superseded_runs": outcome.superseded_runs,
    }


def append_audit(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
