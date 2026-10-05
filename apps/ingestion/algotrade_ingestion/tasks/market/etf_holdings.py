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
  quarterly, so they are never read more often than ``cadence_days``); ``limit`` caps a run (the
  nightly passes ``[etf_holdings] per_night``, so its first runs read a slice, not every fund);
- the fund's lines are ranked by the size of their weight, the largest ``[etf_holdings]
  keep_top`` are kept, and every row carries the file's number of positions (cash, futures and
  FX lines are stored but not counted). A line's ticker resolves to an instrument id through
  ``SymbolResolver`` when the issuer says it is a U.S. listing; lines with no ticker (SEC N-PORT)
  are linked through CUSIPs of equity lines other issuers printed beside a ticker that resolved
  (a foreign line never feeds that map); the rest keep their name only;
- a new read replaces a fund's rows only if it passes sanity checks against the previous read
  (``sanity_problem``): weights add up to about 100% (not for leveraged, inverse and N-PORT
  funds), the number of positions has not collapsed, the as-of date has not gone back. A failed
  check is a FAILED item (the run is PARTIAL) and last read's rows stay.

Per-fund rows are staged, then published as one partition; a crashed run resumes.
"""

from collections.abc import Mapping, Sequence
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
from algotrade_sources.framework.holdings import is_position

TASK = "etf_holdings"
TABLE = "holdings/etf"
DIRECTORY = "directory:"  # item key prefix of an issuer's fund list
NO_FILE = "NO_FILE"
EMPTY = "EMPTY"
REJECTED = "FAILED"  # item status of a read that failed its sanity checks
CHECKPOINT_EVERY = 25
ETF = "ETF"
WEIGHT_SUM_BAND = 0.10  # a fund's weights add up to 100% within this (not geared funds)
MIN_COUNT_RATIO = 0.5  # a read with fewer positions than this share of the last one is rejected


@dataclass(frozen=True)
class HoldingsSources:
    issuers: Sequence[HoldingsSource]  # priority order: the first that lists a fund reads it
    refresh_days: int = 7
    keep_top: int = 100  # holdings stored per fund; 0 keeps all
    fallback_scope: str = "optionable"  # funds a scope-limited issuer (N-PORT) is read for
    check_weight_sum: bool = True  # reject weights far from 100% (off in tests: trimmed files)


@dataclass(frozen=True)
class Previous:
    """What the store holds for a fund: the issuer's date and number of positions."""

    as_of: date
    count: int


def active_etfs(reference: pd.DataFrame) -> pd.DataFrame:
    """``instrument_id``, ``symbol``, ``optionable``, ``geared`` (leveraged or inverse) of the
    active ETFs (not ETNs) of a reference snapshot."""
    kind = reference["security_type"].astype(str).str.upper() == ETF
    active = reference["status"].astype(str).str.upper() == "ACTIVE"
    out = reference.loc[kind & active, ["instrument_id", "symbol"]].astype(str)

    def flag(column: str) -> pd.Series:
        values = reference[column] if column in reference.columns else False
        return pd.Series(values, index=reference.index).eq(True)

    out["optionable"] = flag("optionable")
    out["geared"] = flag("is_leveraged") | flag("is_inverse")
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


def _read_before(
    ctx: TaskContext, etfs: pd.DataFrame, session: date
) -> tuple[dict[str, date], dict[str, Previous]]:
    """-> (symbol -> the latest session a fund was read: stored holdings, or a finished run that
    found the issuer had no file for it, so it is retried once a window, not nightly;
    symbol -> what the store holds for it)."""
    read: dict[str, date] = {}
    previous: dict[str, Previous] = {}
    ids = dict(zip(etfs["instrument_id"], etfs["symbol"], strict=True))
    status = holdings_status(ctx.reader, session)
    columns = (status[c] for c in ("instrument_id", "as_of", "holdings_count", "fetched_on"))
    for iid, as_of, count, fetched in zip(*columns, strict=True):
        if iid in ids:
            read[ids[iid]] = fetched
            previous[ids[iid]] = Previous(as_of, int(count))
    for record in finished_runs(ctx.writer, TASK):
        for symbol, item in record.items.items():
            if item.split(":", 1)[0] in (NO_FILE, EMPTY) and record.session_date <= session:
                read[symbol] = max(read.get(symbol, record.session_date), record.session_date)
    return read, previous


def sanity_problem(
    holdings: pd.DataFrame,
    as_of: date,
    previous: Previous | None,
    geared: bool,
    check_sum: bool,
) -> str | None:
    """Why a fund's new read must not replace what is stored (``None``: it can).

    The weights of all lines add up to about 100% (``check_sum``; not for leveraged and inverse
    funds, whose swap lines do not, nor N-PORT funds, which report net assets differently); the
    number of positions did not collapse and the as-of date did not go back against the previous
    read. A truncated file or a changed layout that still parses fails here."""
    if check_sum and not geared:
        total = float(holdings["weight"].sum())
        if abs(total - 1.0) > WEIGHT_SUM_BAND:
            return f"weights add up to {total:.1%}, not about 100%"
    if previous is None:
        return None
    if as_of < previous.as_of:
        return f"as of {as_of}, older than the stored {previous.as_of}"
    count = positions(holdings)
    if previous.count >= 10 and count < MIN_COUNT_RATIO * previous.count:
        return f"{count} positions, was {previous.count}"
    return None


