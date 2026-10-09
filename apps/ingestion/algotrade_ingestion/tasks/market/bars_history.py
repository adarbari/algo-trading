"""Unadjusted daily bars from Tiingo back to 2018 for the event-study names (ADR 0050).

``algotrade-ingest run bars-history`` fetches ONE request per name of the event-study scope
(``services.events.scope.scoped_instruments``): by default the site list
``config/site/events/scope.toml``, the stocks the scoped leveraged funds track and ``--symbols``;
with ``--include-tiers`` also the tier A / B short-put names. Tiingo's free tier allows 500
unique symbols a month and 50 requests an hour, so the tier names (hundreds) need its Power tier.
The task stores the rows in ``bars/1d`` with ``source = "tiingo"``, one partition per session,
for ``--since`` (default 2018-01-01) to ``--until`` (default: the last session). Prices are
stored unadjusted, as Massive's are (ADR 0016). The source paces one request every 72 s, so ~140
names take ~3 hours: run it detached (README "Long runs"); ``stats["pending"]`` and ``eta_h``
say how many are left.

- **Monthly fill** (``--fill N``): instead of only the scope list, picks up to N names of the
  whole universe that no earlier run fetched for the window, most useful first
  (``services.events.fill.fill_order``: optionable, then ``iv30``, then dollar volume, as of
  ``--until``'s session); the references of leveraged / inverse funds among them come along as
  before. A launchd agent runs it monthly (``ops/schedule.py``) until the optionable universe is
  covered.
- **Monthly budget**: Tiingo's free tier allows 500 distinct symbols a calendar month, so a run
  fetches at most ``[tiingo] monthly_symbol_budget`` minus the distinct names (every ``hist:``
  item, ``FETCH_ERROR`` too) that the runs of the task in ANY status (a crashed run spent its
  requests) had in this UTC month (a run counts in every month from its start to its finish)
  and that this run already asked for. ``stats`` carry ``month_budget``, ``month_used`` and
  ``month_remaining`` (all after the run) and ``filled`` (the ``--fill`` picks fetched this run).
  A new month resets it.
- **From the listings** (``--from-listings``): instead of the scope list, the names are the
  listings of the universe on any session of ``since..until`` (``data.listings.listings_over``,
  ADR 0018 amendment, edges ED6; not with ``--fill``; ``--symbols`` narrows them by ticker). A
  listing is fetched by its ``permaTicker`` when it has one, else by its ticker; a listing whose
  ticker another listing also used and that has no ``permaTicker`` is NEVER fetched (the
  ticker's bars would be the other company's): item ``perma:<id>`` (``NO_PERMA``), counted in
  ``stats["no_perma"]``. The request asks only for the listing's own dates and every row is
  clipped to ``start_date..end_date`` (``stats["clipped_rows"]``).
- **Scope** is resolved once, by the owner, as of ``--until``'s session (ADR 0018): ids come
  from that session's reference snapshot. A symbol it does not know is NEVER fetched under a
  made-up id: it is an item ``sym:<SYMBOL>`` (``UNKNOWN``) and listed in
  ``stats["unknown_symbols"]``; ``stats["by_reason"]`` counts the names per reason (list, requested,
  reference, and tier with ``--include-tiers``).
- **Resumable**, like ``ibkr-iv``: a name an earlier finished run fetched for the whole window
  (item ``hist:<id>``, ``OK: <since>..<until>`` or ``NO_DATA: ...``) is skipped (``--force``
  fetches it again); an interrupted run resumes from its staging when started again with the
  same ``--until``. Rows are staged per name and published together when the run ends (ADR
  0022). Names Tiingo did not answer for are ``FETCH_ERROR`` (a later run asks again);
  ``STOP_AFTER_FAILED`` of them in a row (a bad key, the monthly cap) end the run.
- **Never overwrites Massive** (``bars/1d`` is a snapshot table: a new run's partition replaces
  the old one, so the partition is rewritten whole): a row for an (instrument, session) the
  session's partition already holds is skipped and counted (``overlap_rows``, or
  ``already_stored_rows`` when it is Tiingo's own). A session with NO partition is created only
  before the earliest stored one (the history); at or after it, a missing session is a gap the
  nightly ``bars`` task must fill from Massive (it skips stored dates), so Tiingo rows for it are
  counted (``no_partition_rows``) and not written.
- **Split check**: the days Tiingo's ``splitFactor`` is not 1 are compared with ``events/split``
  (``ratio`` = to / from) over the span of the fetched bars; each difference (a split on one
  side only, or another ratio) is an item ``split:<id>`` (``SPLIT_MISMATCH: <n> ...``) and
  counts in ``stats["split_mismatches"]``. Reported, never a failure and never a reason not
  to write: the bars are what the vendor sent.
"""

