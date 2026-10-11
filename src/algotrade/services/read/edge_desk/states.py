"""Every edge's live state for the session: the one word a list, a header and the Ideas banner
show (ADR 0064 decision 9).

The state is the live record's own (``live.live_record``: the settled paper trades judged against
the backtest's usual range by ``VerdictSettings`` ``live_min_sessions`` / ``live_low`` /
``live_high``), never judged again here: ``on_track``, ``below`` or ``above`` the range,
``too_early`` (too few settled signal sessions), ``no_backtest`` or ``no_trades`` (no live
record), or ``not_recording`` (the edge records no paper trades: a candidate, never judged, never
read). Every edge has a state; the ones with a paper record to speak of (``is_recording``) are the
ones on the user's desk (followed, or their own evidenced or live) and every site edge the site
records. Each state
carries its Guide term (``TERMS``) so a page shows it only through ``InfoButton``; the trades are
read as ``paper.load_trades`` reads them (the rows as the session's cutoff knew them). Nothing is
pushed or sent: ``below_range`` only lists what the nightly's run record says in one line."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from algotrade.config.edges.loading import RECORDING
from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.live import (
    ABOVE,
    BELOW,
    NO_BACKTEST,
    NO_TRADES,
    ON_TRACK,
    TOO_EARLY,
    live_record,
)
from algotrade.services.read.edge_desk.paper import PaperTrade, load_trades, record_owner
from algotrade.services.read.evaluation.edges import Edge, load_edges

NOT_SETTLED = "not_settled"  # the session's nightly has not completed: nothing is judged
NOT_RECORDING = "not_recording"  # a candidate: paper trades start once it is evidenced
LIVE_STATES = (
    ON_TRACK, BELOW, ABOVE, TOO_EARLY, NO_BACKTEST, NO_TRADES, NOT_SETTLED, NOT_RECORDING
)  # fmt: skip
TERM = "live_state"  # the Guide glossary entry that explains every state


@dataclass(frozen=True)
class LiveState:
    """One edge's live state: ``state`` (one of ``LIVE_STATES``), the settled trades behind it
    (``closed``, ``wins``, ``win_rate``), the usual range (``low`` / ``high``, None until it is
    judged), the server's ``headline`` and the Guide ``term`` that explains the state;
    ``followed``: the edge is on the user's desk (else a site edge the user does not follow)."""

    edge_id: str
    name: str
    state: str
    closed: int
    wins: int
    win_rate: float | None
    low: float | None
    high: float | None
    headline: str
    term: str
    followed: bool


def is_recording(edge: Edge) -> bool:
    """The edge records paper trades: the nightly records only evidenced or live edges (a
    follow records nothing)."""
    return edge.status in RECORDING


def live_edges(edges: Mapping[str, Edge]) -> dict[str, Edge]:
    """The edges with a paper record to read (see ``is_recording``), by id."""
    return {i: e for i, e in edges.items() if is_recording(e)}


def _not_recording(edge: Edge) -> LiveState:
    when = "you set it live" if edge.mine else "it is evidenced"
    return LiveState(
        edge.id, edge.name, NOT_RECORDING, 0, 0, None, None, None,
        f"No paper trades are recorded: they start when {when}.", TERM, False,
    )  # fmt: skip


def load_live_states(
    ctx: ReadContext, edges: Mapping[str, Edge], trades: Sequence[PaperTrade]
) -> tuple[LiveState, ...]:
    """The live state of each of ``edges`` over ``trades`` (``load_trades`` of the recording ones),
    sorted by edge name: an edge that records no paper trades is ``not_recording``."""
    settings = load_verdict(ctx.configs)
    states = []
    for edge in edges.values():
        if not is_recording(edge):
            states.append(_not_recording(edge))
            continue
        if ctx.session.cutoff is None:
            states.append(
                LiveState(
                    edge.id, edge.name, NOT_SETTLED, 0, 0, None, None, None,
                    "The session's nightly has not completed: its paper results are not settled.",
                    TERM, edge.paper_traded,
                )
            )  # fmt: skip
            continue
        record = live_record(ctx, edge, [t for t in trades if t.edge_id == edge.id], settings)
        states.append(
            LiveState(
                edge.id, edge.name, record.state, record.closed, record.wins, record.win_rate,
                record.low, record.high, record.headline, TERM, edge.paper_traded,
            )
        )  # fmt: skip
    return tuple(sorted(states, key=lambda s: (s.name, s.edge_id)))


def below_range(ctx: ReadContext, cutoff: datetime | None = None) -> tuple[LiveState, ...]:
    """The edges below their usual range whose paper record ``ctx.user`` owns (a site edge for
    ``site``, else the user's own): what the nightly's run record names, one line each, so a site
    edge is said once, by the site's job, and never again by each follower's. ``cutoff``: the
    moment to read as (the nightly's own step runs before its session completes, so it passes
    now)."""
    if cutoff is not None:
        ctx = replace(ctx, session=replace(ctx.session, cutoff=cutoff))
    edges = {e.id: e for e in load_edges(ctx)}
    mine = {
        i: e
        for i, e in live_edges(edges).items()
        if record_owner(e, ctx.user.user_id) == ctx.user.user_id
    }
    if not mine:
        return ()
    states = load_live_states(ctx, mine, load_trades(ctx, mine))
    return tuple(s for s in states if s.state == BELOW)