def positions(holdings: pd.DataFrame) -> int:
    """The number of lines that are positions in a security (not cash, futures or FX)."""
    return int(holdings["asset_class"].map(is_position).sum())


def fund_frame(
    iid: str,
    symbol: str,
    as_of: date,
    holdings: pd.DataFrame,
    keep_top: int,
    resolver: SymbolResolver,
    cusips: Mapping[str, str],
) -> pd.DataFrame:
    """The stored rows of one fund: ranked, trimmed, holdings linked to instrument ids."""
    count = positions(holdings)
    top = (holdings.head(keep_top) if keep_top > 0 else holdings).reset_index(drop=True)
    tickers = [None if pd.isna(t) else str(t) for t in top["holding_symbol"]]
    listed = [bool(flag) for flag in top["us_listed"]]
    for i, identifier in enumerate(top["identifier"]):
        # No ticker: the one printed beside the same CUSIP by an issuer whose line resolved to
        # the universe. Only equity lines are looked up (a bond's CUSIP is never in the map).
        bridged = None
        if tickers[i] is None and top["asset_class"].iloc[i] == "Equity":
            bridged = cusips.get(cusip_of(identifier) or "")
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
            "filed": top["filed"],
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


@dataclass
class FundContext:
    """What reading one fund needs besides the fund: the run's settings and shared state."""

    sources: HoldingsSources
    resolver: SymbolResolver
    cusips: dict[str, str]  # grows as daily-file funds are read, for the N-PORT funds after
    previous: Mapping[str, Previous]
    geared: set[str]


def _fund(run: IngestRun, source: HoldingsSource, iid: str, symbol: str, c: FundContext) -> str:
    """Read one fund through its issuer and stage its rows (a read that fails the sanity checks
    is a FAILED item and stages nothing, so the fund keeps what it had)."""
    try:
        normalized = run.fetch(source, FetchRequest(symbol, iid, run.session))
    except NoResponseError:
        return NO_FILE
    if normalized is None or normalized.session_date is None:
        return EMPTY
    holdings = normalized.parsed["holdings"]
    problem = sanity_problem(
        holdings,
        normalized.session_date,
        c.previous.get(symbol),
        symbol in c.geared,
        check_sum=c.sources.check_weight_sum and not source.scope_limited,
    )
    if problem is not None:
        return f"{REJECTED}: {problem}"
    frame = fund_frame(
        iid, symbol, normalized.session_date, holdings, c.sources.keep_top, c.resolver, c.cusips
    )
    if not source.scope_limited:  # only issuers that print tickers feed the CUSIP bridge
        known = frame[frame["holding_id"].notna() & frame["identifier"].notna()]
        for identifier, ticker, kind in zip(
            known["identifier"], known["holding_symbol"], known["asset_class"], strict=True
        ):
            cusip = cusip_of(identifier)
            if cusip is not None and kind == "Equity":
                c.cusips[cusip] = str(ticker)
    run.stage(TABLE, symbol, frame, source.name)
    return f"OK: {len(holdings)} lines as of {normalized.session_date}"


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
        read, previous = _read_before(ctx, etfs, session)
        due: list[str] = []
        for source in sources.issuers:  # per issuer: its own cadence (N-PORT is quarterly)
            mine = [s for s, owner in covered.items() if owner is source]
            window = max(sources.refresh_days, source.cadence_days)
            due += due_keys(mine, read, session, window, force)
        todo = due if limit is None else due[: max(limit, 0)]
        shared = FundContext(
            sources,
            run.resolver(),
            known_cusips(run.reader, session, [s.name for s in sources.issuers if s.scope_limited]),
            previous,
            set(etfs.loc[etfs["geared"], "symbol"]),
        )
        pending = [s for s in todo if s not in run.items]  # the rest were read by the run resumed
        for done, symbol in enumerate(pending, start=1):
            run.attempt(symbol, partial(_fund, run, covered[symbol], ids[symbol], symbol, shared))
            if done % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        rows = run.publish(TABLE)
        funds = {k: v for k, v in run.items.items() if not k.startswith(DIRECTORY)}
        run.stats.update(
            etfs=len(ids),
            covered={s.name: sum(1 for o in covered.values() if o is s) for s in sources.issuers},
            uncovered=len(ids) - len(covered) - len(out_of_scope),
            out_of_scope=len(out_of_scope),
            due=len(due),
            requested=len(todo),
            read=sum(1 for v in funds.values() if v.startswith("OK")),
            no_file=sum(1 for v in funds.values() if v.startswith((NO_FILE, EMPTY))),
            rejected=sum(1 for v in funds.values() if v.startswith(REJECTED)),
            failed=run.failures()[:20],
            failed_count=len(run.failures()),
            deferred_by_limit=len(due) - len(todo),
            rows=rows,
            statuses=run.counts(),
        )
    return run.record
