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
  quarterly, so they are never read more often than ``cadence_days``). ONE list orders every due
  fund across issuers (never read first, then the oldest read first, issuer priority breaking
  ties, ``plan_due``), and only then is ``limit`` applied: the nightly passes ``[etf_holdings]
  per_night``, so a cap can slow the weekly funds down but never starves an issuer;
- the fund's lines are ranked by the size of their weight, the largest ``[etf_holdings]
  keep_top`` are kept, and every row carries the file's number of positions (cash, futures and
  FX lines are stored but not counted). A line's ticker resolves to an instrument id through
  ``SymbolResolver`` when the issuer says it is a U.S. listing; lines with no ticker (SEC N-PORT)
  take the instrument of the same CUSIP on an equity line another issuer printed with a ticker
  that resolved when it was stored (a foreign line never feeds that map); the rest keep their
  name only;
- a new read replaces a fund's rows only if it passes sanity checks against the previous read
  (``sanity_problem``): weights add up to about 100% (not for leveraged, inverse and N-PORT
  funds), the file's own published weights too when they can be judged (iShares), the number of
  positions has not collapsed (daily files; a quarterly report is a new document), the as-of
  date has not gone back. A failed check is a FAILED item (the run is PARTIAL) and last read's
  rows stay. The fund is not retried for ``RETRY_AFTER_DAYS`` (a quarterly source: 30), and a
  collapsed position count that three reads in a row agree on (distinct, not older as-of dates)
  is accepted as a real rebalance; ``force`` accepts what it reads, checks off.

Per-fund rows are staged, then published as one partition; a crashed run resumes.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial

import pandas as pd

from algotrade.data.funds.holdings import Bridge, cusip_of, holdings_status, known_cusips
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
PUBLISHED_FLOOR = 0.97  # a file whose own published weights add up to less was cut short
MIN_COUNT_RATIO = 0.5  # a read with fewer positions than this share of the last one is rejected
CONFIRMATIONS = 2  # earlier rejections (as-of dates 2+) after which a third consistent read wins
RETRY_AFTER_DAYS = 2  # a rejected daily-file fund waits this many days (a quarterly one: 30)
_REJECTION = re.compile(r"read as of (\d{4}-\d{2}-\d{2}); (soft|hard)")


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


@dataclass(frozen=True)
class Problem:
    """Why a read must not replace what is stored. ``soft``: a collapsed position count, which
    a real rebalance also causes, so reads that keep agreeing win; ``hard`` never does."""

    text: str
    soft: bool = False


@dataclass(frozen=True)
class Rejection:
    """An earlier run's rejected read of a fund (parsed from its run record)."""

    session: date
    as_of: date
    soft: bool


@dataclass
class History:
    """What earlier runs left: when each fund was last read, what is stored, and rejections."""

    read: dict[str, date] = field(default_factory=dict)
    previous: dict[str, Previous] = field(default_factory=dict)
    rejected: dict[str, list[Rejection]] = field(default_factory=dict)


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


