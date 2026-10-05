"""IBKR's implied and historical vol per underlying (``volatility/ibkr_iv30``, ADR 0028).

Two modes, both through the read-only facade (``ctx.sources["ibkr"]``, opened and closed
around the work) and only for underlyings with a resolved IBKR contract
(``instruments/ibkr_contracts``, the ``ibkr-contracts`` task):

- **History backfill** (``backfill_ivs``, ``--from`` / ``--to``): per underlying ONE request
  (``OPTION_IMPLIED_VOLATILITY`` daily bars over the whole range; IB's HV comes only from the
  nightly snapshot: a history row keeps the HV of the stored row it replaces, else has
  none), paced by the shared
  ``ibkr_historical`` limiter (``[ibkr] historical_min_interval_s``). Rows are
  ``source_kind = history``, one partition per session. Resumable per underlying, also
  across nights: an underlying is skipped when an earlier finished run (this task or the
  nightly) already fetched its history from the same start or earlier (item ``hist:<id>``,
  status ``OK: <from>`` or ``NO_DATA: <from>``). ``NO_DATA`` only when IB ANSWERED with no
  bars; a request IB did not answer (timeout, pacing or connectivity error: the facade's
  ``TransientFetchError``) is retried ``HISTORY_ATTEMPTS`` times with a growing back-off
  (``cool_down`` holds the historical limiter for every process), then recorded
  ``FETCH_ERROR`` (pending: a resume or a later run fetches it again); an error a retry
  cannot fix (no permissions, no security definition) is ``FETCH_ERROR`` at once.
  ``STOP_AFTER_FAILED`` names IB did not answer in a row end the backfill part of the run
  (the rest stay pending). Order: the most liquid names first, names earlier runs could not
  fetch last (``by_liquidity``), so they never block the rest; ``limit`` caps a run.
- **Nightly** (``nightly_ivs``): one streamed snapshot of every underlying's IV (tick 106)
  and HV (tick 104) after the close, ``[ibkr] iv_batch`` streams at a time, written to the
  session as ``source_kind = snapshot``; then the history of up to ``[ibkr]
  iv_backfill_per_night`` underlyings that have none yet (new names; the initial backfill
  spread over nights), up to the session before.

Runs merge per instrument and session (the latest run's row wins, so a later history
backfill replaces a snapshot, keeping its HV, as a second backfill of a session does).
When the gateway cannot be opened the run records ``skipped`` (the nightly step is SKIPPED
with a WARN, never FAILED) and is PARTIAL, never COMPLETE: what a resumed run had staged is
still published, nothing is dropped unpublished. Stats: coverage (snapshot rows with an IV
over the coverage), backfill progress and the estimated time left at the current pace.
"""

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.model.fields import ROLLUP_TABLE_PREFIX
from algotrade.core.time.calendar import sessions_ending
from algotrade.data.reference import ibkr_contracts, snapshot
from algotrade.data.volatility import IBKR_IV30, ibkr_stored_hv
from algotrade.services.features import field_view, site_features, site_store
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.market.option_chains import select_underlyings
from algotrade_sources.framework.base import (
    FetchRequest,
    Normalized,
    SessionSource,
    SessionUnavailableError,
    Throttled,
    TransientFetchError,
    opened,
)

NIGHTLY_TASK, HISTORY_TASK = "ibkr_iv", "ibkr_iv_history"
TABLE = IBKR_IV30
SOURCE = "ibkr"
HISTORY, SNAPSHOT = "history", "snapshot"
DONE = ("OK", "NO_DATA")  # history item statuses that need no refetch
CHECKPOINT_EVERY = 20
REQUESTS_PER_NAME = 1  # one historical request per name: the IV series
VOLS = ("iv30_ibkr", "hv30_ibkr")
HISTORY_ATTEMPTS = 3  # requests per name before it is FETCH_ERROR (pending)
BACKOFF_S = 30.0  # first back-off before a retry; doubles each time (30 s, 60 s)
STOP_AFTER_FAILED = 5  # names IB did not answer in a row (gateway / IB trouble): stop
# Backfill order inputs (stored rollups, through services.features): option tiers, the
# liquidity class expression (config/site/features/liquidity.toml), 20-session dollar volume.
PRICE_GROUP, OPTION_GROUP = "price_stats", "option_liquidity"
LIQUID_TIERS, LIQUID_CLASSES = ("A", "B"), ("HIGH", "MEDIUM")
LIQUIDITY_CLASS = "liquidity_class"


