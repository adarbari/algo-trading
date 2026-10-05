"""Descriptions of what a company or fund is about, as an L1 table (``instruments/description``).

Two sources, one table (ADR 0034):

- **Stocks and ADRs** from Massive's ticker overview: one request per ticker, on the free tier
  5 requests a minute. 11k instruments would take ~37 hours, so a run asks for at most
  ``limit`` tickers (default ``[massive] descriptions_per_night``, 100 = ~21 minutes; named
  ``symbols`` are never capped), in priority order: the configured ``priority_symbols`` and
  S&P 500 members, then by liquidity, then the rest (``option_chains.prioritise``). A ticker
  is asked again after ``[massive] descriptions_refresh_days`` (365). A ticker Massive has no
  text for is stored as a marker (no description) and asked again after 30 days.
- **ETFs** from the investment objective in their SEC prospectus (the quarterly Risk/Return
  Summary data sets, ~80 MB each): no per-ticker requests. The last ``[sec_edgar]
  fund_quarters`` completed quarters are read once each (a quarter a finished run already
  read is skipped; one not published yet answers 404 and is tried again the next night); the
  latest filing per fund series wins and a row is written only when it is new or newer.
  ``force`` rereads every quarter (which also picks up funds the SEC ticker map listed late)
  and replaces a stored objective that reads differently, whatever its filing date.

Runs are increments: only rows fetched or changed are stored (``data.reference.descriptions``
reads the union). The run is resumable: tickers already fetched in an unfinished run are
skipped. A refresh that finds no text keeps the stored text.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any

import pandas as pd

from algotrade.core.model.fields import DESCRIPTION_TABLE
from algotrade.data.reference import DESCRIPTION_COLUMNS, instruments, stored_descriptions
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.market.option_chains import Underlying, prioritise
from algotrade_ingestion.tasks.profile.fund_series import extend_fund_map
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "descriptions"
TABLE = DESCRIPTION_TABLE
MASSIVE_TEXT = "massive_overview"  # description_source of a stock's text
FUND_TEXT = "sec_fund_objective"  # description_source of an ETF's investment objective
STOCK_TYPES = ("COMMON_STOCK", "ADR")
ONLY = ("massive", "funds")
CHECKPOINT_EVERY = 25
FUNDS = "funds"  # staging key of the ETF rows
MARKER_RETRY_DAYS = 30  # a ticker with no text (404, a new IPO) is asked again after this
COLUMNS = list(DESCRIPTION_COLUMNS)  # the table's columns, named once by the reader


@dataclass(frozen=True)
class DescriptionSources:
    """The sources the run may use (None: unavailable, with the reason in ``TaskContext``)."""

    overview: Source | None = None  # MassiveOverview
    fund_tickers: Source | None = None  # SecFundTickerMap
    fund_objectives: Source | None = None  # SecFundObjectives
    per_night: int = 100
    refresh_days: int = 365
    fund_quarters: int = 6
    priority_symbols: tuple[str, ...] = ()
    fund_series: Source | None = None  # SecFundSeries: finds the ETFs the ticker map misses


def recent_quarters(session: date, count: int) -> list[str]:
    """The ``count`` calendar quarters that ended before ``session`` as ``2026q3``, oldest first."""
    year, index = session.year, (session.month - 1) // 3
    out: list[str] = []
    for _ in range(max(count, 0)):
        index -= 1
        if index < 0:
            year, index = year - 1, 3
        out.append(f"{year}q{index + 1}")
    return out[::-1]


def _active(reference: pd.DataFrame) -> pd.DataFrame:
    return reference[reference["status"].astype(str).str.upper() == "ACTIVE"]


def _is_etf(frame: pd.DataFrame) -> pd.Series:
    """ETFs: the reference's ``is_etf`` flag or an ETF security type. The one rule for both
    sources, so an instrument is described from exactly one of them."""
    kind = frame["security_type"] == "ETF" if "security_type" in frame.columns else False
    flag = frame["is_etf"].fillna(False).astype(bool) if "is_etf" in frame.columns else False
    return pd.Series(flag | kind, index=frame.index).astype(bool)


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Rows of ``COLUMNS`` as the table stores them (object dtype, ``None`` for gaps)."""
    out = pd.DataFrame(rows, columns=COLUMNS)
    out["total_employees"] = pd.to_numeric(out["total_employees"], errors="coerce").astype("Int64")
    return out.astype(object).where(out.notna(), None)


