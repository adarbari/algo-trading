"""The Ideas signals of the edges a user follows (ADR 0053 amendment 2026-10-09) for one session:
what to buy (the paper trades the nightly signalled for the session), what to sell next session
(the open trades whose window closes then) and how each followed edge is doing (its live record).

A buy or a sell is the stored paper record, never derived here (``paper.py``); a followed edge
with no trade yet says so. D4: a sell shows ahead or behind only once settled (an open trade has
no mark), which is why the list carries no return."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.config.site.settings import load_verdict
from algotrade.core.time.calendar import next_session
from algotrade.data.paper import job_name
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.live import LiveRecord, live_record
from algotrade.services.read.edge_desk.paper import OPEN, PaperTrade, load_trades, with_instruments
from algotrade.services.read.evaluation.edges import load_edges
from algotrade.storage.runs import RunStatus

FOLLOWING = ("following", "trial")
SIGNALLED, NO_PICKS, NOT_DUE, SKIPPED, NOT_RUN = (
    "signalled", "no_picks", "not_due", "skipped", "not_run",
)  # fmt: skip


def _night(ctx: ReadContext) -> dict[str, Any] | None:
    """The stats of the user's committed ``edge-paper`` run for exactly the session (None: the
    nightly did not run it)."""
    day = ctx.session.date
    found = [
        r
        for r in ctx.reader.runs(job_name(ctx.user.user_id))
        if r.session_date == day and r.status is RunStatus.COMPLETE
    ]
    return max(found, key=lambda r: r.finished_at or r.started_at).stats if found else None


def _tonight(night: dict[str, Any] | None, edge_id: str) -> tuple[str, str]:
    said = (night or {}).get("tonight", {}).get(edge_id)
    if not isinstance(said, dict):
        return NOT_RUN, ""
    return str(said.get("state", NOT_RUN)), str(said.get("reason", ""))


def _missed(night: dict[str, Any] | None, edge_id: str) -> tuple[date, ...]:
    return tuple(
        date.fromisoformat(m["session"])
        for m in (night or {}).get("missed", [])
        if isinstance(m, dict) and m.get("edge") == edge_id
    )


@dataclass(frozen=True)
class FollowedEdge:
    """A followed edge (``state`` following or trial since ``since``) and its live record.
    ``tonight`` is what the nightly did for it on the session, so an empty buy list says why:
    ``signalled``, ``no_picks`` (due, the screen qualified none), ``not_due`` (its schedule does
    not fire), ``skipped`` (due but could not be signalled: ``tonight_reason`` says why) or
    ``not_run`` (no nightly run for the session). ``missed``: due sessions since the previous
    night that nobody signalled."""

    edge_id: str
    name: str
    state: str
    since: date | None
    record: LiveRecord
    tonight: str
    tonight_reason: str
    missed: tuple[date, ...]


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
    night = _night(ctx)
    records = tuple(
        FollowedEdge(
            e.id, e.name, e.state, e.since,
            live_record(ctx, e, [t for t in trades if t.edge_id == e.id], settings),
            *_tonight(night, e.id), _missed(night, e.id),
        )
        for e in followed
    )  # fmt: skip
    return EdgeDesk(day, nxt, buys, sells, records)