def retry_days(source: HoldingsSource) -> int:
    """How long a fund whose read was rejected is left alone."""
    return RETRY_AFTER_DAYS if source.cadence_days <= 1 else max(source.cadence_days // 3, 1)


def plan_due(
    covered: Mapping[str, HoldingsSource],
    issuers: Sequence[HoldingsSource],
    read: Mapping[str, date],
    session: date,
    refresh_days: int,
    force: bool = False,
    hold: Mapping[str, date] | None = None,
) -> list[str]:
    """Every fund to read on ``session``, in the order to read them: one list across issuers,
    funds never read first, then the oldest read first, issuer priority breaking ties (so
    daily-file funds feed the CUSIP bridge before the N-PORT funds that use it). ``hold``: fund
    -> the first session it may be tried again (a rejected read)."""
    rank = {source.name: i for i, source in enumerate(issuers)}
    due: list[str] = []
    for source in issuers:  # per issuer: its own cadence (N-PORT is quarterly)
        mine = [
            s
            for s, owner in covered.items()
            if owner is source and (force or (hold or {}).get(s, session) <= session)
        ]
        due += due_keys(mine, read, session, max(refresh_days, source.cadence_days), force)

    def order(symbol: str) -> tuple[int, date, int, str]:
        fetched = read.get(symbol)
        return (
            0 if fetched is None else 1,
            fetched or date.min,
            rank[covered[symbol].name],
            symbol,
        )

    return sorted(due, key=order)


def _read_before(ctx: TaskContext, etfs: pd.DataFrame, session: date) -> History:
    """Earlier runs' trace: the latest session each fund was read (stored holdings, or a
    finished run that found the issuer had no file for it, so it is retried once a window, not
    nightly), what the store holds, and the reads sanity checks rejected since the last stored
    one."""
    history = History()
    ids = dict(zip(etfs["instrument_id"], etfs["symbol"], strict=True))
    status = holdings_status(ctx.reader, session)
    columns = (status[c] for c in ("instrument_id", "as_of", "holdings_count", "fetched_on"))
    for iid, as_of, count, fetched in zip(*columns, strict=True):
        if iid in ids:
            history.read[ids[iid]] = fetched
            history.previous[ids[iid]] = Previous(as_of, int(count))
    for record in finished_runs(ctx.writer, TASK):
        if record.session_date > session:
            continue
        for symbol, item in record.items.items():
            label = item.split(":", 1)[0]
            if label in (NO_FILE, EMPTY):
                last = history.read.get(symbol, record.session_date)
                history.read[symbol] = max(last, record.session_date)
            found = _REJECTION.search(item) if label == REJECTED else None
            if found and record.session_date > history.read.get(symbol, date.min):
                rejection = Rejection(
                    record.session_date,
                    date.fromisoformat(found.group(1)),
                    found.group(2) == "soft",
                )
                history.rejected.setdefault(symbol, []).append(rejection)
    return history


def sanity_problem(
    holdings: pd.DataFrame,
    as_of: date,
    previous: Previous | None,
    geared: bool,
    check_sum: bool,
    published: float | None = None,
    check_count: bool = True,
) -> Problem | None:
    """Why a fund's new read must not replace what is stored (``None``: it can).

    The weights of all lines add up to about 100% (``check_sum``; not for leveraged and inverse
    funds, whose swap lines do not, nor N-PORT funds, which report net assets differently), and
    so do the file's own published weights when the adapter could judge them (``published``,
    iShares: the market-value weights always add up to 100%, a cut-short file cannot show it
    there). Against the previous read: the as-of date did not go back, and the number of
    positions did not collapse (``check_count``; a quarterly report is a new document, its
    position count may change). A truncated file or a changed layout that still parses fails
    here."""
    if check_sum and not geared:
        total = float(holdings["weight"].sum())
        if abs(total - 1.0) > WEIGHT_SUM_BAND:
            return Problem(f"weights add up to {total:.1%}, not about 100%")
        if published is not None and not PUBLISHED_FLOOR <= published <= 1 + WEIGHT_SUM_BAND:
            return Problem(f"the file's own weights add up to {published:.1%}: cut short?")
    if previous is None:
        return None
    if as_of < previous.as_of:
        return Problem(f"as of {as_of}, older than the stored {previous.as_of}")
    count = positions(holdings)
    if check_count and previous.count >= 10 and count < MIN_COUNT_RATIO * previous.count:
        return Problem(f"{count} positions, was {previous.count}", soft=True)
    return None


def confirmed(earlier: Sequence[Rejection], as_of: date) -> bool:
    """Whether reads on enough different days agree that a position count really collapsed: the
    last ``CONFIRMATIONS`` rejections were soft, on distinct as-of dates, none after this read's."""
    soft = [r for r in earlier if r.soft]
    dates = {r.as_of for r in soft}
    return len(dates) >= CONFIRMATIONS and as_of >= max(dates)


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
    cusips: Mapping[str, Bridge],
) -> pd.DataFrame:
    """The stored rows of one fund: ranked, trimmed, holdings linked to instrument ids."""
    count = positions(holdings)
    top = (holdings.head(keep_top) if keep_top > 0 else holdings).reset_index(drop=True)
    tickers = [None if pd.isna(t) else str(t) for t in top["holding_symbol"]]
    listed = [bool(flag) for flag in top["us_listed"]]
    linked: list[str | None] = []
    for i, identifier in enumerate(top["identifier"]):
        # No ticker: the instrument another issuer's line of the same CUSIP resolved to when it
        # was stored (equity lines only; a bond's CUSIP is never in the map).
        bridged = None
        if tickers[i] is None and top["asset_class"].iloc[i] == "Equity":
            bridged = cusips.get(cusip_of(identifier) or "")
        if bridged is not None:
            tickers[i] = bridged[0]
            linked.append(bridged[1])
        else:
            ticker = tickers[i]
            known = listed[i] and ticker is not None and resolver.knows(ticker)
            linked.append(resolver.id_for(ticker) if known and ticker is not None else None)
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
    cusips: dict[str, Bridge]  # grows as daily-file funds are read, for the N-PORT funds after
    history: History
    geared: set[str]
    force: bool = False