# ------------------------------------------------------------------------------ stocks


def stock_order(
    ctx: TaskContext,
    reference: pd.DataFrame,
    session: date,
    priority_symbols: Sequence[str],
    symbols: Sequence[str] = (),
) -> list[Underlying]:
    """Active stocks and ADRs (or just ``symbols``) in the order they are asked for."""
    active = _active(reference)
    active = active[active["security_type"].isin(STOCK_TYPES) & ~_is_etf(active)]
    if symbols:
        wanted = {s.upper() for s in symbols}
        active = active[active["symbol"].astype(str).str.upper().isin(wanted)]
    names = [Underlying(str(r.instrument_id), str(r.symbol)) for r in active.itertuples()]
    ordered, _ = prioritise(ctx.reader, session, names, priority_symbols, ctx.configs)
    return ordered


def due_stocks(
    order: Sequence[Underlying],
    stored: pd.DataFrame,
    session: date,
    refresh_days: int,
    force: bool = False,
) -> list[Underlying]:
    """Tickers to ask, in order: never asked first (priority order), then those whose refresh
    slot passed since they were asked (``refresh.due_keys``: once per ``refresh_days``, on a
    slot day spread by key; a ticker with no text only ``MARKER_RETRY_DAYS``), the stalest
    first. ``force``: all, in priority order."""
    if force:
        return list(order)
    own = stored[stored["description_source"] == MASSIVE_TEXT]
    asked: dict[str, date] = dict(zip(own["instrument_id"], own["fetched_on"], strict=True))
    text = set(own[own["description"].notna()]["instrument_id"])
    ids = [u.instrument_id for u in order]
    rank = {i: n for n, i in enumerate(ids)}
    new = {i for i in ids if i not in asked}
    wait = min(refresh_days, MARKER_RETRY_DAYS)
    stale = due_keys([i for i in ids if i in text], asked, session, refresh_days)
    stale += due_keys([i for i in ids if i in asked and i not in text], asked, session, wait)
    stale.sort(key=lambda i: (asked[i], rank[i]))
    by_id = {u.instrument_id: u for u in order}
    return [u for u in order if u.instrument_id in new] + [by_id[i] for i in stale]


def _overview(run: IngestRun, source: Source, u: Underlying, stored: pd.DataFrame) -> str:
    """Ask Massive for one ticker and stage its row (a marker when there is no text)."""
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    row.update(instrument_id=u.instrument_id, symbol=u.symbol, fetched_on=run.session)
    row["description_source"] = MASSIVE_TEXT
    try:
        normalized = run.fetch(source, FetchRequest(u.symbol, u.instrument_id, run.session))
    except NoResponseError:
        status = "NOT_FOUND"  # Massive does not know the ticker
    else:
        found = normalized.parsed["overview"].iloc[0] if normalized is not None else None
        if found is not None:
            row.update({k: found[k] for k in ("description", "homepage_url", "total_employees")})
        status = "OK" if row["description"] else "NO_DESCRIPTION"
    had = stored[stored["instrument_id"] == u.instrument_id]
    if len(had):  # a refresh never drops what we had
        for column in ("description", "homepage_url", "total_employees"):
            old = had.iloc[0][column]
            if pd.isna(row[column]) and not pd.isna(old):
                row[column] = old
                status = "KEPT" if column == "description" else status
    run.stage(TABLE, u.symbol, _frame([row]), source.name)
    return status


# ------------------------------------------------------------------------------ ETFs


def _later(new: Any, old: Any) -> bool:
    """Whether a filing dated ``new`` is later than the stored one (``old``; may be unknown)."""
    return not pd.isna(new) and (pd.isna(old) or bool(old < new))