@dataclass(frozen=True)
class Name:
    instrument_id: str
    symbol: str
    conid: int


def covered_names(run: IngestRun, session: date, symbols: Sequence[str]) -> tuple[list[Name], int]:
    """The coverage's underlyings with an IBKR contract (alphabetical) -> (names, coverage
    size)."""
    underlyings = select_underlyings(run.reader, session, symbols)
    contracts = ibkr_contracts(run.reader, session)
    conids = (
        {}
        if contracts is None
        else dict(zip(contracts["instrument_id"].astype(str), contracts["conid"], strict=True))
    )
    names = [
        Name(u.instrument_id, u.symbol, int(conids[u.instrument_id]))
        for u in underlyings
        if u.instrument_id in conids
    ]
    names.sort(key=lambda n: (n.symbol, n.instrument_id))
    return names, len(underlyings)


def _rollup_field(features_table: str, column: str) -> str:
    return f"rollup.{features_table.removeprefix(ROLLUP_TABLE_PREFIX)}.{column}"


def by_liquidity(
    run: IngestRun, session: date, names: Sequence[Name], last: Collection[str] = ()
) -> tuple[list[Name], int]:
    """``names`` in backfill order -> (ordered, how many are liquid). ``last``: instrument
    ids that failed in earlier runs, after every other name (a name IB keeps failing never
    blocks the rest), in the same order among themselves. Liquid first: an option
    tier A or B on either side (``option_liquidity`` ``put_tier`` / ``call_tier``) or a
    ``liquidity_class`` of HIGH or MEDIUM; within each part by ``adv_usd_20d`` descending,
    names without one after; ties by symbol. Inputs are the stored rollups of the latest
    session on or before ``session`` with ``price_stats`` rows (the backfill runs before
    that night's rollups); without any, the order is alphabetical."""
    features = site_features(site_store(run.ctx.configs))
    snap = snapshot(run.reader, features.table(PRICE_GROUP), session)
    info: dict[str, tuple[bool, float | None]] = {}
    if snap is not None and not snap.pre_snapshot and names:
        option = features.table(OPTION_GROUP)
        fields = [
            _rollup_field(features.table(PRICE_GROUP), "adv_usd_20d"),
            _rollup_field(option, "put_tier"),
            _rollup_field(option, "call_tier"),
            f"feature.{LIQUIDITY_CLASS}",
        ]
        ids = [n.instrument_id for n in names]
        view = field_view(run.reader, snap.snapshot_date, fields, ids, features=features).frame
        # a table with no partition that day leaves its columns out: all unknown
        nothing = pd.Series([None] * len(view), index=view.index, dtype=object)
        adv, put, call, label = (view.get(f, nothing) for f in fields)
        for i, row_id in enumerate(view["instrument_id"].astype(str)):
            liquid = put.iloc[i] in LIQUID_TIERS or call.iloc[i] in LIQUID_TIERS
            liquid = liquid or (isinstance(label.iloc[i], str) and label.iloc[i] in LIQUID_CLASSES)
            dollars = adv.iloc[i]
            info[row_id] = (liquid, None if pd.isna(dollars) else float(dollars))

    def key(n: Name) -> tuple[bool, int, int, float, str, str]:
        liquid, dollars = info.get(n.instrument_id, (False, None))
        known = dollars is not None
        retry = n.instrument_id in last
        return (
            retry,
            0 if liquid else 1,
            0 if known else 1,
            -(dollars or 0.0),
            n.symbol,
            n.instrument_id,
        )

    ordered = sorted(names, key=key)
    return ordered, sum(1 for n in ordered if info.get(n.instrument_id, (False, None))[0])


def history_failed(runs: Sequence[RunRecord]) -> set[str]:
    """Instrument ids an earlier finished run could not fetch (``FETCH_ERROR``): still pending."""
    return {
        key.removeprefix("hist:")
        for record in runs
        for key, status in record.items.items()
        if key.startswith("hist:") and status_label(status) == FETCH_ERROR
    }


def history_done(runs: Sequence[RunRecord], start: date) -> set[str]:
    """Instrument ids whose history an earlier finished run fetched from ``start`` or before."""
    done: set[str] = set()
    for record in runs:
        for key, status in record.items.items():
            label, _, since = status.partition(": ")
            if key.startswith("hist:") and label in DONE and since and since <= start.isoformat():
                done.add(key.removeprefix("hist:"))
    return done


