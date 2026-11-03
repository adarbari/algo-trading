"""The ``option-history-outcomes`` task (ADR 0088 decision 11, E5): the option trades of the windows
the bought history closes, written to ``outcomes/option/structure_pnl@v2`` with ``price_source =
option_history`` and the licence ``personal``. It computes frames the way ``option-outcomes`` does
(the same positions, the same engine, the same ``trade_rows``; only ``HistoryChainLoader`` differs)
and publishes them through that writer's one publisher, ``frame_and_publish``: there is no second
writer of the table.

``algotrade-ingest run option-history-outcomes --from D --to D [--batch N] [--symbols S,T]
[--force]``.

- **Range.** A window's entry session S must be a stored history session strictly before
  ``FIRST_CBOE_CHAIN_SESSION``: from the cutover the table's rows are Cboe's (its key does not hold
  the price source, a history row would replace one), so such a window is not computed. Until PR
  #968's listing history is in, only the index underlyings and ``--symbols`` names (default
  ``SPY,QQQ,IWM``) are chains (``HistoryChainLoader``).
- **Start.** The main store must hold bars, ``forward_returns@v2``, the Treasury curve and the
  dividends from the range start (a missing session of bars or the curve fails the run: carry or a
  stop would be silently zero), and each position's exit-rule fields must have partitions in the
  range; a position that does not is refused, recorded and FAILs the run, never run as "never
  fires". The history mount is checked before every batch (``HistoryUnavailableError``).
- **Batches** of ``--batch`` window ends (default 20): the nightly window is waited out; the batch
  is computed with no IngestRun open under the ``ingest-tree`` lock (a deploy cannot rewrite the
  code mid-batch); then, still outside the nightly window, the ingest lock is taken (``wait=False``
  and retried), ``recover_unpublished`` runs, ONE IngestRun writes the batch through
  ``frame_and_publish`` and commits, and both locks are released before the next batch. No batch
  holds the ingest lock across two publishes. The window is the exchange close of the session day
  plus ``settle_minutes`` to ``data_deadline`` (``nightly.toml``, owner zone).
- **Resume.** A window end already written (same positions, same history run of its session) is
  skipped unless ``--force``; each batch's run records, per end, the history runs it read
  (``history_runs``, ADR 0084 decision 3).
- The summary record (``option-history-outcomes-summary``, no pending writes) is saved after the
  last batch: batches, rows, refusals and the measured seconds beside the estimate."""

import hashlib
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.site.nightly import NightlySettings
from algotrade.config.site.settings import load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import (
    OWNER_ZONE,
    close_time,
    is_session,
    local_deadline,
    sessions_between,
    sessions_ending,
)
from algotrade.data import StoreReader
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.data.option_history import reading
from algotrade.data.option_history.store import open_history
from algotrade.data.rates import TABLE as RATES
from algotrade.features.site import site_features
from algotrade.services.jobs.exclusive import INGEST_LOCK, INGEST_TREE_LOCK, RunLockedError
from algotrade.storage.locks import held
from algotrade.storage.runs import RunRecord, RunStatus, published, start_run
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade_ingestion.tasks.derived.paths.close_fields import (
    FieldLoader,
    refuse_unstored,
    rule_licence,
)
from algotrade_ingestion.tasks.derived.paths.option_outcomes import (
    EXPECTED_DATE,
    SITE,
    frame_and_publish,
    refusal,
    trade_rows,
)
from algotrade_ingestion.tasks.derived.paths.wanted import Wanted, positions_wanted
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, recover_unpublished
from algotrade_ingestion.tasks.options_history.chains import HistoryChainLoader

TASK = "option-history-outcomes"  # one run per batch (the resume reads these)
SUMMARY_TASK = "option-history-outcomes-summary"
PRICE_SOURCE = "option_history"
LICENCE = "personal"
BARS = "bars/1d"
DIVIDENDS = "events/dividend"
SYMBOLS = ("SPY", "QQQ", "IWM")  # the index ETFs the first setups name (X1)
SHOWN = 5
RETRY_SECONDS = 60.0
LOCK_ATTEMPTS = 24 * 60  # a day of one-minute retries


@dataclass(frozen=True)
class HistoryOutcomeOptions:
    url: str | None = None  # the history store (default: ALGOTRADE_OPTION_HISTORY_URL)
    start: date | None = None
    end: date | None = None
    batch: int = 20
    symbols: tuple[str, ...] = SYMBOLS
    force: bool = False


