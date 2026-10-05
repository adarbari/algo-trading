"""What each ETF holds -> ``holdings/etf`` (ADR 0035): one row per fund x holding x as-of date.

Issuers are adapters behind one shape (``HoldingsSource``), tried in priority order: the first
that lists a fund publishes it (State Street's and iShares' daily files, then SEC N-PORT for the
rest). Per run:

- each issuer's directory says which funds it publishes; the funds are the active ETFs of the
  reference snapshot (security type ``ETF``) that some issuer lists. N-PORT is scope-limited
  (``[etf_holdings] fallback_scope``): by default only for optionable ETFs no daily file covers;
- a fund is due when it was never read, or past its refresh slot (``[etf_holdings]
  refresh_days``, spread over the window by ticker; funds an issuer lists but has no file for
  count as read, so they are retried once a window, not nightly; SEC N-PORT funds report
  quarterly, so they are never read more often than ``cadence_days``); ``limit`` caps a run;
- the fund's lines are ranked by weight, the largest ``[etf_holdings] keep_top`` are kept, and
  every row carries the file's total line count. A line's ticker resolves to an instrument id
  through ``SymbolResolver`` when the issuer says it is a U.S. listing; lines with no ticker
  (SEC N-PORT) are linked through the CUSIPs the other issuers printed beside tickers; the rest
  keep their name only (cash, futures, bonds, foreign lines).

Per-fund rows are staged, then published as one partition; a crashed run resumes.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

import pandas as pd

from algotrade.data.funds.holdings import cusip_of, holdings_status, known_cusips
from algotrade.data.reference import instruments
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
)
from algotrade_sources.framework.base import FetchRequest, HoldingsSource

TASK = "etf_holdings"
TABLE = "holdings/etf"
DIRECTORY = "directory:"  # item key prefix of an issuer's fund list
NO_FILE = "NO_FILE"
EMPTY = "EMPTY"
CHECKPOINT_EVERY = 25
ETF = "ETF"


@dataclass(frozen=True)
class HoldingsSources:
    issuers: Sequence[HoldingsSource]  # priority order: the first that lists a fund reads it
    refresh_days: int = 7
    keep_top: int = 100  # holdings stored per fund; 0 keeps all
    fallback_scope: str = "optionable"  # funds a scope-limited issuer (N-PORT) is read for


def active_etfs(reference: pd.DataFrame) -> pd.DataFrame:
    """``instrument_id``, ``symbol``, ``optionable`` of the active ETFs (not ETNs) of a
    reference snapshot."""
    kind = reference["security_type"].astype(str).str.upper() == ETF
    active = reference["status"].astype(str).str.upper() == "ACTIVE"
    out = reference.loc[kind & active, ["instrument_id", "symbol"]].astype(str)
    optionable = reference["optionable"] if "optionable" in reference.columns else False
    out["optionable"] = pd.Series(optionable, index=reference.index).fillna(False).astype(bool)
    return out.reset_index(drop=True)


def _wanted(symbol: str, optionable: set[str], sources: HoldingsSources) -> bool:
    """Whether a scope-limited issuer is read for ``symbol`` (``fallback_scope``)."""
    if sources.fallback_scope == "all":
        return True
    return sources.fallback_scope == "optionable" and symbol in optionable


def _directory(run: IngestRun, source: HoldingsSource, listed: dict[str, set[str]]) -> str:
    request = FetchRequest(source.directory_key, session_date=run.session)
    normalized = run.fetch(source, request)
    funds = set() if normalized is None else set(normalized.parsed["funds"]["symbol"])
    listed[source.name] = funds
    return f"OK: {len(funds)} funds"


def assign(
    symbols: Sequence[str], issuers: Sequence[HoldingsSource], listed: dict[str, set[str]]
) -> dict[str, HoldingsSource]:
    """symbol -> the first issuer (in priority order) whose directory lists it."""
    out: dict[str, HoldingsSource] = {}
    for symbol in symbols:
        for source in issuers:
            if symbol in listed.get(source.name, ()):
                out[symbol] = source
                break
    return out


def _read_before(ctx: TaskContext, etfs: pd.DataFrame, session: date) -> dict[str, date]:
    """symbol -> the latest session a fund was read: stored holdings, or a finished run that
    found the issuer had no file for it (so it is retried once a window, not nightly)."""
    read: dict[str, date] = {}
    ids = dict(zip(etfs["instrument_id"], etfs["symbol"], strict=True))
    status = holdings_status(ctx.reader, session)
    for iid, fetched in zip(status["instrument_id"], status["fetched_on"], strict=True):
        if iid in ids:
            read[ids[iid]] = fetched
    for record in finished_runs(ctx.writer, TASK):
        for symbol, item in record.items.items():
            if item.split(":", 1)[0] in (NO_FILE, EMPTY) and record.session_date <= session:
                read[symbol] = max(read.get(symbol, record.session_date), record.session_date)
    return read


def fund_frame(
    iid: str,
    symbol: str,
    as_of: date,
    holdings: pd.DataFrame,
    keep_top: int,
    resolver: SymbolResolver,
    cusips: dict[str, str],
) -> pd.DataFrame:
    """The stored rows of one fund: ranked, trimmed, holdings linked to instrument ids."""
    count = len(holdings)
    top = (holdings.head(keep_top) if keep_top > 0 else holdings).reset_index(drop=True)
    tickers = [None if pd.isna(t) else str(t) for t in top["holding_symbol"]]
    listed = [bool(flag) for flag in top["us_listed"]]
    for i, identifier in enumerate(top["identifier"]):  # no ticker: the one other issuers printed
        bridged = cusips.get(cusip_of(identifier) or "") if tickers[i] is None else None
        if bridged is not None:
            tickers[i], listed[i] = bridged, True
    linked = [
        resolver.id_for(t) if (ok and t is not None and resolver.knows(t)) else None
        for t, ok in zip(tickers, listed, strict=True)
    ]
    return pd.DataFrame(
        {
            "instrument_id": iid,
            "symbol": symbol,
            "as_of": as_of,
            "rank": range(1, len(top) + 1),
            "holding_symbol": tickers,
            "holding_id": linked,
            "holding_name": top["holding_name"],
            "weight": top["weight"],
            "asset_class": top["asset_class"],
            "sector": top["sector"],
            "shares": top["shares"],
            "identifier": top["identifier"],
            "holdings_count": count,
        }
    )


def _fund(
    run: IngestRun,
    source: HoldingsSource,
    iid: str,
    symbol: str,
    sources: HoldingsSources,
    resolver: SymbolResolver,
    cusips: dict[str, str],
) -> str:
    """Read one fund through its issuer and stage its rows (``cusips`` grows as it goes)."""
    try:
        normalized = run.fetch(source, FetchRequest(symbol, iid, run.session))
    except NoResponseError:
        return NO_FILE
    if normalized is None or normalized.session_date is None:
        return EMPTY
    holdings = normalized.parsed["holdings"]
    frame = fund_frame(
        iid, symbol, normalized.session_date, holdings, sources.keep_top, resolver, cusips
    )
    known = frame[frame["holding_symbol"].notna() & frame["identifier"].notna()]
    for identifier, ticker in zip(known["identifier"], known["holding_symbol"], strict=True):
        cusip = cusip_of(identifier)
        if cusip is not None:
            cusips[cusip] = str(ticker)  # later funds of this run (N-PORT) link through it
    run.stage(TABLE, symbol, frame, source.name)
    return f"OK: {len(holdings)} holdings as of {normalized.session_date}"


def ingest_etf_holdings(
    ctx: TaskContext,
    sources: HoldingsSources,
    session: date,
    force: bool = False,
    limit: int | None = None,
    only: Sequence[str] = (),
) -> RunRecord:
    """Read the due ETFs' holdings from their issuers (``only``: just these tickers)."""
    etfs = active_etfs(instruments(ctx.reader, session))
    if only:
        etfs = etfs[etfs["symbol"].isin([s.upper() for s in only])]
    ids = dict(zip(etfs["symbol"], etfs["instrument_id"], strict=True))
    with IngestRun(ctx, TASK, session, resume=True) as run:
        listed: dict[str, set[str]] = {}
        for source in sources.issuers:
            run.attempt(DIRECTORY + source.name, partial(_directory, run, source, listed))
        covered = assign(sorted(ids), sources.issuers, listed)
        optionable = set(etfs.loc[etfs["optionable"], "symbol"])
        out_of_scope = {
            s for s, o in covered.items() if o.scope_limited and not _wanted(s, optionable, sources)
        }
        covered = {s: o for s, o in covered.items() if s not in out_of_scope}
        read = _read_before(ctx, etfs, session)
        due: list[str] = []
        for source in sources.issuers:  # per issuer: its own cadence (N-PORT is quarterly)
            mine = [s for s, owner in covered.items() if owner is source]
            window = max(sources.refresh_days, source.cadence_days)
            due += due_keys(mine, read, session, window, force)
        todo = due if limit is None else due[: max(limit, 0)]
        resolver = run.resolver()
        cusips = known_cusips(run.reader, session)
        pending = [s for s in todo if s not in run.items]  # the rest were read by the run resumed
        for done, symbol in enumerate(pending, start=1):
            fund = partial(
                _fund, run, covered[symbol], ids[symbol], symbol, sources, resolver, cusips
            )
            run.attempt(symbol, fund)
            if done % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        rows = run.publish(TABLE)
        funds = {k: v for k, v in run.items.items() if not k.startswith(DIRECTORY)}
        counts = run.counts()
        run.stats.update(
            etfs=len(ids),
            covered={s.name: sum(1 for o in covered.values() if o is s) for s in sources.issuers},
            uncovered=len(ids) - len(covered) - len(out_of_scope),
            out_of_scope=len(out_of_scope),
            due=len(due),
            requested=len(todo),
            read=sum(1 for v in funds.values() if v.startswith("OK")),
            no_file=sum(1 for v in funds.values() if v.startswith((NO_FILE, EMPTY))),
            failed=run.failures()[:20],
            failed_count=len(run.failures()),
            deferred_by_limit=len(due) - len(todo),
            rows=rows,
            statuses=counts,
        )
    return run.record