import math
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from itertools import islice
from typing import cast

import pandas as pd

from algotrade.data.events import read_events
from algotrade.data.listings.universe import listings_over
from algotrade.services.events.fill import FillCandidate, fill_order
from algotrade.services.events.scope import (
    LIST,
    REFERENCE,
    REQUESTED,
    TIER,
    ScopedInstruments,
    scoped_instruments,
)
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.framework.tiingo_budget import month_symbols
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "bars_history"
BARS = "bars/1d"
SPLITS = "events/split"
DEFAULT_SINCE = date(2018, 1, 1)
DEFAULT_REASONS = (LIST, REQUESTED, REFERENCE)  # the tier names need Tiingo's Power tier
DONE = ("OK", "NO_DATA")  # item statuses that need no refetch
UNKNOWN = "UNKNOWN"
SPLIT_MISMATCH = "SPLIT_MISMATCH"
CHECKPOINT_EVERY = 5
STOP_AFTER_FAILED = 3  # names Tiingo did not answer in a row (key, caps, outage): stop the run
RATIO_TOLERANCE = 1e-3
DETAIL_LIMIT = 20  # split mismatches listed in the run stats (every one is an item)
HOURLY_FREE_PACE_S = 72.0


@dataclass(frozen=True)
class Name:
    """A name to fetch. ``perma`` / ``start`` / ``end`` come from a listing (``--from-listings``):
    the vendor key is then the ``permaTicker`` and the rows are clipped to the listing's dates."""

    symbol: str
    instrument_id: str
    perma: str = ""
    start: date | None = None
    end: date | None = None

    @property
    def vendor_key(self) -> str:
        return self.perma or self.symbol


def names_of(scope: ScopedInstruments) -> list[Name]:
    """The scoped names that have a ticker in the reference snapshot (one is fetched by it)."""
    return [Name(n.symbol, n.instrument_id) for n in scope.names if n.symbol]


NO_PERMA = "NO_PERMA"


def listing_names(
    listings: pd.DataFrame, requested: Collection[str] = ()
) -> tuple[list[Name], list[Name]]:
    """-> (names to fetch, names never fetched): a listing of a reused ticker without a
    ``permaTicker`` is the second kind. ``requested`` (tickers) narrows when not empty."""
    wanted = {r.strip().upper() for r in requested}
    fetch: list[Name] = []
    never: list[Name] = []
    for row in listings.itertuples():
        if wanted and str(row.ticker).upper() not in wanted:
            continue
        name = Name(
            str(row.ticker),
            str(row.instrument_id),
            str(row.perma_ticker or ""),
            cast(date, row.start_date),
            None if pd.isna(row.end_date) else cast(date, row.end_date),
        )
        (never if bool(row.reused) and not name.perma else fetch).append(name)
    return fetch, never


def _window(since: date, until: date) -> str:
    return f"{since.isoformat()}..{until.isoformat()}"


def history_done(runs: Sequence[RunRecord], since: date, until: date) -> set[str]:
    """Instrument ids an earlier finished run fetched for ``since..until`` or a wider window."""
    done: set[str] = set()
    for record in runs:
        for key, status in record.items.items():
            label, _, window = status.partition(": ")
            first, _, last = window.partition("..")
            if (
                key.startswith("hist:")
                and label in DONE
                and first <= since.isoformat()
                and last >= until.isoformat()
            ):
                done.add(key.removeprefix("hist:"))
    return done


def split_findings(
    tiingo: pd.DataFrame, stored: pd.DataFrame, first: date, last: date
) -> list[str]:
    """Differences between the splits in Tiingo's ``actions`` (``ts``, ``split_factor``) and the
    stored ``events/split`` rows (``ts``, ``ratio``) of one instrument, over ``first..last`` (the
    span of the fetched bars): one line per day with a split on one side only or two ratios."""
    ours = {
        pd.Timestamp(t).date(): float(f)
        for t, f in zip(tiingo["ts"], tiingo["split_factor"], strict=True)
        if f != 1.0
    }
    theirs = (
        {}
        if stored.empty  # no split stored at all: an empty read has no ``ratio`` column
        else {
            pd.Timestamp(t).date(): float(r)
            for t, r in zip(stored["ts"], stored["ratio"], strict=True)
        }
    )
    found = []
    for day in sorted(set(ours) | {d for d in theirs if first <= d <= last}):
        a, b = ours.get(day), theirs.get(day)
        if a is None or b is None or not math.isclose(a, b, rel_tol=RATIO_TOLERANCE):
            ours_text, theirs_text = ("none" if v is None else f"{v:g}" for v in (a, b))
            found.append(f"{day.isoformat()}: tiingo {ours_text} vs events/split {theirs_text}")
    return found


