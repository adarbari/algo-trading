"""An edge's live stroke: its settled paper trades on the basis, laid on the backtest's curve
(ADR 0064 decision 9, ADR 0053: the stored record is never re-derived from today's document).

The trades are ``edge_desk.paper.load_trades`` as the resolved session knew them: a trade whose
sell session is after it is open, whatever a later night recorded, and open and skipped trades
are no point. Of the edge's trades only the basis's screen and holding period count. Each signal
session is ONE point at its sell session: the mean excess return of its settled trades (a
return outcome), or the wins above what the series' base rate at the same decision session
predicts (any other outcome; a session the series has no row for is no point: never a base rate
made up). The stroke is anchored SERVER SIDE at the backtest's cumulative value at the record's
first signal, so the browser adds nothing and the gap between the lines is the drift.

The same out-of-sample rules as the backtest: a copy whose out-of-sample result is hidden shows
no live stroke (``oos_hidden``): its paper trades are out of sample."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Final

from algotrade.quant.edges import paths
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.paper import LOST, WON, PaperTrade, load_trades
from algotrade.services.read.edge_evidence.series import BasisSeries
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import window_weights

RECORDED, NONE, OOS_HIDDEN = "recorded", "none", "oos_hidden"
LIVE_STATES: Final = (RECORDED, NONE, OOS_HIDDEN)


@dataclass(frozen=True)
class LivePoint:
    """One signal session's settled trades, plotted at their ``sell`` session: ``value`` the
    session's (mean excess return, or wins above the base rate), ``cumulative`` the stroke so far
    from its anchor, ``trades`` how many settled."""

    sell: date
    value: float
    cumulative: float
    trades: int


@dataclass(frozen=True)
class EdgeLive:
    """The live stroke: ``state`` (``recorded``: trades have settled, ``points`` may be fewer
    than ``sessions`` when a session has nothing to value; ``none``: no settled trade of the
    basis yet; ``oos_hidden``: a copy's out-of-sample result is withheld), ``since`` the first
    signal session of the settled record, ``anchor`` the backtest's cumulative value it starts from,
    ``closed`` settled trades over ``sessions`` signal sessions, ``points`` by sell session."""

    state: str
    since: date | None = None
    anchor: float | None = None
    closed: int = 0
    sessions: int = 0
    points: tuple[LivePoint, ...] = ()


def settled_trades(ctx: ReadContext, edge: Edge, series: BasisSeries) -> list[PaperTrade]:
    """The settled paper trades of ``edge`` on the basis's screen and holding period, as the
    session knew them (open and skipped ones are not settled)."""
    screen, horizon = series.key
    return [
        t
        for t in load_trades(ctx, {edge.id: edge})
        if t.edge_id == edge.id
        and t.screener == screen
        and t.horizon_sessions == horizon
        and t.status in (WON, LOST)
    ]


def by_signal_session(trades: list[PaperTrade]) -> dict[date, list[PaperTrade]]:
    """``trades`` grouped by signal session, in session order."""
    found: dict[date, list[PaperTrade]] = {}
    for t in sorted(trades, key=lambda t: (t.signal_session, t.rank, t.instrument_id)):
        found.setdefault(t.signal_session, []).append(t)
    return found


def _bases(series: BasisSeries) -> dict[date, tuple[int, int]]:
    """The series' ``(base_hits, eligible)`` at each decision session it measured."""
    return {
        w.row.decision_session: (w.row.base_hits, w.row.eligible)
        for w in series.windows
        if w.row.base_hits is not None and w.row.eligible
    }


def session_value(
    trades: list[PaperTrade], series: BasisSeries, base: tuple[int, int] | None
) -> float | None:
    """One signal session's value: the mean excess return of its settled trades in a return
    outcome, else its wins above the base rate ``base`` (``(base_hits, eligible)``); None when
    the session has nothing to value (no return stored, or no base rate)."""
    if series.is_return:
        found = [t.excess_return for t in trades if t.excess_return is not None]
        return sum(found) / len(found) if found else None
    if base is None:
        return None
    wins = sum(t.status == WON for t in trades)
    return float(paths.excess_wins([wins], [len(trades)], [base[0]], [base[1]])[0])


def load_live(
    ctx: ReadContext, edge: Edge, series: BasisSeries, anchor_at: Callable[[date], float]
) -> EdgeLive:
    """The live stroke of ``edge`` on the basis ``series``; ``anchor_at(day)``: the backtest's
    cumulative value at ``day``."""
    if series.hidden:
        return EdgeLive(OOS_HIDDEN)
    sessions = by_signal_session(settled_trades(ctx, edge, series))
    if not sessions:
        return EdgeLive(NONE)
    bases = _bases(series)
    weights = window_weights(
        sessions, series.horizon
    )  # overlapping signals count as the curve's do
    valued = [
        (max(t.sell_session for t in trades), signal, len(trades), v * weights[signal])
        for signal, trades in sessions.items()
        if (v := session_value(trades, series, bases.get(signal))) is not None
    ]
    first = min(sessions)
    anchor = anchor_at(first)
    running = anchor
    points: list[LivePoint] = []
    for sell, _signal, n, value in sorted(valued):
        running += value
        points.append(LivePoint(sell, value, running, n))
    return EdgeLive(
        RECORDED,  # settled trades exist; a session with nothing to value is just no point
        since=first,
        anchor=anchor,
        closed=sum(len(t) for t in sessions.values()),
        sessions=len(sessions),
        points=tuple(points),
    )
