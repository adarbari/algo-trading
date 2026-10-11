"""The trade ledger of an edge's verdict basis, one page at a time (ADR 0064 decisions 2, 10, 11).

``load_edge_trades`` serves the picks of the basis the verdict rests on (``basis.official_basis``:
never re-chosen) for one ``period``: ``in_sample`` / ``out_of_sample`` / ``all`` from the official
run's ledger (``runs.load_run_trades``, the one reader: hidden copies keep their in-sample rows,
a personal-licence per-name value is ``Unknown(LICENCE)`` to anyone but the licence holder,
a pruned ledger ``Unknown(PRUNED)``, one never written ``Unknown(NOT_STORED)``), and ``live`` from
the edge's paper record (``edge_desk.paper.load_trades``: the rows as the session's cutoff knew
them, never re-derived); an edge that records no paper trades has no live period
(``Unknown(NOT_RECORDING)``, said, not an empty list). The GraphQL page and the CSV file both
call it, so they cannot differ; an excluded pick keeps its public reason, the causes stay in the
``Unknown`` for admins."""

from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.tickers import ListingTickers, listing_tickers
from algotrade.data.reference import companies, instruments
from algotrade.services.read.availability.cause import Cause, CauseLevel, CauseLink, table_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk import paper
from algotrade.services.read.edge_desk.states import is_recording
from algotrade.services.read.edge_evidence.basis import OfficialBasis, official_basis
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, load_edge
from algotrade.services.read.evaluation.runs import SORTABLE, TradeCell, TradeRow, TradeText
from algotrade.services.read.session import reference_snapshot_on, reference_snapshots
from algotrade.services.read.values import Unknown, UnknownCode

PAGE_SIZE = 50
SKIPPED = "SKIPPED"  # the public reason of a live signal that was not traded
STATUSES = ("won", "lost", "excluded", "open")  # open: a paper trade not settled by the session
EXCLUDED_REASONS = (
    "UNMEASURED", "MISSING_VALUE", "NO_ENTRY_BAR", "NO_IMPLIED_VOL", "MISSING_DRAWDOWN", SKIPPED,
)  # fmt: skip


class Period(StrEnum):
    """Which trades: the backtest's in-sample or out-of-sample side, the live paper record, all."""

    IN_SAMPLE = "in_sample"
    OUT_OF_SAMPLE = "out_of_sample"
    LIVE = "live"
    ALL = "all"


class Sort(StrEnum):
    """The columns a page sorts by (``runs.SORTABLE``); a per-name value the viewer may not see
    sorts as missing."""

    DECISION = "decision_session"
    EXIT = "exit_session"
    INSTRUMENT = "instrument_id"
    RANK = "rank"
    STATUS = "status"
    VALUE = "value"
    SCORE = "score"
    DRAWDOWN = "max_drawdown"
    ADV = "adv_usd"
    SYMBOL = "symbol"


@dataclass(frozen=True)
class EdgeTradePage:
    """One page (``page`` from 1, ``PAGE_SIZE`` rows) of ``total`` trades of the basis
    (``basis``: its screen and holding period; None: ``unknown`` says why there is none).
    ``unknown``: why the ledger cannot be read (NOT_RUN, PRUNED, NOT_STORED) or None;
    ``oos_hidden``: a copy's out-of-sample trades are withheld, so none of them is served;
    ``licence``: the trial licence of the rows; ``symbols_snapshot``: the
    ``instruments/reference`` snapshot the tickers and company names are read from (ADR 0007)."""

    period: Period
    page: int
    unknown: Unknown | None
    basis: str | None = None
    rows: tuple[TradeRow, ...] = ()
    total: int = 0
    licence: str | None = None
    oos_hidden: bool = False
    page_size: int = PAGE_SIZE
    symbols_snapshot: date | None = None


def _backtest(
    ctx: ReadContext,
    basis: OfficialBasis,
    period: Period,
    offset: int,
    limit: int | None,
    sort: str | None,
    descending: bool,
) -> runs.RunTrades:
    assert basis.run is not None and basis.key is not None
    before = {Period.IN_SAMPLE: True, Period.OUT_OF_SAMPLE: False}.get(period)
    return runs.load_run_trades(
        ctx, basis.run, variant=basis.key[0], horizon=basis.key[1], before_split=before,
        offset=offset, limit=limit, sort=sort, descending=descending,
    )  # fmt: skip


def _live_row(t: paper.PaperTrade) -> TradeRow:
    skipped = t.status == paper.SKIPPED
    status = "excluded" if skipped else t.status
    return TradeRow(
        variant=t.screener, horizon_sessions=t.horizon_sessions,
        decision_session=t.signal_session, entry_session=t.buy_session,
        exit_session=t.sell_session, instrument_id=t.instrument_id, rank=t.rank, status=status,
        excluded_reason=SKIPPED if skipped else None,
        hit=(t.status == paper.WON) if t.status in (paper.WON, paper.LOST) else None,
        delisted=t.delisted, before_split=False, score=TradeCell(),
        value=TradeCell(t.excess_return),
        gross_value=TradeCell(), max_drawdown=None, adv_usd=TradeCell(), reference=TradeCell(),
        touch=TradeCell(), source="live",
    )  # fmt: skip