def _answered(run: IngestRun, source: SessionSource, request: FetchRequest) -> Normalized | None:
    """``run.fetch`` retried while IB does not answer (``TransientFetchError``): at most
    ``HISTORY_ATTEMPTS`` requests, backing off ``BACKOFF_S`` x 2^n in between (a hold on the
    source's historical limiter when it is ``Throttled``); the last error is raised."""
    for attempt in range(1, HISTORY_ATTEMPTS + 1):
        try:
            return run.fetch(source, request)
        except TransientFetchError:
            if attempt == HISTORY_ATTEMPTS:
                raise
            if isinstance(source, Throttled):
                source.cool_down(BACKOFF_S * 2 ** (attempt - 1))
    raise AssertionError("unreachable")  # pragma: no cover


def _noting_unanswered(fetch: Callable[[], str], seen: list[TransientFetchError]) -> str:
    """``fetch()``, noting in ``seen`` when it failed because IB did not answer."""
    try:
        return fetch()
    except TransientFetchError as exc:
        seen.append(exc)
        raise


def _fetch_history(
    run: IngestRun,
    source: SessionSource,
    name: Name,
    start: date,
    end: date,
    kept_hv: Mapping[tuple[str, date], float],
) -> str:
    key = f"volhist__{name.symbol}__{name.conid}__{start.isoformat()}"  # IbkrSource keys
    normalized = _answered(run, source, FetchRequest(key, name.instrument_id, end))
    if normalized is None or "volhist" not in normalized.parsed:
        raise NoResponseError(f"IBKR {key}: nothing parsed")
    rows = normalized.parsed["volhist"]
    rows = rows[(rows["date"] >= start) & (rows["date"] <= end)]
    if rows.empty:
        return f"NO_DATA: {start.isoformat()}"
    # IV only: a session's stored HV is kept (this row replaces the stored one)
    stored = [kept_hv.get((name.instrument_id, d)) for d in rows["date"]]
    fetched = rows["hv30_ibkr"].astype(float).to_numpy()
    hv = pd.Series([f if k is None else k for f, k in zip(fetched, stored, strict=True)])
    frame = pd.DataFrame(
        {
            "instrument_id": name.instrument_id,
            "symbol": name.symbol,
            "iv30_ibkr": rows["iv30_ibkr"].astype(float).to_numpy(),
            "hv30_ibkr": hv.astype(float).to_numpy(),
            "source_kind": HISTORY,
            "session_date": list(rows["date"]),
        }
    )
    run.stage_sessions(TABLE, f"hist_{name.instrument_id}", frame, SOURCE)
    return f"OK: {start.isoformat()}"


def _backfill(
    run: IngestRun,
    source: SessionSource,
    names: Sequence[Name],
    start: date,
    end: date,
    limit: int | None,
) -> dict[str, int | float]:
    """Fetch the history of ``names`` not done yet (``limit`` at most), the most liquid
    first and names earlier runs could not fetch last (``by_liquidity``) -> progress stats."""
    earlier = finished_runs(run.writer, NIGHTLY_TASK, HISTORY_TASK)
    done = history_done(earlier, start)
    ordered, liquid = by_liquidity(run, run.session, names, history_failed(earlier) - done)
    pending = [
        n
        for n in ordered
        if n.instrument_id not in done and f"hist:{n.instrument_id}" not in run.items
    ]
    todo = pending if limit is None else pending[: max(0, limit)]
    kept_hv = ibkr_stored_hv(run.reader, start, end, [n.instrument_id for n in todo])
    unanswered_in_a_row = 0
    for i, name in enumerate(todo, 1):
        item = f"hist:{name.instrument_id}"
        fetch = partial(_fetch_history, run, source, name, start, end, kept_hv)
        transient: list[TransientFetchError] = []
        status = run.attempt(item, partial(_noting_unanswered, fetch, transient))
        unanswered_in_a_row = unanswered_in_a_row + 1 if transient else 0
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
        if unanswered_in_a_row >= STOP_AFTER_FAILED:
            run.partial(
                f"backfill stopped: IB did not answer {unanswered_in_a_row} names in a row "
                f"({status})"
            )
            break
    statuses = [status_label(run.items.get(f"hist:{n.instrument_id}", "")) for n in todo]
    left = len(pending) - sum(1 for s in statuses if s in DONE)
    pace = run.ctx.settings.ibkr.historical_min_interval_s
    return {
        "backfill_names": len(names),
        "backfill_liquid": liquid,
        "backfilled": len(todo),
        "backfill_failed": sum(1 for s in statuses if s and s not in DONE),
        "backfill_pending": left,
        "backfill_eta_h": round(left * REQUESTS_PER_NAME * pace / 3600, 1),
    }


