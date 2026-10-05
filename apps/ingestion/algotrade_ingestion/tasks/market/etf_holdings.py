"""What each ETF holds -> ``holdings/etf`` (ADR 0035): one row per fund x holding x as-of date.

Issuers are adapters behind one shape (``HoldingsSource``), tried in priority order: the first
that lists a fund publishes it (State Street's and iShares' daily files, then SEC N-PORT for the
rest). Per run:

- each issuer's directory says which funds it publishes; the funds are the active ETFs of the
  reference snapshot (security type ``ETF``) that some issuer lists. N-PORT is scope-limited
  (``[etf_holdings] fallback_scope``): by default only for the ETFs no daily file covers that are
  optionable or liquid (a 20-session dollar volume of at least ``fallback_min_adv_usd``, read
  from the latest ``price_stats`` rows; without any (a new store: the nightly rolls up after this
  step), only the optionable ones, and the stats say so: ``fallback_adv_missing``);
- a fund is due when it was never read, or past its refresh slot (``[etf_holdings]
  refresh_days``, spread over the window by ticker; funds an issuer lists but has no file for
  count as read, so they are retried once a window, not nightly; SEC N-PORT funds report
  quarterly, so they are never read more often than ``cadence_days``). ONE list orders every due
  fund across issuers (``plan_due``): funds whose last read failed go after healthy ones, then
  funds never read, then the oldest read first, issuer priority breaking ties. Only then is
  ``limit`` applied (``nightly_cap``; the nightly passes ``[etf_holdings] per_night``), and every
  issuer with funds due is first given at least ``ISSUER_FLOOR`` (20%) of the slots, so a cap can
  slow the weekly funds down but one issuer, broken or not, never starves the others. A fund
  whose read failed (an error, or a rejection) is held back with a wait that doubles on each
  failure in a row (``hold_until``: 1 or 2 days, up to 30; N-PORT 30), so a lasting fault costs
  one request a month per fund, not one a night;
- an issuer whose fund list could not be read tonight keeps its funds: they are not handed to
  the next issuer (N-PORT is months older than the daily rows stored), and the run is PARTIAL;
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
  rows stay. A collapsed position count is a soft rejection: it is accepted as a real rebalance
  once the two latest outcomes were soft rejections too and the three reads agree (``confirmed``:
  counts within 10% of each other and below the stored one, three increasing as-of dates, or one
  date and one count seen on three different run days); a hard rejection, a missing file or a
  failed read in between starts the count over. Outcomes are saved as plain fields in the run's
  stats (``fund_events``), not read back from item text. ``force`` accepts what it reads,
  checks off.

Per-fund rows are staged, then published as one partition; a crashed run resumes.
"""

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from itertools import pairwise
from typing import Any, Self

import pandas as pd

from algotrade.data.funds.holdings import Bridge, cusip_of, holdings_status, known_cusips
from algotrade.data.reference import instruments, snapshot
from algotrade.data.resolver import SymbolResolver
from algotrade.data.rollups import rollup_on
from algotrade.services.features import site_features, site_store
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.refresh import due_keys
from algotrade_ingestion.tasks.framework.run import (
    FAILURES,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_ingestion.tasks.market.option_chains import PRICE_GROUP
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
CONFIRMATIONS = 2  # earlier soft rejections after which a third consistent read wins
COUNT_SPREAD = 1.10  # position counts of reads that "agree" are within 10% of each other
EVENTS = "fund_events"  # run stats key: what each fund's outcome was, structured (see Event)
ERROR, MISSING, SOFT, HARD = "error", "missing", "soft", "hard"  # Event kinds
FAILING = (ERROR, SOFT, HARD)  # the kinds that hold a fund back (MISSING is a window, not a fault)
REJECTION_HOLD_DAYS = 2  # a rejected daily-file fund first waits this long, then 4, 8, ... (cap 30)
ERROR_HOLD_DAYS = 1  # a daily-file fund whose read failed first waits this long, then 2, 4, ...
MAX_HOLD_DAYS = 30
ISSUER_FLOOR = 0.2  # each issuer with funds due gets at least this share of the nightly cap


@dataclass(frozen=True)
class HoldingsSources:
    issuers: Sequence[HoldingsSource]  # priority order: the first that lists a fund reads it
    refresh_days: int = 7
    keep_top: int = 100  # holdings stored per fund; 0 keeps all
    fallback_scope: str = "liquid"  # funds a scope-limited issuer (N-PORT) is read for
    check_weight_sum: bool = True  # reject weights far from 100% (off in tests: trimmed files)
    fallback_min_adv_usd: float = 5_000_000.0  # "liquid": also funds with at least this ADV


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
class Event:
    """One fund's non-OK outcome in a run: ``kind`` (``ERROR`` the read failed, ``MISSING`` the
    issuer has no file, ``SOFT`` / ``HARD`` a rejected read with the as-of date and number of
    positions it had). Saved in the run's stats (``EVENTS``) as plain fields, never parsed from
    the wording of an item."""

    session: date
    kind: str
    as_of: date | None = None
    count: int | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "as_of": None if self.as_of is None else self.as_of.isoformat(),
            "count": self.count,
        }

    @classmethod
    def from_record(cls, session: date, raw: Mapping[str, Any]) -> Self:
        as_of = raw.get("as_of")
        return cls(
            session,
            str(raw["kind"]),
            None if as_of is None else date.fromisoformat(as_of),
            raw.get("count"),
        )