def _sort_value(row: TradeRow, sort: str) -> object:
    found = getattr(row, sort)
    return found.value if isinstance(found, TradeCell) else found


def _live(
    ctx: ReadContext, edge: Edge, basis: OfficialBasis, sort: str | None, descending: bool
) -> list[TradeRow]:
    assert basis.key is not None
    found = paper.load_trades(ctx, {edge.id: edge}, lookback=None)
    rows = [
        _live_row(t)
        for t in found
        if t.screener == basis.key[0] and t.horizon_sessions == basis.key[1]
    ]
    rows.sort(key=lambda r: (r.decision_session, r.rank or 0, r.instrument_id))
    if sort not in SORTABLE:
        return rows
    present = [r for r in rows if _sort_value(r, sort) is not None]
    missing = [r for r in rows if _sort_value(r, sort) is None]  # a missing value sorts last
    present.sort(key=lambda r: _sort_value(r, sort), reverse=descending)  # type: ignore[arg-type,return-value]
    return present + missing


PAPER_STEP = "edge-signals"  # the nightly step that records paper trades
REFERENCE = "instruments/reference"
SYMBOL = "symbol"  # the sort by ticker: the tickers are read after the rows, so it sorts here


def _gap(why: str, code: UnknownCode = UnknownCode.NO_ROW) -> Unknown:
    return Unknown(code, table_cause(REFERENCE, why, code.value))


Names = dict[str, tuple[str, TradeText]]


def _snapshot_names(ctx: ReadContext, snap: date) -> Names:
    """Every instrument's ticker and company name in the reference snapshot ``snap`` (the company
    snapshot on or before it; the company's name, else the listing's, else ``Unknown``). The
    snapshot is read once per publish, not once per page or per row (the key reads ``visible_seq``
    before computing, ADR 0022)."""

    def read() -> Names:
        found = instruments(ctx.reader, snap)
        firms = companies(ctx.reader, snap)
        firm = (
            {} if firms is None else dict(zip(firms["instrument_id"], firms["name"], strict=False))
        )
        out: Names = {}
        for iid, symbol, listing in zip(
            found["instrument_id"], found["symbol"], found["name"], strict=True
        ):
            text = (str(firm.get(iid) or "").strip()) or (str(listing or "").strip())
            gap = TradeText(None, _gap("the snapshot has no company name"))
            out[str(iid)] = (str(symbol), TradeText(text) if text else gap)
        return out

    return ctx.cache.get_or_compute(("ledger-names", ctx.reader.visible_seq(), snap), read)  # type: ignore[no-any-return]


def _listing_tickers(ctx: ReadContext) -> ListingTickers:
    """The listing history's tickers, read once per publish (like the snapshot maps)."""
    return ctx.cache.get_or_compute(  # type: ignore[no-any-return]
        ("ledger-listing-tickers", ctx.reader.visible_seq()), lambda: listing_tickers(ctx.reader)
    )


def _listed(ctx: ReadContext, missing: list[TradeRow]) -> dict[tuple[str, date], str]:
    """The ticker each of ``missing`` (rows no reference snapshot names) carried at its decision
    session, from the listing history (a delisted name no snapshot ever held); a store with no
    listing history names none."""
    try:
        listings = _listing_tickers(ctx)
    except MissingDataError:
        return {}
    found = {(r.instrument_id, r.decision_session): listings.on(r.instrument_id, r.decision_session)
             for r in missing}  # fmt: skip
    return {k: v for k, v in found.items() if v is not None}


def _last_known(ctx: ReadContext, ids: set[str]) -> dict[str, tuple[str, TradeText, date]]:
    """For each of ``ids`` the ticker of the LAST reference snapshot that held it (newest first,
    stopping once every id is found): a delisted pick's last known ticker."""
    found: dict[str, tuple[str, TradeText, date]] = {}
    for snap in reversed(reference_snapshots(ctx.reader)):
        if not ids - found.keys():
            break
        for iid, (symbol, company) in _snapshot_names(ctx, snap).items():
            if iid in ids and iid not in found:
                found[iid] = (symbol, company, snap)
    return found