@dataclass
class Pacing:
    """The clock and the sleep the batches wait with (tests pass a fake pair)."""

    sleep: Callable[[float], None] = time.sleep
    retry_seconds: float = RETRY_SECONDS
    attempts: int = LOCK_ATTEMPTS
    slept: float = 0.0  # seconds spent waiting (the nightly window, a held lock), never computing

    def wait(self, seconds: float) -> None:
        self.slept += seconds
        self.sleep(seconds)


def nightly_window(now: datetime, nightly: NightlySettings) -> datetime | None:
    """When the nightly window that ``now`` is inside ends (UTC), else ``None``: on an exchange
    session day (owner zone) from its close plus ``settle_minutes`` to ``data_deadline``."""
    day = now.astimezone(ZoneInfo(OWNER_ZONE)).date()
    if not is_session(day):
        return None
    opens = close_time(day) + timedelta(minutes=nightly.settle_minutes)
    closes = local_deadline(day, nightly.data_deadline)
    return closes if opens <= now < closes else None


def wait_out_nightly(ctx: TaskContext, nightly: NightlySettings, pacing: Pacing) -> int:
    """Sleep until the nightly window is over -> the number of sleeps (0: not in it)."""
    sleeps = 0
    while (until := nightly_window(ctx.clock(), nightly)) is not None:
        pacing.wait(max(1.0, (until - ctx.clock()).total_seconds()))
        sleeps += 1
    return sleeps


@contextmanager
def locked(backend: Backend, name: str, pacing: Pacing) -> Iterator[None]:
    """Hold the store's lock ``name`` for the block, trying without waiting and retrying after a
    sleep (``RunLockedError`` when it never frees)."""
    for _ in range(pacing.attempts):
        with held(backend.lock(name), wait=False) as taken:
            if taken:
                yield
                return
        pacing.wait(pacing.retry_seconds)
    raise RunLockedError(f"the {name} lock stayed taken for {pacing.attempts} attempts")


def coverage_problems(reader: StoreReader, first: date, last: date) -> list[str]:
    """What the main store lacks for a history run over ``first..last`` (S of the first window to
    the last close): the tables must start by ``first``, bars and the curve hold every session."""
    problems = []
    needed = set(sessions_between(first, last))
    for table in (BARS, FORWARD_RETURNS, RATES, DIVIDENDS):
        stored = reader.dates(table)
        if not stored or min(stored) > first:
            found = min(stored).isoformat() if stored else "nothing"
            problems.append(f"{table}: holds {found}, needs {first}")
        elif table in (BARS, RATES) and (gap := sorted(needed - set(stored))):
            problems.append(f"{table}: {len(gap)} sessions missing, first {gap[0]}")
    return problems


def start_refusals(
    reader: StoreReader, wanted: Sequence[Wanted], closes: Sequence[date]
) -> dict[str, str]:
    """Position key -> why it is not written over ``closes``: an exit rule over a field the range
    cannot read (``close_fields``), or ``skip_report_in_life`` over no expected-report date."""
    out = {}
    for w in wanted:
        spec = w.outcome.position
        problems = refuse_unstored(reader, w.fields, closes)
        if spec is not None and spec.skip_report_in_life:  # the date read at each entry (X3)
            problems += refuse_unstored(reader, [EXPECTED_DATE], closes)
        if problems:
            out[w.key] = "; ".join(problems[:SHOWN])
    return out


def wanted_hash(wanted: Sequence[Wanted]) -> str:
    return hashlib.sha1("|".join(sorted(w.key for w in wanted)).encode()).hexdigest()[:12]


def identity(history: StoreReader, wanted: str, end: date, depth: int) -> str:
    """What a written window end is: the positions and the history import of every session its
    longest window reads (a re-imported session makes it a different end)."""
    runs = [reading.session_run(history, d) for d in sessions_ending(end, depth)]
    return f"{wanted}:{hashlib.sha1(repr(runs).encode()).hexdigest()[:12]}"


def written_ends(ctx: TaskContext) -> dict[str, set[str]]:
    """End (ISO) -> the identities of the published batch runs that wrote it."""
    found: dict[str, set[str]] = {}
    for record in ctx.writer.runs_for(TASK):
        if published(record):
            for end, ident in record.stats.get("identities", {}).items():
                found.setdefault(end, set()).add(ident)
    return found