def fund_rows(
    objectives: Sequence[pd.DataFrame],
    funds: pd.DataFrame,
    etfs: pd.DataFrame,
    stored: pd.DataFrame,
    replace: bool = False,
) -> pd.DataFrame:
    """ETF description rows to store: the latest objective per series (``objectives``, one frame
    per quarter) for every ETF whose ticker is in the fund map (``funds``), when the ETF has no
    objective yet or this one reads differently and is from a later filing (``replace``: from
    any filing, for a forced reread). ``etfs``: ``instrument_id``, ``symbol``. ``fetched_on`` is
    left for the caller."""
    if not objectives:
        return _frame([])
    found = pd.concat(objectives, ignore_index=True)
    found = found.sort_values(["filed", "accn"], na_position="first", kind="stable")
    found = found.drop_duplicates("series_id", keep="last")
    rows = etfs.merge(funds[["symbol", "series_id"]], on="symbol").merge(found, on="series_id")
    rows = rows.sort_values(["filed", "accn"], na_position="first", kind="stable")
    rows = rows.drop_duplicates("instrument_id", keep="last")
    own = stored[stored["description_source"] == FUND_TEXT].set_index("instrument_id")
    out: list[dict[str, Any]] = []
    for r in rows.itertuples(index=False):
        old = own.loc[r.instrument_id] if r.instrument_id in own.index else None
        changed = old is not None and old["description"] != r.objective
        if old is None or (changed and (replace or _later(r.filed, old["filed"]))):
            out.append(
                {
                    "instrument_id": r.instrument_id,
                    "symbol": r.symbol,
                    "description": r.objective,
                    "description_source": FUND_TEXT,
                    "filed": None if pd.isna(r.filed) else r.filed,
                    "accn": r.accn,
                }
            )
    return _frame(out)


def _fund_tickers(run: IngestRun, source: Source, out: list[pd.DataFrame]) -> str:
    normalized = run.fetch(source, FetchRequest("fund_tickers", session_date=run.session))
    if normalized is None:
        raise ValueError("SEC fund ticker map had no rows")
    out.append(normalized.parsed["funds"])
    return f"OK: {len(out[-1])} fund tickers"


def _fund_series(run: IngestRun, source: Source, out: list[pd.DataFrame]) -> str:
    normalized = run.fetch(source, FetchRequest(str(run.session.year), session_date=run.session))
    if normalized is None or normalized.parsed["series"].empty:
        raise ValueError("SEC series / class file had no rows")
    out.append(normalized.parsed["series"])
    return f"OK: {len(out[-1])} share classes"


def _quarter(run: IngestRun, source: Source, quarter: str, out: list[pd.DataFrame]) -> str:
    try:
        normalized = run.fetch(source, FetchRequest(quarter, session_date=run.session))
    except NoResponseError:
        return "NOT_PUBLISHED"  # the SEC publishes a quarter about ten days after it ends
    frame = normalized.parsed["objectives"] if normalized is not None else None
    if frame is None or frame.empty:  # a published file with no objectives is a parse problem
        raise ValueError(f"{quarter}: the data set held no investment objectives")
    out.append(frame)
    return f"OK: {len(frame)} series"


def _quarters_read(ctx: TaskContext) -> set[str]:
    """Quarters a published run (COMPLETE or PARTIAL) read. Never this run's own items: its
    objectives are staged after the loop, so a crashed run that is resumed has not stored them."""
    done: set[str] = set()
    for record in finished_runs(ctx.writer, TASK):
        done |= {k for k, v in record.items.items() if status_label(v) == "OK"}
    return {k.removeprefix("fund:") for k in done if k.startswith("fund:")}