def _fund(run: IngestRun, source: HoldingsSource, iid: str, symbol: str, c: FundContext) -> str:
    """Read one fund through its issuer and stage its rows (a read that fails the sanity checks
    is a FAILED item and stages nothing, so the fund keeps what it had)."""
    try:
        normalized = run.fetch(source, FetchRequest(symbol, iid, run.session))
    except NoResponseError:
        return NO_FILE
    if normalized is None or normalized.session_date is None:
        return EMPTY
    holdings, as_of = normalized.parsed["holdings"], normalized.session_date
    basis_points = normalized.notes.get("published_weight_bp")
    note = ""
    problem = None
    if not c.force:
        problem = sanity_problem(
            holdings,
            as_of,
            c.history.previous.get(symbol),
            symbol in c.geared,
            check_sum=c.sources.check_weight_sum and not source.scope_limited,
            published=None if basis_points is None else basis_points / 10_000,
            check_count=source.cadence_days <= 1,
        )
    if (
        problem is not None
        and problem.soft
        and confirmed(c.history.rejected.get(symbol, []), as_of)
    ):
        problem, note = None, " (the new size was confirmed by earlier reads)"
    if problem is not None:
        kind = "soft" if problem.soft else "hard"
        return f"{REJECTED}: {problem.text} (read as of {as_of}; {kind})"
    frame = fund_frame(iid, symbol, as_of, holdings, c.sources.keep_top, c.resolver, c.cusips)
    if not source.scope_limited:  # only issuers that print tickers feed the CUSIP bridge
        known = frame[frame["holding_id"].notna() & frame["identifier"].notna()]
        for identifier, ticker, holding_id, kind in zip(
            known["identifier"],
            known["holding_symbol"],
            known["holding_id"],
            known["asset_class"],
            strict=True,
        ):
            cusip = cusip_of(identifier)
            if cusip is not None and kind == "Equity":
                c.cusips[cusip] = (str(ticker), str(holding_id))
    run.stage(TABLE, symbol, frame, source.name)
    return f"OK: {len(holdings)} lines as of {as_of}{note}"


def ingest_etf_holdings(
    ctx: TaskContext,
    sources: HoldingsSources,
    session: date,
    force: bool = False,
    limit: int | None = None,
    only: Sequence[str] = (),
) -> RunRecord:
    """Read the due ETFs' holdings from their issuers (``only``: just these tickers; ``force``:
    every covered fund, accepting what it reads without the sanity checks)."""
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
        history = _read_before(ctx, etfs, session)
        hold = {
            s: max(r.session for r in rejected) + timedelta(days=retry_days(covered[s]))
            for s, rejected in history.rejected.items()
            if s in covered
        }
        due = plan_due(
            covered, sources.issuers, history.read, session, sources.refresh_days, force, hold
        )
        todo = due if limit is None else due[: max(limit, 0)]
        shared = FundContext(
            sources,
            run.resolver(),
            known_cusips(run.reader, session, [s.name for s in sources.issuers if s.scope_limited]),
            history,
            set(etfs.loc[etfs["geared"], "symbol"]),
            force,
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