def history_ends(
    history: StoreReader, start: date, end: date, holds: Sequence[int]
) -> tuple[list[date], date]:
    """The window ends to compute (sessions of ``start..end``) -> (them, the first entry session):
    entry sessions before the Cboe cutover only are written (see the module docstring)."""
    stored = set(reading.sessions(history))
    ends = [
        t
        for t in sessions_between(start, end)
        if any(
            (days := sessions_ending(t, h + 1))[0] < FIRST_CBOE_CHAIN_SESSION
            and set(days) <= stored
            for h in holds
        )
    ]
    if not ends:
        raise ConfigurationError(
            f"no window of {start}..{end} has an entry session in the history before "
            f"{FIRST_CBOE_CHAIN_SESSION}"
        )
    return ends, sessions_ending(ends[0], max(holds) + 1)[0]


def compute_batch(
    ctx: TaskContext,
    history: StoreReader,
    ends: Sequence[date],
    wanted: Sequence[Wanted],
    options: HistoryOutcomeOptions,
    features: Any,
) -> tuple[dict[date, list[pd.DataFrame]], dict[str, str], dict[str, str]]:
    """The frames of ``ends`` by start session, no run open -> (frames, item statuses by
    ``<T>:<key>``, the history runs read by session)."""
    stored = set(reading.sessions(history))
    loader = HistoryChainLoader(history, ctx.settings, options.symbols)
    fields = FieldLoader(ctx.reader)
    parts: dict[date, list[pd.DataFrame]] = {}
    items: dict[str, str] = {}
    for t in ends:
        for w in wanted:
            sessions = sessions_ending(t, w.hold + 1)
            item = f"{t}:{w.key}"
            if sessions[0] >= FIRST_CBOE_CHAIN_SESSION:
                items[item] = "AFTER_CUTOVER"
                continue
            if not set(sessions) <= stored:  # a close the history lacks is no chain, not a miss
                items[item] = "NO_HISTORY"
                continue
            if why := refusal(
                ctx.reader, w, sessions
            ):  # fail closed per window, never "never fires"
                items[item] = f"REFUSED: {why}"
                continue
            loader.reset()
            licence = rule_licence(features, w.fields, price=LICENCE)
            rows, ok = trade_rows(w, sessions, loader, fields, licence, PRICE_SOURCE)
            if len(rows):
                parts.setdefault(sessions[0], []).append(rows)
            items[item] = f"OK: {len(rows)} rows from {ok} chains"
    read = {
        d.isoformat(): run
        for d in sorted(loader._days)
        if (run := reading.session_run(history, d)) is not None
    }
    return parts, items, read


def publish_batch(
    ctx: TaskContext,
    backend: Backend,
    parts: dict[date, list[pd.DataFrame]],
    ends: Sequence[date],
    stats: dict[str, Any],
    items: dict[str, str],
    nightly: NightlySettings,
) -> RunRecord | None:
    """One batch's IngestRun, written and committed entirely under the ingest lock, taken with one
    non-blocking try: ``None`` when it is busy or the nightly window has opened (the caller frees
    its locks, waits and tries again). Under the lock a crash's leftovers are recovered first."""
    with held(backend.lock(INGEST_LOCK), wait=False) as taken:
        if not taken or nightly_window(ctx.clock(), nightly) is not None:
            return None
        recover_unpublished(ctx.writer, ctx.clock())
        with IngestRun(ctx, TASK, ends[-1]) as run:
            run.stats.update(stats)
            run.items.update(items)
            frame_and_publish(run, parts)
    return run.record


