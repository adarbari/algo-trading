"""IBKR's implied and historical vol per underlying (``volatility/ibkr_iv30``, ADR 0028).

Two modes, both through the read-only facade (``ctx.sources["ibkr"]``, opened and closed
around the work) and only for underlyings with a resolved IBKR contract
(``instruments/ibkr_contracts``, the ``ibkr-contracts`` task):

- **History backfill** (``backfill_ivs``, ``--from`` / ``--to``): per underlying ONE request
  per series (``OPTION_IMPLIED_VOLATILITY`` and ``HISTORICAL_VOLATILITY`` daily bars over the
  whole range), paced by the shared ``ibkr_historical`` limiter (``[ibkr]
  historical_min_interval_s``). Rows are ``source_kind = history``, one partition per
  session. Resumable per underlying, also across nights: an underlying is skipped when an
  earlier finished run (this task or the nightly) already fetched its history from the same
  start or earlier (item ``hist:<id>``, status ``OK: <from>`` or ``NO_DATA: <from>``);
  ``limit`` caps a run (priority symbols first, then alphabetical).
- **Nightly** (``nightly_ivs``): one streamed snapshot of every underlying's IV (tick 106)
  and HV (tick 104) after the close, ``[ibkr] iv_batch`` streams at a time, written to the
  session as ``source_kind = snapshot``; then the history of up to ``[ibkr]
  iv_backfill_per_night`` underlyings that have none yet (new names; the initial backfill
  spread over nights), up to the session before.

Runs merge per instrument and session (the latest run's row wins, so a later history
backfill replaces a snapshot). When the gateway cannot be opened the run records ``skipped``
(the nightly step is SKIPPED with a WARN, never FAILED). Stats: coverage (snapshot rows with
an IV over the coverage), backfill progress and the estimated time left at the current pace.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.data.reference import ibkr_contracts
from algotrade.data.volatility import IBKR_IV30
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.market.option_chains import select_underlyings
from algotrade_sources.framework.base import (
    FetchRequest,
    SessionSource,
    SessionUnavailableError,
    opened,
)

NIGHTLY_TASK, HISTORY_TASK = "ibkr_iv", "ibkr_iv_history"
TABLE = IBKR_IV30
SOURCE = "ibkr"
HISTORY, SNAPSHOT = "history", "snapshot"
DONE = ("OK", "NO_DATA")  # history item statuses that need no refetch
CHECKPOINT_EVERY = 20
REQUESTS_PER_NAME = 2  # one historical request per series (IV, HV)
VOLS = ("iv30_ibkr", "hv30_ibkr")


@dataclass(frozen=True)
class Name:
    instrument_id: str
    symbol: str
    conid: int


def covered_names(
    run: IngestRun, session: date, symbols: Sequence[str], priority: Sequence[str]
) -> tuple[list[Name], int]:
    """The coverage's underlyings with an IBKR contract (priority symbols first, then
    alphabetical) -> (names, coverage size)."""
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
    first = {s.upper(): i for i, s in enumerate(priority)}
    names.sort(key=lambda n: (first.get(n.symbol, len(first)), n.symbol))
    return names, len(underlyings)


def history_done(runs: Sequence[RunRecord], start: date) -> set[str]:
    """Instrument ids whose history an earlier finished run fetched from ``start`` or before."""
    done: set[str] = set()
    for record in runs:
        for key, status in record.items.items():
            label, _, since = status.partition(": ")
            if key.startswith("hist:") and label in DONE and since and since <= start.isoformat():
                done.add(key.removeprefix("hist:"))
    return done


def _fetch_history(
    run: IngestRun, source: SessionSource, name: Name, start: date, end: date
) -> str:
    key = f"volhist__{name.symbol}__{name.conid}__{start.isoformat()}"  # IbkrSource keys
    normalized = run.fetch(source, FetchRequest(key, name.instrument_id, end))
    if normalized is None or "volhist" not in normalized.parsed:
        raise NoResponseError(f"IBKR {key}: nothing parsed")
    rows = normalized.parsed["volhist"]
    rows = rows[(rows["date"] >= start) & (rows["date"] <= end)]
    if rows.empty:
        return f"NO_DATA: {start.isoformat()}"
    frame = pd.DataFrame(
        {
            "instrument_id": name.instrument_id,
            "symbol": name.symbol,
            "iv30_ibkr": rows["iv30_ibkr"].astype(float).to_numpy(),
            "hv30_ibkr": rows["hv30_ibkr"].astype(float).to_numpy(),
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
    """Fetch the history of ``names`` not done yet (``limit`` at most) -> progress stats."""
    done = history_done(finished_runs(run.writer, NIGHTLY_TASK, HISTORY_TASK), start)
    pending = [
        n
        for n in names
        if n.instrument_id not in done and f"hist:{n.instrument_id}" not in run.items
    ]
    todo = pending if limit is None else pending[: max(0, limit)]
    for i, name in enumerate(todo, 1):
        item = f"hist:{name.instrument_id}"
        run.attempt(item, partial(_fetch_history, run, source, name, start, end))
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    left = len(pending) - sum(
        1 for n in todo if status_label(run.items.get(f"hist:{n.instrument_id}", "")) in DONE
    )
    pace = run.ctx.settings.ibkr.historical_min_interval_s
    return {
        "backfill_names": len(names),
        "backfilled": len(todo),
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
        names, coverage = covered_names(run, session, symbols, ctx.settings.cboe_priority_symbols)
        run.stats.update(underlyings=coverage, with_contract=len(names))
        try:
            with opened(source):
                work(run, source, names)
        except SessionUnavailableError as exc:
            run.stats["skipped"] = f"WARN: {exc}"
            return run.record
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
    """IB's IV and HV history from ``start`` to ``end`` for every covered underlying not
    backfilled yet (``symbols``: only those; ``limit``: at most that many this run)."""

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