@dataclass
class History:
    """What earlier runs left: when each fund was last read, what is stored (and from which
    issuer), and the outcomes (``Event``) of every run since its last stored read."""

    read: dict[str, date] = field(default_factory=dict)
    previous: dict[str, Previous] = field(default_factory=dict)
    stored_from: dict[str, str] = field(default_factory=dict)
    events: dict[str, list[Event]] = field(default_factory=dict)


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


def liquid_funds(
    run: IngestRun, etfs: pd.DataFrame, session: date, min_adv_usd: float
) -> set[str] | None:
    """Tickers of the ``etfs`` whose 20-session dollar volume (``price_stats.adv_usd_20d``) is at
    least ``min_adv_usd``, on the latest session on or before ``session`` that has ``price_stats``
    rows; ``None`` when there are none (the nightly rolls them up after this step, so they are
    usually the previous session's)."""
    table = site_features(site_store(run.ctx.configs)).table(PRICE_GROUP)
    snap = snapshot(run.reader, table, session)
    if snap is None or snap.pre_snapshot:
        return None
    frame = rollup_on(run.reader, table, snap.snapshot_date, list(etfs["instrument_id"]))
    if frame is None or "adv_usd_20d" not in frame.columns:
        return None
    dollars = pd.to_numeric(frame["adv_usd_20d"], errors="coerce")
    symbols = dict(zip(etfs["instrument_id"], etfs["symbol"], strict=True))
    return {symbols[i] for i in frame.loc[dollars >= min_adv_usd, "instrument_id"] if i in symbols}


def scope_funds(
    run: IngestRun, etfs: pd.DataFrame, session: date, sources: HoldingsSources
) -> tuple[set[str], bool]:
    """(the tickers a scope-limited issuer is read for, whether ``liquid`` had to fall back to
    the optionable funds for want of ``price_stats`` rows), by ``fallback_scope``."""
    optionable = set(etfs.loc[etfs["optionable"], "symbol"])
    if sources.fallback_scope == "all":
        return set(etfs["symbol"]), False
    if sources.fallback_scope == "optionable":
        return optionable, False
    if sources.fallback_scope != "liquid":
        return set(), False
    liquid = liquid_funds(run, etfs, session, sources.fallback_min_adv_usd)
    return (optionable, True) if liquid is None else (optionable | liquid, False)


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


def failing_streak(events: Sequence[Event]) -> list[Event]:
    """The trailing run of failures (errors and rejections) with nothing else in between."""
    streak: list[Event] = []
    for event in reversed(events):
        if event.kind not in FAILING:
            break
        streak.append(event)
    return streak[::-1]