def _fetch_name(
    run: IngestRun,
    source: Source,
    name: Name,
    since: date,
    until: date,
    stored_splits: pd.DataFrame,
) -> str:
    first = since if name.start is None else max(since, name.start)
    last = until if name.end is None else min(until, name.end)
    key = f"{name.vendor_key}:{first.isoformat()}:{last.isoformat()}"
    request = FetchRequest(key, name.instrument_id, until)
    try:
        normalized = run.fetch(source, request, raw_key=f"{name.vendor_key}__{since.isoformat()}")
    except NoResponseError:  # 404: Tiingo does not list the ticker
        return f"NO_DATA: {_window(since, until)}"
    bars = normalized.tables[BARS] if normalized else pd.DataFrame()
    run.stats["invalid_rows"] = run.stats.get("invalid_rows", 0) + int(
        normalized.notes.get("invalid_rows", 0) if normalized else 0
    )
    if normalized is None or bars.empty:
        return f"NO_DATA: {_window(since, until)}"
    days = bars["ts"].dt.date
    inside = (days >= first) & (days <= last)  # a listing's own dates, whatever the vendor sent
    run.stats["clipped_rows"] = run.stats.get("clipped_rows", 0) + int((~inside).sum())
    bars, days = bars[inside], days[inside]
    if bars.empty:
        return f"NO_DATA: {_window(since, until)}"
    frame = bars.drop(columns="symbol").assign(session_date=days)
    run.stage_sessions(BARS, f"hist_{name.instrument_id}", frame, source.name)
    mine = stored_splits[stored_splits["instrument_id"] == name.instrument_id]
    found = split_findings(normalized.parsed["actions"], mine, days.min(), days.max())
    if found:
        shown = "; ".join(found[:3]) + ("; ..." if len(found) > 3 else "")
        run.record_item(f"split:{name.instrument_id}", f"{SPLIT_MISMATCH}: {len(found)} {shown}")
    return f"OK: {_window(since, until)}"


def _publish(run: IngestRun, source_name: str) -> dict[str, int]:
    """Write the staged bars, one partition per session, WITHOUT replacing rows the session's
    partition already holds (see the module docstring) -> counts."""
    staged = run.writer.staging.collect(run.run_id, BARS)
    counts = dict.fromkeys(
        ("sessions_written", "rows", "overlap_rows", "already_stored_rows", "no_partition_rows"), 0
    )
    if staged is None:
        return counts
    staged["session_date"] = pd.to_datetime(staged["session_date"]).dt.date
    stored_days = run.reader.dates(BARS)
    frontier = min(stored_days) if stored_days else None
    now = pd.Timestamp(run.clock())
    for key, rows in staged.groupby("session_date", sort=True):
        day = pd.Timestamp(str(key)).date()
        existing = run.reader.table(BARS, day)
        if existing is None:
            if frontier is not None and day >= frontier:
                counts["no_partition_rows"] += len(rows)
                continue
            fresh = rows
        else:
            held = existing["instrument_id"].isin(set(rows["instrument_id"]))
            own = existing.loc[held, "source"].astype(str).eq(source_name)
            counts["already_stored_rows"] += int(own.sum())
            counts["overlap_rows"] += int((~own).sum())
            fresh = rows[~rows["instrument_id"].isin(set(existing["instrument_id"]))]
            if fresh.empty:
                continue
        fresh = fresh.assign(knowledge_ts=now)
        part = fresh if existing is None else pd.concat([existing, fresh], ignore_index=True)
        part = part.sort_values("instrument_id", kind="stable").reset_index(drop=True)
        run.writer.write_table(BARS, day, run.run_id, part, pending=True)
        counts["sessions_written"] += 1
        counts["rows"] += len(fresh)
    return counts


def _mismatches(items: dict[str, str]) -> tuple[int, list[str]]:
    """-> (split differences this run recorded, a few of them with their instrument)."""
    total, shown = 0, []
    for key, status in items.items():
        if key.startswith("split:") and status_label(status) == SPLIT_MISMATCH:
            count, _, detail = status.partition(": ")[2].partition(" ")
            total += int(count)
            shown.append(f"{key.removeprefix('split:')} {detail}")
    return total, shown[:DETAIL_LIMIT]


