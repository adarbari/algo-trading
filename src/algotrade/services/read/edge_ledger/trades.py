"""The trade ledger of an edge's verdict basis, one page at a time (ADR 0064 decisions 2, 10, 11).

``load_edge_trades`` serves the picks of the basis the verdict rests on (``basis.official_basis``:
never re-chosen) for one ``period``: ``in_sample`` / ``out_of_sample`` / ``all`` from the official
run's ledger (``runs.load_run_trades``, the one reader: hidden copies keep their in-sample rows,
a personal-licence per-name value is ``Unknown(LICENCE)`` to anyone but the licence holder,
a pruned ledger ``Unknown(PRUNED)``, one never written ``Unknown(NOT_STORED)``), and ``live`` from
the edge's paper record (``edge_desk.paper.load_trades``: the rows as the session's cutoff knew
them, never re-derived). The GraphQL page and the CSV file both call it, so they cannot differ;
an excluded pick keeps its public reason, the causes stay in the ``Unknown`` for admins."""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk import paper
from algotrade.services.read.edge_evidence.basis import OfficialBasis, official_basis
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, load_edge
from algotrade.services.read.evaluation.runs import SORTABLE, TradeCell, TradeRow
from algotrade.services.read.values import Unknown

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


@dataclass(frozen=True)
class EdgeTradePage:
    """One page (``page`` from 1, ``PAGE_SIZE`` rows) of ``total`` trades of the basis
    (``basis``: its screen and holding period; None: ``unknown`` says why there is none).
    ``unknown``: why the ledger cannot be read (NOT_RUN, PRUNED, NOT_STORED) or None;
    ``oos_hidden``: a copy's out-of-sample trades are withheld, so none of them is served;
    ``licence``: the trial licence of the rows."""

    period: Period
    page: int
    unknown: Unknown | None
    basis: str | None = None
    rows: tuple[TradeRow, ...] = ()
    total: int = 0
    licence: str | None = None
    oos_hidden: bool = False
    page_size: int = PAGE_SIZE


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
    (None: every row, for the file), sorted by ``sort`` (``runs.SORTABLE``)."""
    page = max(page, 1)  # a page below the first is the first, and served as such
    basis = official_basis(ctx, edge)
    if basis.key is None or basis.run is None:
        return EdgeTradePage(period, page, basis.unknown)
    words = f"{basis.key[0]}, {basis.key[1]} trading days"
    offset = 0 if limit is None else (page - 1) * limit
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