def hold_until(events: Sequence[Event], source: HoldingsSource) -> date | None:
    """The first session a fund may be tried again, or ``None`` when it may be tried now.

    A failure (a read that raised, or one the sanity checks rejected) holds the fund back, and
    each further failure in a row doubles the wait: 1 day for an error and 2 for a rejection
    (daily files), 4, 8, ... up to ``MAX_HOLD_DAYS``; a quarterly source waits ``cadence // 3``
    (30 for N-PORT) from the first failure. A fund that keeps failing is tried about monthly
    instead of nightly, so a broken issuer cannot keep taking the nightly cap."""
    streak = failing_streak(events)
    if not streak:
        return None
    if source.cadence_days > 1:
        base = max(source.cadence_days // 3, 1)
    else:
        base = ERROR_HOLD_DAYS if streak[-1].kind == ERROR else REJECTION_HOLD_DAYS
    days = min(base * 2 ** (len(streak) - 1), MAX_HOLD_DAYS)
    return streak[-1].session + timedelta(days=days)


def plan_due(
    covered: Mapping[str, HoldingsSource],
    issuers: Sequence[HoldingsSource],
    read: Mapping[str, date],
    session: date,
    refresh_days: int,
    force: bool = False,
    hold: Mapping[str, date] | None = None,
    failing: Collection[str] = (),
) -> list[str]:
    """Every fund to read on ``session``, in the order to read them: one list across issuers,
    healthy funds before those whose last read failed (``failing``), funds never read first,
    then the oldest read first, issuer priority breaking ties (so daily-file funds feed the
    CUSIP bridge before the N-PORT funds that use it). ``hold``: fund -> the first session it
    may be tried again (a failed or rejected read)."""
    rank = {source.name: i for i, source in enumerate(issuers)}
    due: list[str] = []
    for source in issuers:  # per issuer: its own cadence (N-PORT is quarterly)
        mine = [
            s
            for s, owner in covered.items()
            if owner is source and (force or (hold or {}).get(s, session) <= session)
        ]
        due += due_keys(mine, read, session, max(refresh_days, source.cadence_days), force)

    def order(symbol: str) -> tuple[int, int, date, int, str]:
        fetched = read.get(symbol)
        return (
            1 if symbol in failing else 0,
            0 if fetched is None else 1,
            fetched or date.min,
            rank[covered[symbol].name],
            symbol,
        )

    return sorted(due, key=order)


def nightly_cap(
    due: Sequence[str], covered: Mapping[str, HoldingsSource], limit: int | None
) -> list[str]:
    """The funds to read tonight: the first ``limit`` of the ordered ``due`` list, except that
    every issuer with funds due is first given its own best ``ISSUER_FLOOR`` of the slots, so
    one issuer (whatever its funds' ages or faults) cannot take the whole cap."""
    if limit is None:
        return list(due)
    limit = max(limit, 0)
    if limit >= len(due):
        return list(due)
    reserve = math.ceil(round(ISSUER_FLOOR * limit, 6))
    chosen: set[str] = set()
    taken: dict[str, int] = {}
    for fund in due:  # first pass: up to the floor per issuer, in list order
        name = covered[fund].name
        if taken.get(name, 0) < reserve and len(chosen) < limit:
            chosen.add(fund)
            taken[name] = taken.get(name, 0) + 1
    for fund in due:  # second pass: the rest of the cap, in list order
        if len(chosen) >= limit:
            break
        chosen.add(fund)
    return [fund for fund in due if fund in chosen]


def _read_before(ctx: TaskContext, etfs: pd.DataFrame, session: date) -> History:
    """Earlier runs' trace: the latest session each fund was read (stored holdings, or a
    finished run that found the issuer had no file for it, so it is retried once a window, not
    nightly), what the store holds and from which issuer, and every outcome (``Event``) the
    runs since the last stored read recorded in their stats."""
    history = History()
    ids = dict(zip(etfs["instrument_id"], etfs["symbol"], strict=True))
    status = holdings_status(ctx.reader, session)
    names = ("instrument_id", "as_of", "holdings_count", "fetched_on", "source")
    for iid, as_of, count, fetched, issuer in zip(*(status[c] for c in names), strict=True):
        if iid in ids:
            history.read[ids[iid]] = fetched
            history.previous[ids[iid]] = Previous(as_of, int(count))
            history.stored_from[ids[iid]] = str(issuer)
    stored, symbols = dict(history.read), set(ids.values())
    for record in finished_runs(ctx.writer, TASK):
        if record.session_date > session:
            continue
        for symbol, raw in record.stats.get(EVENTS, {}).items():
            if symbol not in symbols or record.session_date <= stored.get(symbol, date.min):
                continue  # not an active ETF, or a stored read has happened since
            event = Event.from_record(record.session_date, raw)
            history.events.setdefault(symbol, []).append(event)
            if event.kind == MISSING:  # no file: counts as read, so it is retried once a window
                history.read[symbol] = max(history.read.get(symbol, event.session), event.session)
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


def confirmed(earlier: Sequence[Event], read: Event, stored: int) -> bool:
    """Whether three reads in a row agree that a position count really collapsed.

    The two latest outcomes before ``read`` must both be soft rejections with nothing else
    after them (a hard rejection, a missing file or a failed read in between starts over), all
    three counts below the ``stored`` one and within ``COUNT_SPREAD`` of each other, and
    either their as-of dates strictly increase (a file that updates daily: three distinct
    days) or they are one date with one count seen on three different run days (a file that
    updates monthly keeps its date for weeks, so it must still get through)."""
    streak = [e for e in earlier[-CONFIRMATIONS:] if e.kind == SOFT]
    if len(streak) < CONFIRMATIONS:
        return False
    window = [*streak, read]
    counts = [e.count for e in window if e.count is not None]
    dates = [e.as_of for e in window if e.as_of is not None]
    if len(counts) < len(window) or len(dates) < len(window):
        return False
    if min(counts) < 1 or max(counts) >= stored or max(counts) > COUNT_SPREAD * min(counts):
        return False
    if all(a < b for a, b in pairwise(dates)):
        return True
    one_reading = len(set(dates)) == 1 and len(set(counts)) == 1
    return one_reading and len({e.session for e in window}) == len(window)


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
    outcomes: dict[str, Event] = field(default_factory=dict)  # a fund's non-OK result, this run


def _fund(run: IngestRun, source: HoldingsSource, iid: str, symbol: str, c: FundContext) -> str:
    """Read one fund through its issuer and stage its rows (a read that fails the sanity checks
    is a FAILED item and stages nothing, so the fund keeps what it had)."""
    try:
        normalized = run.fetch(source, FetchRequest(symbol, iid, run.session))
    except NoResponseError:
        c.outcomes[symbol] = Event(run.session, MISSING)
        return NO_FILE
    if normalized is None or normalized.session_date is None:
        c.outcomes[symbol] = Event(run.session, MISSING)
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
    count = positions(holdings)
    previous = c.history.previous.get(symbol)
    read = Event(run.session, SOFT, as_of, count)
    if (
        problem is not None
        and problem.soft
        and previous is not None
        and confirmed(c.history.events.get(symbol, []), read, previous.count)
    ):
        problem, note = None, " (the new size was confirmed by earlier reads)"
    if problem is not None:
        kind = SOFT if problem.soft else HARD
        c.outcomes[symbol] = Event(run.session, kind, as_of, count)
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
        events: dict[str, Any] = run.stats.setdefault(
            EVENTS, dict(run.record.stats.get(EVENTS, {}))
        )
        run.record.stats = run.stats  # checkpoints save the events with the items
        listed: dict[str, set[str]] = {}
        for source in sources.issuers:
            run.attempt(DIRECTORY + source.name, partial(_directory, run, source, listed))
        history = _read_before(ctx, etfs, session)
        covered = assign(sorted(ids), sources.issuers, listed)
        # An issuer whose fund list could not be read tonight: do not hand its funds to the next
        # issuer (N-PORT is months older than the daily rows stored and would be rejected, after
        # hundreds of header requests); they wait for the next night.
        down = {
            s.name for s in sources.issuers if status_label(run.items[DIRECTORY + s.name]) != "OK"
        }
        skipped = {s for s in covered if history.stored_from.get(s) in down}
        covered = {s: o for s, o in covered.items() if s not in skipped}
        wanted, no_adv = scope_funds(run, etfs, session, sources)
        out_of_scope = {s for s, o in covered.items() if o.scope_limited and s not in wanted}
        covered = {s: o for s, o in covered.items() if s not in out_of_scope}
        hold = {
            s: until
            for s, past in history.events.items()
            if s in covered and (until := hold_until(past, covered[s])) is not None
        }
        failing = {s for s, past in history.events.items() if s in covered and failing_streak(past)}
        due = plan_due(
            covered, sources.issuers, history.read, session, sources.refresh_days, force, hold,
            failing,
        )  # fmt: skip
        todo = nightly_cap(due, covered, limit)
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
            status = run.attempt(
                symbol, partial(_fund, run, covered[symbol], ids[symbol], symbol, shared)
            )
            _note(events, symbol, status, shared.outcomes.get(symbol), session)
            if done % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        rows = run.publish(TABLE)
        funds = {k: v for k, v in run.items.items() if not k.startswith(DIRECTORY)}
        run.stats.update(
            etfs=len(ids),
            fallback_scope=sources.fallback_scope,
            fallback_adv_missing=no_adv,
            covered={s.name: sum(1 for o in covered.values() if o is s) for s in sources.issuers},
            uncovered=len(ids) - len(covered) - len(out_of_scope) - len(skipped),
            out_of_scope=len(out_of_scope),
            skipped_directory_down=len(skipped),
            directory_down=sorted(down),
            held=len(hold),
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
        if down:
            run.partial(
                f"{', '.join(sorted(down))}: fund list unavailable, {len(skipped)} funds skipped"
            )

    return run.record


def _note(
    events: dict[str, Any], symbol: str, status: str, outcome: Event | None, session: date
) -> None:
    """Keep the structured outcome of one fund in the run's stats: a read that raised is an
    ``ERROR``, a rejection or a missing file carries its own ``Event``, an OK read clears it."""
    label = status_label(status)
    if label == "OK":
        events.pop(symbol, None)
    elif label in FAILURES and outcome is None:
        events[symbol] = Event(session, ERROR).to_record()
    elif outcome is not None:
        events[symbol] = outcome.to_record()