def _snapshot(run: IngestRun, source: SessionSource, names: Sequence[Name], size: int) -> int:
    """Stream every name's IV and HV in batches -> names with an IV."""
    with_iv = 0
    for at in range(0, len(names), max(1, size)):
        batch = names[at : at + size]
        key = "vols__" + "+".join(f"{n.symbol}:{n.conid}" for n in batch)
        item = f"snap:{batch[0].instrument_id}"
        try:
            normalized = run.fetch(source, FetchRequest(key, None, run.session), f"vols__{at:05d}")
        except SessionUnavailableError:
            raise
        except Exception as exc:
            run.fail(item, f"{type(exc).__name__}: {exc}")
            continue
        found = normalized.parsed["vols"].set_index("symbol") if normalized else pd.DataFrame()
        rows = []
        for n in batch:
            iv = found["iv30_ibkr"].get(n.symbol) if not found.empty else None
            hv = found["hv30_ibkr"].get(n.symbol) if not found.empty else None
            if pd.notna(iv) or pd.notna(hv):
                rows.append((n.instrument_id, n.symbol, iv, hv))
                with_iv += int(pd.notna(iv))
        run.record_item(item, f"OK: {len(rows)}/{len(batch)}")
        if rows:
            frame = pd.DataFrame(rows, columns=["instrument_id", "symbol", *VOLS])
            frame = frame.astype(dict.fromkeys(VOLS, float))
            frame = frame.assign(source_kind=SNAPSHOT, session_date=run.session)
            run.stage_sessions(TABLE, f"snap_{at:05d}", frame, SOURCE)
    return with_iv


def _run(
    ctx: TaskContext,
    source: SessionSource,
    task: str,
    session: date,
    symbols: Sequence[str],
    work: Callable[[IngestRun, SessionSource, list[Name]], None],
) -> RunRecord:
    with IngestRun(ctx, task, session, resume=True) as run:
        names, coverage = covered_names(run, session, symbols)
        run.stats.update(underlyings=coverage, with_contract=len(names))
        try:
            with opened(source):
                work(run, source, names)
        except SessionUnavailableError as exc:
            # Not COMPLETE (nothing new was fetched), and what a resumed run staged before is
            # published below: a COMPLETE skip would keep its items as done and drop that
            # staging unpublished.
            run.stats["skipped"] = f"WARN: {exc}"
            run.partial(f"skipped: {exc}")
        written = run.publish_sessions(TABLE)
        run.stats.update(sessions_written=len(written), rows=sum(written.values()))
    return run.record


def backfill_ivs(
    ctx: TaskContext,
    source: SessionSource,
    start: date,
    end: date,
    symbols: Sequence[str] = (),
    limit: int | None = None,
) -> RunRecord:
    """IB's IV history from ``start`` to ``end`` for every covered underlying not backfilled
    yet, most liquid first (``symbols``: only those; ``limit``: at most that many this run)."""

    def work(run: IngestRun, source: SessionSource, names: list[Name]) -> None:
        run.stats.update(history_from=start.isoformat(), history_to=end.isoformat())
        run.stats.update(_backfill(run, source, names, start, end, limit))

    return _run(ctx, source, HISTORY_TASK, end, symbols, work)


def nightly_ivs(
    ctx: TaskContext, source: SessionSource, session: date, symbols: Sequence[str] = ()
) -> RunRecord:
    """The session's IV snapshot for every covered underlying, then the history of up to
    ``[ibkr] iv_backfill_per_night`` underlyings without any (up to the session before)."""
    settings = ctx.settings.ibkr

    def work(run: IngestRun, source: SessionSource, names: list[Name]) -> None:
        with_iv = _snapshot(run, source, names, settings.iv_batch)
        coverage = int(run.stats["underlyings"])
        run.stats.update(
            with_iv=with_iv,
            coverage_pct=round(100.0 * with_iv / coverage, 1) if coverage else None,
        )
        if settings.iv_backfill_per_night > 0:
            end = sessions_ending(session, 2)[0]
            start = session - timedelta(days=settings.iv_history_days)
            stats = _backfill(run, source, names, start, end, settings.iv_backfill_per_night)
            run.stats.update(stats)

    return _run(ctx, source, NIGHTLY_TASK, session, symbols, work)
