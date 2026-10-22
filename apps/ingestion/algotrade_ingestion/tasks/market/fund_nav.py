"""Daily NAV of closed-end funds from Tiingo's Nasdaq MFQS series -> ``events/fund_nav`` (edge
build D5).

``algotrade-ingest run fund-nav`` maps every closed-end fund of the reference snapshot to its NAV
symbol ``X<ticker>X`` and fetches one request per fund (``tiingo/nav.py``), the same endpoint
and pace as ``bars-history``. Rows are staged per fund and published together when the run ends
(ADR 0022), one partition per NAV date (``session_date`` = the NAV date), merged on
(instrument, series, date).

- **Funds** (``data.reference.is_closed_end``, also the read side's test for skipping this table
  for other instruments): the reference snapshot's ``security_type = CEF`` (Massive's
  ``FUND``) plus the common stocks whose name says ``Closed End Fund`` (the vendor types the
  Calamos funds as stocks). The id is the fund's own ``instrument_id`` (ADR 0018), never built
  from the NAV symbol, which is not an instrument. A fund is MAPPED only when Tiingo's listing holds
  ``X<ticker>X`` under ``NMFQS``; the others (no NAV published: a fund under $75 M, a fund the
  vendor does not carry) are counted and named in ``stats["unmapped"]``. A NAV symbol whose
  series ended before the window is skipped (``ended``, from the listing's last day). BDCs are
  not covered: their NAV is quarterly (10-Q ``NetAssetValuePerShare``, SEC company facts), no
  MFQS symbol exists for the business development companies checked (ARCC, MAIN, OBDC, FSK,
  HTGC, GBDC, TSLX, BXSL, PSEC, GAIN), and the reference holds no BDC type.
- **Windows**: ``--from`` / ``--to`` (``--to`` defaults to the session). Without ``--from`` the
  window is the last ``LOOKBACK_DAYS`` calendar days (the nightly increment, overlapping so a
  late or restated NAV is caught); the one-off history is ``--from 2004-01-01``. A request starts
  no earlier than the series' own first day, and a row already stored with the same NAV is skipped
  (``already_stored_rows``); a different NAV for a stored date is written as a later version.
- **known_from** is the next session after the NAV date (the NAV is struck after the close and
  the vendor shows it the next day), the same for the nightly fetch and the 2004 backfill;
  ``knowledge_ts`` is the real fetch (publish) instant. A later restatement of a stored NAV
  replaces the row (merge mode), so it takes ``known_from = max(next session, the session
  of the fetch)``: an as-of read before that session never sees it, and reads before it see no
  NAV for that date (the replaced original is not served: the cost of the one-row key).
- **Budget**: each fund is one Tiingo symbol (item ``nav:<id>``) counted with ``bars-history``'s
  against ``[tiingo] monthly_symbol_budget`` (``tiingo_budget``); a run fetches no more than the
  month's remainder (``stats`` carry ``month_budget``, ``month_used``, ``month_remaining``).
  A fund fetched again in the month is the same symbol, so the nightly increment adds ~300
  symbols a month, once. On the free tier (50 requests an hour, 500 symbols a month) that is 6
  hours a run at 72 s a request and 60% of the month's symbols: so the task is in NO workflow;
  the owner runs it (detached, README "Long runs") weekly or monthly with ``--from`` the last
  stored date.
- **Resumable**, like ``bars-history``: a fund an earlier finished run fetched for the window
  is skipped (``--force``: fetch it again); an interrupted run resumes from its staging.
  ``STOP_AFTER_FAILED`` unanswered funds in a row end the run.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache, partial
from typing import cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date, next_session
from algotrade.data.reference import instruments, is_closed_end
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

TASK = "fund_nav"
TABLE = "events/fund_nav"
LOOKBACK_DAYS = 10  # the nightly window when --from is not given
DONE = ("OK", "NO_DATA")
UNMAPPED_SHOWN = 50  # unmapped funds named in the stats (the rest are counted)
CHECKPOINT_EVERY = 5
STOP_AFTER_FAILED = 3


@dataclass(frozen=True)
class Fund:
    """A closed-end fund with its NAV symbol and the dates Tiingo has that series for."""

    symbol: str
    instrument_id: str
    nav_symbol: str
    start: date
    end: date | None  # the last day Tiingo has the series (None: the file gives none)


def nav_symbol(ticker: str) -> str:
    """``PHK`` -> ``XPHKX`` (Nasdaq MFQS's rule); a share class keeps Tiingo's hyphen."""
    return f"X{ticker.strip().upper().replace('.', '-')}X"


def map_funds(
    reference: pd.DataFrame, nav_tickers: pd.DataFrame, requested: Collection[str] = ()
) -> tuple[list[Fund], list[str]]:
    """-> (funds with a NAV series in Tiingo's listing, tickers of the funds without one).
    ``requested`` (tickers) narrows when not empty."""
    wanted = {r.strip().upper() for r in requested}
    funds = reference[is_closed_end(reference)].drop_duplicates("instrument_id")
    series = nav_tickers.set_index("ticker")
    mapped: list[Fund] = []
    unmapped: list[str] = []
    for row in funds.sort_values("symbol").itertuples():
        ticker = str(row.symbol).upper()
        if wanted and ticker not in wanted:
            continue
        symbol = nav_symbol(ticker)
        if symbol not in series.index:
            unmapped.append(ticker)
            continue
        found = series.loc[symbol]
        last = found["last_nav"]
        end: date | None = None if pd.isna(last) else cast(date, last)
        mapped.append(
            Fund(ticker, str(row.instrument_id), symbol, cast(date, found["first_nav"]), end)
        )
    return mapped, unmapped


@cache
def _known_from(day: date) -> date:
    return next_session(day)


def _learned_on(run: IngestRun) -> date:
    """The first session strictly after the exchange date of the run's clock: the same rule as a
    fresh NAV's ``known_from`` (the next session), whatever ``--to`` says (a past ``--to`` is
    not a past fetch)."""
    return next_session(exchange_date(run.clock()))


def nav_rows(
    nav: pd.DataFrame,
    fund: Fund,
    first: date,
    last: date,
    stored: dict[pd.Timestamp, float],
    session: date,
) -> tuple[pd.DataFrame, int, int]:
    """Fetched NAV rows -> (rows to store, rows clipped outside ``first..last``, rows already
    stored with the same NAV). ``stored``: this fund's stored NAV by ``ts``. A NAV that differs
    from a stored one is a restatement: merge mode replaces the original row (the key has no
    ``knowledge_ts``), so its ``known_from`` is ``max(next session, session)`` with ``session``
    the one the run learned it on (``_learned_on``: the fetch, never ``--to``), never a date before
    it was learned."""
    days = nav["ts"].dt.date
    inside = (days >= first) & (days <= last)
    kept = nav[inside]
    same = [
        t in stored and abs(stored[t] - v) <= 1e-9
        for t, v in zip(kept["ts"], kept["nav"], strict=True)
    ]
    fresh = kept[[not s for s in same]]
    days = fresh["ts"].dt.date
    known = days.map(_known_from)
    restated = fresh["ts"].isin(list(stored))
    known = known.where(~restated, known.map(lambda d: max(d, session)))
    rows = fresh.drop(columns="instrument_id", errors="ignore").assign(
        instrument_id=fund.instrument_id, known_from=known, session_date=days
    )
    return rows.reset_index(drop=True), int((~inside).sum()), int(sum(same))


def nav_done(runs: Sequence[RunRecord], since: date, until: date) -> set[str]:
    """Instrument ids an earlier finished run fetched for ``since..until`` or a wider window."""
    done: set[str] = set()
    for record in runs:
        for key, status in record.items.items():
            label, _, window = status.partition(": ")
            first, _, last = window.partition("..")
            if (
                key.startswith("nav:")
                and label in DONE
                and first <= since.isoformat()
                and last >= until.isoformat()
            ):
                done.add(key.removeprefix("nav:"))
    return done


def _window(since: date, until: date) -> str:
    return f"{since.isoformat()}..{until.isoformat()}"


def _fetch_fund(
    run: IngestRun,
    source: Source,
    fund: Fund,
    since: date,
    until: date,
    stored: dict[str, dict[pd.Timestamp, float]],
) -> str:
    first = max(since, fund.start)
    last = until  # the vendor sends nothing later than its last NAV
    done = f"NO_DATA: {_window(since, until)}"
    key = f"{fund.nav_symbol}:{first.isoformat()}:{last.isoformat()}"
    try:
        normalized = run.fetch(
            source,
            FetchRequest(key, fund.instrument_id, until),
            raw_key=f"{fund.nav_symbol}__{since.isoformat()}",
        )
    except NoResponseError:  # 404: Tiingo does not carry the symbol
        return done
    if normalized is None or normalized.tables[TABLE].empty:
        return done
    stats = run.stats
    stats["invalid_rows"] = stats.get("invalid_rows", 0) + int(normalized.notes["invalid_rows"])
    rows, clipped, same = nav_rows(
        normalized.tables[TABLE],
        fund,
        first,
        last,
        stored.get(fund.instrument_id, {}),
        _learned_on(run),
    )
    stats["clipped_rows"] = stats.get("clipped_rows", 0) + clipped
    stats["already_stored_rows"] = stats.get("already_stored_rows", 0) + same
    if not rows.empty:
        run.stage_sessions(TABLE, f"nav_{fund.instrument_id}", rows, source.name)
    return f"OK: {_window(since, until)}"


def _stored_nav(run: IngestRun, since: date, until: date) -> dict[str, dict[pd.Timestamp, float]]:
    """The stored NAV by fund and ``ts`` over the window (the partitions are the NAV dates)."""
    out: dict[str, dict[pd.Timestamp, float]] = {}
    for day in (d for d in run.reader.dates(TABLE) if since <= d <= until):
        frame = run.reader.table(TABLE, day)
        if frame is None:
            continue
        for fund, ts, nav in zip(frame["instrument_id"], frame["ts"], frame["nav"], strict=True):
            out.setdefault(str(fund), {})[pd.Timestamp(ts)] = float(nav)
    return out


def ingest_fund_nav(
    ctx: TaskContext,
    nav: Source,
    tickers: Source,
    until: date,
    since: date | None = None,
    requested: Sequence[str] = (),
    force: bool = False,
    limit: int | None = None,
) -> RunRecord:
    """The NAV of every closed-end fund (or the ``requested`` tickers) over ``since..until``
    (default: the last ``LOOKBACK_DAYS``); ``limit``: fetch at most that many funds this run;
    ``force``: also the funds an earlier run fetched for the window. Never more than the
    month's remaining symbol budget."""
    since = since or until - timedelta(days=LOOKBACK_DAYS)
    if until < since:
        raise ValueError(f"--to {until} is before --from {since}")
    with IngestRun(ctx, TASK, until, resume=True) as run:
        try:
            listing = run.fetch(tickers, FetchRequest("nav_tickers", session_date=until))
        except NoResponseError as error:
            run.failed(str(error))
            return run.record
        assert listing is not None
        reference = instruments(run.reader, until)
        funds, unmapped = map_funds(reference, listing.parsed["nav_tickers"], requested)
        live = [f for f in funds if f.end is None or f.end >= since]
        done: Collection[str] = (
            set() if force else nav_done(finished_runs(run.writer, TASK), since, until)
        )
        pending = [
            f
            for f in live
            if f.instrument_id not in done and f"nav:{f.instrument_id}" not in run.items
        ]
        budget = ctx.settings.tiingo_monthly_symbol_budget
        remaining = max(0, budget - len(month_symbols(run)))
        todo = pending[: remaining if limit is None else min(remaining, max(0, limit))]
        stored = _stored_nav(run, since, until)
        failed_in_a_row = 0
        for i, fund in enumerate(todo, 1):
            fetch = partial(_fetch_fund, run, nav, fund, since, until, stored)
            status = run.attempt(f"nav:{fund.instrument_id}", fetch)
            failed_in_a_row = failed_in_a_row + 1 if status_label(status) == FETCH_ERROR else 0
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
            if failed_in_a_row >= STOP_AFTER_FAILED:
                run.partial(f"stopped: Tiingo failed {failed_in_a_row} funds in a row ({status})")
                break
        published = run.publish_sessions(TABLE)
        statuses = [status_label(run.items.get(f"nav:{f.instrument_id}", "")) for f in todo]
        left = len(pending) - sum(1 for s in statuses if s in DONE)
        used = len(month_symbols(run))
        run.stats.update(
            window=_window(since, until),
            licence=ctx.settings.tiingo_licence,  # the rows' terms, in the run record
            funds=int(is_closed_end(reference).sum()),
            mapped=len(funds),
            unmapped_count=len(unmapped),
            unmapped=unmapped[:UNMAPPED_SHOWN],
            ended=len(funds) - len(live),
            skipped_done=len(live) - len(pending),
            fetched=len(todo),
            rows=sum(published.values()),
            sessions_written=len(published),
            latest_nav=max(published).isoformat() if published else None,
            month_budget=budget,
            month_used=used,
            month_remaining=max(0, budget - used),
            pending=left,
        )
        run.stats["items"] = run.counts()
    return run.record