def _fetch_pending(
    run: IngestRun, source: Source, todo: Sequence[Name], since: date, until: date
) -> None:
    ids = [n.instrument_id for n in todo]
    stored = read_events(run.reader, SPLITS, since, until, ids).frame
    failed_in_a_row = 0
    for i, name in enumerate(todo, 1):
        item = f"hist:{name.instrument_id}"
        fetch = partial(_fetch_name, run, source, name, since, until, stored)
        status = run.attempt(item, fetch)
        failed_in_a_row = failed_in_a_row + 1 if status_label(status) == FETCH_ERROR else 0
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
        if failed_in_a_row >= STOP_AFTER_FAILED:
            run.partial(f"stopped: Tiingo failed {failed_in_a_row} names in a row ({status})")
            return


def _fill_picks(
    run: IngestRun, until: date, done: Collection[str], fill: int
) -> list[FillCandidate]:
    """The first ``fill`` names of the universe, most useful first, that no earlier run fetched.
    Names this (resumed) run already asked for stay in the count, so a restart fetches no more
    than N in all."""
    waiting = (c for c in fill_order(run.reader, until) if c.instrument_id not in done)
    return list(islice(waiting, fill))


def ingest_bars_history(
    ctx: TaskContext,
    source: Source,
    requested: Sequence[str],
    since: date,
    until: date,
    force: bool = False,
    limit: int | None = None,
    include_tiers: bool = False,
    fill: int | None = None,
    from_listings: bool = False,
) -> RunRecord:
    """Daily bars of the scope list, its funds' references and ``requested`` symbols (plus the
    tier A / B names with ``include_tiers``) from ``since`` to ``until`` (``limit``: fetch at
    most that many names this run; ``force``: also the names an earlier run fetched for the
    window; ``fill``: also the first ``fill`` names of the universe without history, most useful
    first; ``from_listings``: the listings of the universe over the window instead of the scope
    list, see the module docstring). Never more than the month's remaining symbol budget."""
    if until < since:
        raise ValueError(f"--until {until} is before --since {since}")
    if from_listings and fill is not None:
        raise ValueError("--from-listings and --fill are two ways to pick names: use one")
    with IngestRun(ctx, TASK, until, resume=True) as run:
        runs = finished_runs(run.writer, TASK)
        done: Collection[str] = set() if force else history_done(runs, since, until)
        picks = _fill_picks(run, until, done, max(0, fill)) if fill is not None else []
        never: list[Name] = []
        if from_listings:
            listings, _ = listings_over(run.reader, since, until)
            names, never = listing_names(listings, requested)
            scope = ScopedInstruments(until, None, None, None, (), ())
            unknown: tuple[str, ...] = ()
            for name in never:
                run.record_item(
                    f"perma:{name.instrument_id}",
                    f"{NO_PERMA}: {name.symbol} was used by several listings and this one has "
                    "no permaTicker",
                )
        else:
            scope = scoped_instruments(
                run.reader,
                ctx.configs,
                until,
                [*requested, *(p.symbol for p in picks)],
                DEFAULT_REASONS + ((TIER,) if include_tiers else ()),
            )
            names, unknown = names_of(scope), scope.unresolved
        for symbol in unknown:
            run.record_item(
                f"sym:{symbol}", f"{UNKNOWN}: not in the reference of {scope.reference_snapshot}"
            )
        pending = [
            n
            for n in names
            if n.instrument_id not in done and f"hist:{n.instrument_id}" not in run.items
        ]
        budget = ctx.settings.tiingo_monthly_symbol_budget
        remaining = max(0, budget - len(month_symbols(run)))
        todo = pending[: remaining if limit is None else min(remaining, max(0, limit))]
        _fetch_pending(run, source, todo, since, until)
        run.stats.update(_publish(run, source.name))
        mismatches, shown = _mismatches(run.items)
        statuses = [status_label(run.items.get(f"hist:{n.instrument_id}", "")) for n in todo]
        left = len(pending) - sum(1 for s in statuses if s in DONE)
        picked = {p.instrument_id for p in picks}
        fetched = {n.instrument_id for n, s in zip(todo, statuses, strict=True) if s in DONE}
        used = len(month_symbols(run))
        pace = ctx.settings.vendor("tiingo").min_interval_s or HOURLY_FREE_PACE_S
        run.stats.update(
            window=_window(since, until),
            licence=ctx.settings.tiingo_licence,  # the rows' terms, in the run record
            symbols=len(names) + len(unknown),
            no_perma=len(never),
            by_reason=dict(Counter(r for n in scope.names for r in n.reasons)),
            tier_session=scope.tier_session,
            unknown_symbols=list(unknown),
            skipped_done=len(names) - len(pending),
            fetched=len(todo),
            filled=len(picked & fetched),
            month_budget=budget,
            month_used=used,
            month_remaining=max(0, budget - used),
            pending=left,
            eta_h=round(left * pace / 3600, 1),
            split_mismatches=mismatches,
            split_mismatch_examples=shown,
        )
        run.stats["items"] = run.counts()
    return run.record
