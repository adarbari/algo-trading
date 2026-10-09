"""The ``outcomes`` task (ADR 0053 decision 3): write every forward-outcome window a session
closes to ``outcomes/instrument/forward_returns@v1``, the grain only the edge harness reads.

For a window-end session T and each horizon h, S is the h-th exchange session before T; the
rows are the names in the universe at S with a bar at S, measured from S's close to T's
(``outcome_paths``) on bars split-adjusted as of T, and written to partition S. Horizons and
benchmarks come from the site's edge documents that are not rejected or blocked
(``config.edges``), the winners study's (``config/site/studies/winners.toml``), plus the harness
default (``DEFAULT_HORIZON`` sessions over ``DEFAULT_BENCHMARK``): a new edge needs no code
change. Before the first
universe snapshot the names are the listing history's alive on S (``data.listings.universe_asof``,
survivors and the delisted alike), not today's snapshot; a name with no bar at T is DELISTED when
the reference snapshot, or the listing history (``delisted_by``: a last trading day on or
before T), says it left. A window whose S is before the first
stored bars session is not computed; one whose T has not closed is refused (``knowledge_ts``,
the write time, is never before the window's close).

Each night also recomputes the ``RECHECK`` window ends before it, reading delistings from the
latest reference snapshot (``outcome_paths``: a delisting is stamped when the weekly build
notices it). A re-run never retracts a row it no longer computes (runs merge); a row whose
bars later vanish stays until a restating backfill.

A horizon above ``NIGHTLY_MAX_HORIZON`` (the 504-session edges) is computed only in a
``--from/--to`` backfill, so the nightly's bars read stays at the recheck window plus 252 sessions.

``--from/--to`` backfills: each window-end session is its own run, exactly what that night's
run writes (a re-run's rows win per instrument, horizon and benchmark), so backfilled rows equal
nightly rows on the same store. Bars restated after T are read as stored now; the bars of a
backfill chunk are read once (``CHUNK`` window ends at a time).

The acceptance check (``check_outcomes``) holds the run to its own count: every eligible name has
a row or a reason, and the rows are stored.
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import Documents, load_edges
from algotrade.config.edges.winners import load_winners
from algotrade.config.env import config_dir
from algotrade.config.site.settings import SourcesSettings
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import close_time, next_session, sessions_between, sessions_ending
from algotrade.data import StoreReader
from algotrade.data.listings.universe import delisted_by, universe_asof
from algotrade.data.prices import SessionBars, bars, session_bars
from algotrade.data.reference import instruments, load_universe
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade_ingestion.tasks.derived.outcome_paths import Window, window_rows
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "outcomes"
SOURCE = "outcomes"
TABLE = FORWARD_RETURNS
TABLES = (TABLE,)
DEFAULT_HORIZON = 20  # sessions: the harness default (ADR 0053), always computed
DEFAULT_BENCHMARK = "SPY"
CHUNK = 40  # window ends whose bars are read at once in a backfill
# A night also recomputes the window ends of the sessions before it: the weekly reference build
# stamps a delisting when it notices, after the last bar, so a name that was a reason the night
# its window closed becomes a DELISTED row (its new run wins on the merge key).
RECHECK = 10
NIGHTLY_MAX_HORIZON = 252  # longer horizons are backfill-only: the nightly panel stays this deep
SHOWN = 5  # reasons listed per window in the run stats
SITE = FileConfigStore(config_dir())


def horizons_and_benchmarks(configs: Documents | None = None) -> tuple[list[int], list[str]]:
    """The horizons (sessions) and benchmark tickers of the site's open edge documents and their
    ``[[variants]]``, with the harness default and the winners study's (ADR 0053, ED6)."""
    edges = [e for e in load_edges(configs or SITE) if e.status not in CLOSED]
    outcomes = [o for e in edges for o in (e.outcome, *(v.outcome for v in e.variants))]
    study = load_winners(configs or SITE)
    horizons = {DEFAULT_HORIZON, study.horizon_sessions}
    horizons |= {h for o in outcomes for h in o.horizon_sessions}
    benchmarks = {DEFAULT_BENCHMARK, study.benchmark, *(o.benchmark for o in outcomes)} - {"none"}
    return sorted(horizons), sorted(benchmarks)


def compute_outcomes(
    ctx: TaskContext, session: date, start: date | None = None, end: date | None = None
) -> RunRecord:
    """The windows ``session`` and the ``RECHECK`` sessions before it close, or those of every
    window-end session in ``start..end``
    (one run each) -> the last run's record."""
    ends = (
        sessions_between(start, end or session) if start else sessions_ending(session, RECHECK + 1)
    )
    if not ends:
        raise ValueError(f"no exchange session in {start}..{end or session}")
    if close_time(ends[-1]) > ctx.clock():
        raise ValueError(f"the window ending {ends[-1]} has not closed yet")
    horizons, benchmarks = horizons_and_benchmarks(ctx.configs)
    nightly = start is None
    gone = _delisted(ctx.reader, ends[-1])  # the latest snapshot: delistings noticed since
    listed = _listing_delisted(ctx.reader, ends[-1])  # filtered to each window end in ``_one``
    stored = ctx.reader.dates("bars/1d")
    first = stored[0] if stored else ends[-1]
    record: RunRecord | None = None
    for i in range(0, len(ends), CHUNK):
        chunk = ends[i : i + CHUNK]
        lo = sessions_ending(
            chunk[0], max(h for h in horizons if not nightly or h <= NIGHTLY_MAX_HORIZON) + 1
        )[0]
        panel = session_bars(
            ctx.reader, max(lo, first), chunk[-1], columns=("high", "low", "close")
        )
        for t in chunk:
            record = _one(ctx, t, horizons, benchmarks, first, panel, gone, listed, nightly)
    assert record is not None
    return record