def _named(ctx: ReadContext, page: EdgeTradePage) -> EdgeTradePage:
    """``page`` with each row's ticker and company name as the reference snapshot in force at the
    row's DECISION session had them (never today's: a name changes ticker). Each row's day maps to
    its snapshot and each snapshot is read once, however many days or rows. A delisted pick its
    day's snapshot lacks gets its ticker from the listing history as of that session (a delisted
    name no snapshot ever held), else the last snapshot that held it, its last known ticker; any
    other name no snapshot names is ``Unknown`` (never its id, ADR 0018)."""
    stamp = {
        d: reference_snapshot_on(ctx.reader, d) for d in {r.decision_session for r in page.rows}
    }
    names = {s: _snapshot_names(ctx, s) for s in {s for s in stamp.values() if s is not None}}
    unnamed = [
        r
        for r in page.rows
        if (snap := stamp[r.decision_session]) is None or r.instrument_id not in names[snap]
    ]
    listed = _listed(ctx, unnamed) if unnamed else {}
    missing = {
        r.instrument_id
        for r in unnamed
        if r.delisted and (r.instrument_id, r.decision_session) not in listed
    }
    last = _last_known(ctx, missing) if missing else {}
    rows = []
    for r in page.rows:
        snap = stamp[r.decision_session]
        hit = names[snap].get(r.instrument_id) if snap is not None else None
        as_of = snap
        if hit is not None:
            symbol, company = TradeText(hit[0]), hit[1]
        elif (r.instrument_id, r.decision_session) in listed:
            symbol = TradeText(listed[(r.instrument_id, r.decision_session)])
            company = TradeText(None, _gap("the listing history names no company"))
            as_of = _listing_tickers(ctx).snapshot  # the snapshot read, not the session (ADR 0036)
        elif r.instrument_id in last:
            ticker, company, as_of = last[r.instrument_id]
            symbol = TradeText(ticker)
        else:
            gap = _gap("no row for the name in the snapshot in force at its decision session")
            symbol, company, as_of = TradeText(None, gap), TradeText(None, gap), None
        rows.append(replace(r, symbol=symbol, company=company, symbol_as_of=as_of))
    newest = max((r.symbol_as_of for r in rows if r.symbol_as_of), default=None)
    return replace(page, rows=tuple(rows), symbols_snapshot=newest)


def load_edge_trades(
    ctx: ReadContext,
    edge: Edge,
    period: Period = Period.ALL,
    page: int = 1,
    sort: str | None = None,
    descending: bool = False,
    *,
    limit: int | None = PAGE_SIZE,
) -> EdgeTradePage:
    """The trades of ``edge``'s verdict basis for ``period``: page ``page`` of ``limit`` rows
    (None: every row, for the file), sorted by ``sort`` (``runs.SORTABLE``), each named."""
    if sort == SYMBOL:  # sorted after naming, over the whole ledger, then paged
        whole = _named(ctx, _unnamed(ctx, edge, period, 1, None, False, None))
        known = [r for r in whole.rows if r.symbol.value is not None]
        known.sort(key=lambda r: (r.symbol.value or "").casefold(), reverse=descending)
        rows = (*known, *(r for r in whole.rows if r.symbol.value is None))  # unknown last
        offset = 0 if limit is None else (max(page, 1) - 1) * limit
        part = rows[offset : None if limit is None else offset + limit]
        return replace(whole, page=max(page, 1), rows=part)
    return _named(ctx, _unnamed(ctx, edge, period, page, sort, descending, limit))


def _unnamed(
    ctx: ReadContext,
    edge: Edge,
    period: Period,
    page: int,
    sort: str | None,
    descending: bool,
    limit: int | None,
) -> EdgeTradePage:
    page = max(page, 1)  # a page below the first is the first, and served as such
    basis = official_basis(ctx, edge)
    if basis.key is None or basis.run is None:
        return EdgeTradePage(period, page, basis.unknown)
    words = f"{basis.key[0]}, {basis.key[1]} trading days"
    offset = 0 if limit is None else (page - 1) * limit
    if period is Period.LIVE and not is_recording(edge):
        why = "paper trades are recorded once the edge is evidenced or followed"
        link = CauseLink(CauseLevel.STEP, PAPER_STEP, UnknownCode.NOT_RECORDING.value, why)
        gap = Unknown(UnknownCode.NOT_RECORDING, Cause((link,)))
        return EdgeTradePage(period, page, gap, words)
    if period is Period.LIVE:
        rows = _live(ctx, edge, basis, sort, descending)
        part = tuple(rows[offset : None if limit is None else offset + limit])
        return EdgeTradePage(period, page, None, words, part, len(rows))
    hidden = basis.run.oos_hidden and period in (Period.OUT_OF_SAMPLE, Period.ALL)
    if basis.run.oos_hidden and period is Period.OUT_OF_SAMPLE:
        return EdgeTradePage(period, page, None, words, oos_hidden=True)
    found = _backtest(ctx, basis, period, offset, limit, sort, descending)
    return EdgeTradePage(
        period, page, found.unknown, words, found.rows, found.total, found.licence, hidden
    )


def load_trades_of(
    ctx: ReadContext,
    edge_id: str,
    period: Period = Period.ALL,
    page: int = 1,
    sort: str | None = None,
    descending: bool = False,
) -> EdgeTradePage | None:
    """``load_edge_trades`` for the edge ``edge_id`` the user sees (None: they see no such edge)."""
    edge = load_edge(ctx, edge_id)
    return None if edge is None else load_edge_trades(ctx, edge, period, page, sort, descending)
