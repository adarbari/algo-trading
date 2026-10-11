"""``EdgeDesk`` (the Ideas signals of the edges a user follows) and ``EdgePaper`` (one edge's live
record, paper trades and forward test), ADR 0053 amendment 2026-10-09. Every figure, sentence and
bar of the picture is the read model's, for exactly the request's session; the browser derives and
filters nothing."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk import desk as desk_read
from algotrade.services.read.edge_desk import live as live_read
from algotrade.services.read.edge_desk import paper as paper_read
from algotrade.services.read.edge_desk import states as states_read
from algotrade_api.graphql.types.instruments.instrument import Instrument


@strawberry.type(
    description="One paper trade of an edge: `rank` 1 is the screener's best name, `status` open, "
    "won, lost or skipped (`reason` says why a skipped one is: never a loss), `excessReturn` "
    "only once settled (null while open), `delisted` measured to the name's last bar"
)
class PaperTrade:
    edge_id: str
    edge_name: str
    instrument_id: str
    instrument: Instrument | None
    screener: str
    rank: int
    signal_session: dt.date
    buy_session: dt.date
    sell_session: dt.date
    horizon_sessions: int
    status: str
    reason: str
    excess_return: float | None
    delisted: bool

    @classmethod
    def of(cls, d: paper_read.PaperTrade, ctx: ReadContext) -> Self:
        return cls(
            edge_id=d.edge_id,
            edge_name=d.edge_name,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            screener=d.screener,
            rank=d.rank,
            signal_session=d.signal_session,
            buy_session=d.buy_session,
            sell_session=d.sell_session,
            horizon_sessions=d.horizon_sessions,
            status=d.status,
            reason=d.reason,
            excess_return=d.excess_return,
            delisted=d.delisted,
        )


@strawberry.type(
    description="One bar of the picture: the win rates `start` to `end` and the `chance` (0 to 1) "
    "the live win rate falls there if the backtest's held"
)
class RangeBin:
    start: float
    end: float
    chance: float

    @classmethod
    def of(cls, d: live_read.RangeBin) -> Self:
        return cls(start=d.start, end=d.end, chance=d.chance)


@strawberry.type(
    description="An edge's live record over its closed paper trades. `state`: on_track, below or "
    "above the backtest's usual range (`low` to `high`: quantiles of the wins n closed trades "
    "would show if the backtest's win rate held), too_early (fewer than the site's minimum "
    "closed), no_backtest or no_trades. `backtestRate` and its `basis`; `bins` the picture; open "
    "and skipped trades are counted apart; `headline` the sentence"
)
class LiveRecord:
    state: str
    closed: int
    wins: int
    open: int
    skipped: int
    win_rate: float | None
    backtest_rate: float | None
    basis: str
    low: float | None
    high: float | None
    bins: list[RangeBin]
    headline: str

    @classmethod
    def of(cls, d: live_read.LiveRecord) -> Self:
        return cls(
            state=d.state,
            closed=d.closed,
            wins=d.wins,
            open=d.open,
            skipped=d.skipped,
            win_rate=d.win_rate,
            backtest_rate=d.backtest_rate,
            basis=d.basis,
            low=d.low,
            high=d.high,
            bins=[RangeBin.of(b) for b in d.bins],
            headline=d.headline,
        )


@strawberry.type(
    description="A trial's forward test: its record and the replaced edge's over the trades "
    "signalled from the trial's start, `sessions` of `needed` passed, and whether it `canReplace` "
    "the edge (the sessions have passed and it is not behind)"
)
class ForwardTest:
    replaces: str
    replaces_name: str
    since: dt.date
    sessions: int
    needed: int
    this: LiveRecord
    replaced: LiveRecord
    can_replace: bool
    headline: str

    @classmethod
    def of(cls, d: live_read.ForwardTest) -> Self:
        return cls(
            replaces=d.replaces,
            replaces_name=d.replaces_name,
            since=d.since,
            sessions=d.sessions,
            needed=d.needed,
            this=LiveRecord.of(d.this),
            replaced=LiveRecord.of(d.replaced),
            can_replace=d.can_replace,
            headline=d.headline,
        )


@strawberry.type(
    description="One edge's paper record as the session knew it: the live record, the trades "
    "(newest signal first) and, for a trial, the forward test"
)
class EdgePaper:
    edge_id: str
    record: LiveRecord
    trades: list[PaperTrade]
    forward: ForwardTest | None

    @classmethod
    def of(cls, d: live_read.EdgePaper, ctx: ReadContext) -> Self:
        return cls(
            edge_id=d.edge_id,
            record=LiveRecord.of(d.record),
            trades=[PaperTrade.of(t, ctx) for t in d.trades],
            forward=ForwardTest.of(d.forward) if d.forward is not None else None,
        )


@strawberry.type(
    description="An edge the user follows (or tries as a new version) and its record. `tonight` "
    "is what the nightly did for it on the session, so an empty buy list says why: signalled, "
    "no_picks (due, the screen qualified none), not_due, skipped (due but could not be "
    "signalled: `tonightReason`), not_recording (the nightly ran but the edge is not "
    "evidenced or live) or not_run (no nightly run for the session); `missed` the due "
    "sessions since the previous night that nobody signalled"
)
class FollowedEdge:
    edge_id: str
    name: str
    state: str
    since: dt.date | None
    record: LiveRecord
    tonight: str
    tonight_reason: str
    missed: list[dt.date]

    @classmethod
    def of(cls, d: desk_read.FollowedEdge) -> Self:
        return cls(
            edge_id=d.edge_id,
            name=d.name,
            state=d.state,
            since=d.since,
            record=LiveRecord.of(d.record),
            tonight=d.tonight,
            tonight_reason=d.tonight_reason,
            missed=list(d.missed),
        )


@strawberry.type(
    description="One edge's live state for the session, the word a list, a header and the Ideas "
    "banner show. `state` is the live record's: on_track, below or above the backtest's usual "
    "range (`low` to `high`), too_early (too few settled signal sessions), no_backtest or "
    "no_trades (no live record yet) or not_settled (the session's nightly has not completed: "
    "nothing is judged); `closed` settled trades, `wins`, `winRate`; `headline` the "
    "sentence; `term` the Guide entry that explains the state; `followed` the edge is on the "
    "user's desk (else a site edge the site records). Settled trades only, as the session's "
    "cutoff knew them"
)
class EdgeLiveState:
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

    @classmethod
    def of(cls, d: states_read.LiveState) -> Self:
        return cls(
            edge_id=d.edge_id,
            name=d.name,
            state=d.state,
            closed=d.closed,
            wins=d.wins,
            win_rate=d.win_rate,
            low=d.low,
            high=d.high,
            headline=d.headline,
            term=d.term,
            followed=d.followed,
        )


@strawberry.type(
    description="The Ideas signals of the edges the user follows for the session: `buys` the "
    "paper trades signalled on it, `sells` the open ones whose window closes at `sellSession` "
    "(the next session), `followed` every followed edge with its record, `liveStates` "
    "the live state of every edge with a record (the followed ones and the site's). Empty lists "
    "with no followed edge; `liveStates` still names the site's edges"
)
class EdgeDesk:
    session: dt.date
    sell_session: dt.date
    buys: list[PaperTrade]
    sells: list[PaperTrade]
    followed: list[FollowedEdge]
    live_states: list[EdgeLiveState]

    @classmethod
    def of(cls, d: desk_read.EdgeDesk, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            sell_session=d.sell_session,
            buys=[PaperTrade.of(t, ctx) for t in d.buys],
            sells=[PaperTrade.of(t, ctx) for t in d.sells],
            followed=[FollowedEdge.of(f) for f in d.followed],
            live_states=[EdgeLiveState.of(s) for s in d.live_states],
        )