def _one(
    ctx: TaskContext,
    end: date,
    horizons: Sequence[int],
    benchmarks: Sequence[str],
    first: date,
    panel: SessionBars,
    gone: dict[str, date],
    listed: dict[str, date],
    nightly: bool,
) -> RunRecord:
    noticed = end
    for _ in range(RECHECK):
        noticed = next_session(noticed)
    # a last trading day counts when on or before ``end``; a reference stamp (the notice date)
    # when within the ``RECHECK`` sessions after it, the nights that recheck this window
    left = {i: d for i, d in listed.items() if d <= end} | {
        i: d for i, d in gone.items() if d <= noticed
    }
    with IngestRun(ctx, TASK, end) as run:
        for h in horizons:
            if nightly and h > NIGHTLY_MAX_HORIZON:
                run.record_item(f"h{h}", "BACKFILL_ONLY")
                continue
            window = Window(tuple(sessions_ending(end, h + 1)))
            if window.start < first:
                run.record_item(f"h{h}", "BEFORE_HISTORY")
                continue
            names, pre_snapshot = _universe_ids(run.reader, window.start, not nightly)
            resolver = run.resolver(window.start)
            frames, reasons, eligible = [], {}, 0
            prices = panel.window(window.start, end)
            for ticker in benchmarks:
                bench = resolver.id_for(ticker) if resolver.knows(ticker) else None
                rows, why = window_rows(prices, window, names, bench, left)
                frames.append(rows.assign(benchmark=ticker))
                reasons, eligible = why, len(rows) + len(why)
            out = pd.concat(frames, ignore_index=True)
            out = out.assign(
                ts=close_time(window.start), horizon_sessions=h, window_end=end
            ).sort_values(["instrument_id", "benchmark"], kind="stable")
            if len(out):
                run.write(TABLE, out.reset_index(drop=True), SOURCE, session=window.start)
            run.record_item(f"h{h}", f"OK: {len(out)} rows")
            run.stats[f"h{h}"] = {
                "start": window.start.isoformat(),
                "eligible": eligible,
                "rows": len(out) // max(len(benchmarks), 1),
                "reasons": len(reasons),
                "examples": dict(sorted(reasons.items())[:SHOWN]),
                "pre_snapshot": pre_snapshot,  # survivors only: no snapshot, no listing history
            }
    return run.record


def _universe_ids(
    reader: StoreReader, start: date, backfill: bool = False
) -> tuple[set[str], bool]:
    """The names to measure from ``start`` and whether they are today's (survivorship): the
    universe snapshot's, or before the first snapshot the listing history's alive on ``start``
    (with no listing history stored: the snapshot's names, flagged, in the nightly; a backfill
    raises ``MissingDataError``, its rows would be survivors only)."""
    universe = load_universe(reader, start)
    if not universe.pre_snapshot:
        return set(universe.instruments), False
    try:
        return set(universe_asof(reader, start).instruments["instrument_id"].astype(str)), False
    except MissingDataError:
        if backfill:
            raise
        return set(universe.instruments), True


def _listing_delisted(reader: StoreReader, on: date) -> dict[str, date]:
    """Listing-history delistings known on ``on`` (none when no history is stored)."""
    try:
        return delisted_by(reader, on)
    except MissingDataError:
        return {}


def _delisted(reader: StoreReader, on: date) -> dict[str, date]:
    """Instrument id -> delisting date, as the reference snapshot at ``on`` records it."""
    frame = instruments(reader, on)
    if "delisted_on" not in frame.columns:
        return {}
    dated = frame[frame["delisted_on"].notna()]
    return dict(
        zip(
            dated["instrument_id"].astype(str),
            pd.to_datetime(dated["delisted_on"]).dt.date,
            strict=True,
        )
    )


def check_outcomes(reader: StoreReader, session: date, s: SourcesSettings) -> list[Check]:
    """The acceptance of the ``outcomes`` step for window end ``session``: for each horizon the
    run computed, every name in the universe at S with a bar at S (counted again here, not
    taken from the run) has a row or a reason, and the run's rows are stored."""
    runs = [r for r in reader.runs(TASK, session) if r.status == RunStatus.COMPLETE]
    if not runs:
        return [Check("outcomes", "FAIL", f"no complete outcomes run for {session}")]
    problems = []
    for key, value in sorted(runs[-1].stats.items()):
        if not (key.startswith("h") and isinstance(value, dict)):
            continue
        start = date.fromisoformat(value["start"])
        unaccounted = len(_eligible(reader, start)) - value["rows"] - value["reasons"]
        stored = reader.table(TABLE, start)
        mine = set() if stored is None else set(
            stored.loc[
                (pd.to_datetime(stored["window_end"]).dt.date == session)
                & (stored["horizon_sessions"] == int(key[1:])),
                "instrument_id",
            ].astype(str)
        )  # fmt: skip
        if unaccounted or len(mine) != value["rows"]:
            problems.append(f"{key}: {unaccounted} names without a row or a reason, "
                            f"{len(mine)} of {value['rows']} rows stored")  # fmt: skip
    if problems:
        return [Check("outcomes", "FAIL", "; ".join(problems))]
    return [Check("outcomes", "PASS", f"every eligible name has a row or a reason for {session}")]


def _eligible(reader: StoreReader, start: date) -> set[str]:
    """The names in the universe at ``start`` with a bar at ``start``."""
    universe = _universe_ids(reader, start)[0]
    day = bars(reader, "1d", start, start, columns=("close",))
    return universe & set(day.loc[day["close"].notna(), "instrument_id"].astype(str))