def _funds(
    ctx: TaskContext,
    run: IngestRun,
    sources: DescriptionSources,
    reference: pd.DataFrame,
    stored: pd.DataFrame,
    force: bool,
) -> None:
    """Read the quarters not read yet and stage the ETF rows they change."""
    assert sources.fund_tickers is not None and sources.fund_objectives is not None
    wanted = recent_quarters(run.session, sources.fund_quarters)
    done = set() if force else _quarters_read(ctx)
    todo = [q for q in wanted if q not in done]
    run.stats.update(fund_quarters=wanted, fund_quarters_todo=todo)
    if not todo:
        return
    funds: list[pd.DataFrame] = []
    status = run.attempt("fund_tickers", partial(_fund_tickers, run, sources.fund_tickers, funds))
    if status_label(status) != "OK":
        return  # the failure is on the run; the quarters are read next time
    objectives: list[pd.DataFrame] = []
    for quarter in todo:
        run.attempt(
            f"fund:{quarter}", partial(_quarter, run, sources.fund_objectives, quarter, objectives)
        )
        run.checkpoint()
    active = _active(reference)
    etfs = active[_is_etf(active)].reindex(columns=["instrument_id", "symbol", "name"])
    etfs = etfs.fillna("").astype(str)
    fund_map = funds[0]
    if sources.fund_series is not None:  # without it the ticker map alone decides (as before)
        series: list[pd.DataFrame] = []
        found = run.attempt("fund_series", partial(_fund_series, run, sources.fund_series, series))
        if status_label(found) == "OK":
            fund_map, matched = extend_fund_map(fund_map, series[0], etfs)
            run.stats.update(fund_matched=matched)
    rows = fund_rows(objectives, fund_map, etfs, stored, replace=force)
    run.stats.update(fund_etfs=len(etfs), fund_rows=len(rows))
    if not rows.empty:
        rows["fetched_on"] = run.session
        run.stage(TABLE, FUNDS, rows, sources.fund_objectives.name)


# ------------------------------------------------------------------------------ the task


def _why(ctx: TaskContext, *names: str) -> str:
    return "; ".join(sorted({ctx.unavailable.get(n, f"{n} is not configured") for n in names}))


def _stocks(
    run: IngestRun,
    ctx: TaskContext,
    sources: DescriptionSources,
    reference: pd.DataFrame,
    stored: pd.DataFrame,
    symbols: Sequence[str],
    cap: int | None,
    force: bool,
) -> None:
    if sources.overview is None:
        run.stats["massive"] = "skipped: " + _why(ctx, "massive_overview")
        return
    order = stock_order(ctx, reference, run.session, sources.priority_symbols, symbols)
    due = due_stocks(order, stored, run.session, sources.refresh_days, force or bool(symbols))
    todo = due if cap is None else due[: max(cap, 0)]
    for i, u in enumerate(todo, start=1):
        if u.symbol in run.items:
            continue  # fetched before a resume
        run.attempt(u.symbol, partial(_overview, run, sources.overview, u, stored))
        if i % CHECKPOINT_EVERY == 0:
            run.checkpoint()
    run.stats.update(
        stocks=len(order), due=len(due), requested=len(todo), deferred_by_cap=len(due) - len(todo)
    )


def ingest_descriptions(
    ctx: TaskContext,
    sources: DescriptionSources,
    session: date,
    *,
    only: str | None = None,
    limit: int | None = None,
    symbols: Sequence[str] = (),
    force: bool = False,
) -> RunRecord:
    """Describe stocks (Massive, at most ``limit`` tickers, default the per-night cap) and ETFs
    (SEC prospectuses). ``only``: ``massive`` or ``funds``. ``symbols`` names the stocks to ask
    (always asked, never capped by the nightly cap) and skips the ETFs (a quarter read for a few
    tickers must not count as read). A forced or named run does not resume an earlier record:
    what it asks for is asked."""
    if only is not None and only not in ONLY:
        raise ValueError(f"only must be one of {ONLY}, got {only!r}")
    reference = instruments(ctx.reader, session)
    stored = stored_descriptions(ctx.reader)
    cap = None if symbols else (sources.per_night if limit is None else limit)
    with IngestRun(ctx, TASK, session, resume=not (symbols or force)) as run:
        if only != "funds":
            _stocks(run, ctx, sources, reference, stored, symbols, cap, force)
        if only != "massive" and not symbols:
            if sources.fund_tickers is None or sources.fund_objectives is None:
                reason = _why(ctx, "sec_fund_tickers", "sec_fund_objectives")
                run.stats["funds"] = f"skipped: {reason}"
            else:
                _funds(ctx, run, sources, reference, stored, force)
        rows = run.publish(TABLE)
        failed = run.failures()
        run.stats.update(
            counts=run.counts(), failed=failed[:20], failed_count=len(failed), rows=rows
        )
    return run.record