def _run_batch(
    ctx: TaskContext,
    backend: Backend,
    history: StoreReader,
    chunk: list[date],
    wanted: list[Wanted],
    options: HistoryOutcomeOptions,
    features: Any,
    run: tuple[NightlySettings, Pacing, str, int, dict[str, Any]],
) -> None:
    """One batch: compute under ``ingest-tree`` with no run open, then publish under one hold of
    the ingest lock outside the nightly window; ``totals`` collects the counts and seconds."""
    nightly, pacing, sha, depth, totals = run
    totals["waited_for_nightly"] += wait_out_nightly(ctx, nightly, pacing)
    began = time.monotonic()
    with locked(backend, INGEST_TREE_LOCK, pacing):
        parts, items, read = compute_batch(ctx, history, chunk, wanted, options, features)
    totals["compute_seconds"] += time.monotonic() - began
    refused_ends = {k.split(":")[0] for k, v in items.items() if v.startswith("REFUSED")}
    totals["refused_windows"] += sum(v.startswith("REFUSED") for v in items.values())
    batch_stats = {
        "ends": [t.isoformat() for t in chunk],
        "identities": {  # an end with a refused window is not written: it is retried
            t.isoformat(): identity(history, sha, t, depth)
            for t in chunk
            if t.isoformat() not in refused_ends
        },
        "history_runs": read,
        "rows": sum(len(f) for fs in parts.values() for f in fs),
    }
    for _ in range(pacing.attempts):  # outside the nightly window, ingest lock free
        totals["waited_for_nightly"] += wait_out_nightly(ctx, nightly, pacing)
        with locked(backend, INGEST_TREE_LOCK, pacing):
            began = time.monotonic()
            done = publish_batch(ctx, backend, parts, chunk, batch_stats, items, nightly)
            if done is not None:
                totals["publish_seconds"] += time.monotonic() - began
                break
        pacing.wait(pacing.retry_seconds)  # both locks are free while it waits
    else:
        raise RunLockedError(f"the ingest lock stayed busy for {pacing.attempts} tries")
    totals["batches"] += 1
    totals["rows"] += batch_stats["rows"]


def compute_history_outcomes(
    ctx: TaskContext,
    today: date,
    options: HistoryOutcomeOptions,
    open_store: Callable[[str | None], Backend] = open_history,
    pacing: Pacing | None = None,
) -> RunRecord:
    """The batches over ``options.start..end`` -> the summary record (FAILED on a coverage
    problem, a refused position or a batch that raised; batches written before it stay)."""
    pacing = pacing or Pacing()
    if options.start is None or options.end is None:
        raise ConfigurationError("option-history-outcomes needs --from and --to")
    configs = ctx.configs or SITE
    nightly = load_nightly(configs)
    summary = start_run(SUMMARY_TASK, today, ctx.clock())
    stats: dict[str, Any] = summary.stats
    history = StoreReader(open_store(options.url))
    wanted = positions_wanted(load_edges(configs), load_templates(configs))
    ends, first = history_ends(history, options.start, options.end, [w.hold for w in wanted])
    problems = coverage_problems(ctx.reader, first, ends[-1])
    closes = sessions_between(first, ends[-1])
    refused = start_refusals(ctx.reader, wanted, closes)
    wanted = [w for w in wanted if w.key not in refused]
    stats.update(coverage=problems, refused=refused, positions=len(wanted), window_ends=len(ends))
    if problems or not wanted:
        return _finish(ctx, summary, failed=True)
    features = site_features(configs) if any(w.fields for w in wanted) else None
    sha = wanted_hash(wanted)
    depth = max(w.hold for w in wanted) + 1
    already = written_ends(ctx)
    todo = [
        t
        for t in ends
        if options.force or identity(history, sha, t, depth) not in already.get(t.isoformat(), ())
    ]
    stats["skipped"] = len(ends) - len(todo)
    backend = ctx.writer.backend
    totals: dict[str, Any] = {
        "batches": 0, "rows": 0, "refused_windows": 0, "compute_seconds": 0.0,
        "publish_seconds": 0.0, "waited_for_nightly": 0,
    }  # fmt: skip
    try:
        for i in range(0, len(todo), options.batch):
            open_store(options.url)  # the drive is still mounted and marked (HistoryUnavailable)
            _run_batch(
                ctx, backend, history, todo[i : i + options.batch], wanted, options, features,
                (nightly, pacing, sha, depth, totals),
            )  # fmt: skip
    except Exception as exc:  # a batch that raised stops the run; earlier batches are committed
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats.update(totals)
        return _finish(ctx, summary, failed=True)
    totals.update(slept_seconds=round(pacing.slept, 1))
    for key in ("compute_seconds", "publish_seconds"):
        totals[key] = round(totals[key], 2)
    stats.update(totals)
    return _finish(ctx, summary, failed=bool(refused) or bool(totals["refused_windows"]))


def _finish(ctx: TaskContext, record: RunRecord, failed: bool) -> RunRecord:
    """Close the summary (it holds no pending write; recovery ignores it) and save it."""
    record.status = RunStatus.FAILED if failed else RunStatus.COMPLETE
    record.finished_at = ctx.clock().astimezone(UTC)
    ctx.writer.save_run(record)
    return record
