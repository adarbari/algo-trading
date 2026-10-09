"""The Ideas signals of the edges a user follows (ADR 0053 amendment 2026-10-09) for one session:
what to buy (the paper trades the nightly signalled for the session), what to sell next session
(the open trades whose window closes then) and how each followed edge is doing (its live record).

A buy or a sell is the stored paper record, never derived here (``paper.py``); a followed edge
with no trade yet says so. D4: a sell shows ahead or behind only once settled (an open trade has
no mark), which is why the list carries no return."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.site.settings import load_verdict
from algotrade.core.time.calendar import next_session
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.live import LiveRecord, live_record
from algotrade.services.read.edge_desk.paper import OPEN, PaperTrade, load_trades, with_instruments
from algotrade.services.read.evaluation.edges import load_edges

FOLLOWING = ("following", "trial")


@dataclass(frozen=True)
class FollowedEdge:
    """A followed edge (``state`` following or trial since ``since``) and its live record."""

    edge_id: str
    name: str
    state: str
    since: date | None
    record: LiveRecord


@dataclass(frozen=True)
class EdgeDesk:
    """``buys``: the trades signalled on the session; ``sells``: the open trades whose sell
    session is the next one (``sell_session``); ``followed``: every edge the user follows or
    tries, with its record."""

    session: date
    sell_session: date
    buys: tuple[PaperTrade, ...]
    sells: tuple[PaperTrade, ...]
    followed: tuple[FollowedEdge, ...]


def load_edge_desk(ctx: ReadContext) -> EdgeDesk:
    """The desk for ``ctx.session``."""
    day = ctx.session.date
    edges = {e.id: e for e in load_edges(ctx)}
    followed = [e for e in edges.values() if e.state in FOLLOWING]
    nxt = next_session(day)
    if not followed:
        return EdgeDesk(day, nxt, (), (), ())
    trades = load_trades(ctx, {i: e.name for i, e in edges.items()})
    settings = load_verdict(ctx.configs)
    buys = with_instruments(ctx, tuple(t for t in trades if t.signal_session == day))
    sells = with_instruments(
        ctx, tuple(t for t in trades if t.status == OPEN and t.sell_session == nxt)
    )
    records = tuple(
        FollowedEdge(
            e.id, e.name, e.state, e.since,
            live_record(ctx, e, [t for t in trades if t.edge_id == e.id], settings),
        )
        for e in followed
    )  # fmt: skip
    return EdgeDesk(day, nxt, buys, sells, records)
