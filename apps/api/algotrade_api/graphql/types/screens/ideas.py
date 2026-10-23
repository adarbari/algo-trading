"""``Ideas``: one row per ticker the user's screeners picked for the session, ranked by the
Ideas rule (services/ideas), served from its best pick with the screeners that picked it; and each
screener with its run (or ``notRun``), its picked count and first picks over the whole run
(computed on the server, never from a page)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import ideas
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.screens.result import ScreenResult
from algotrade_api.graphql.types.screens.screener import Screener, ScreenerRun


@strawberry.type(
    description="One of a screener's first picks: who it is, its `position` in the screener's "
    "run and the `score` the run stored for it (null: none stored)"
)
class TopPick:
    instrument_id: str
    instrument: Instrument | None
    position: int
    score: float | None

    @classmethod
    def of(cls, d: ideas.TopPick, ctx: ReadContext) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            position=d.position,
            score=d.score,
        )


@strawberry.type(
    description="One of the user's screeners on the Ideas page: its run for the session "
    "(else `notRun`: NOT_RUN), how many tickers it picked over the run, its first picks that "
    "count towards the ideas (`top`) and `withheld`: its run's order follows values the "
    "viewer's data licences do not cover, so it contributes no idea and lists no pick"
)
class IdeaScreener:
    screener: Screener
    run: ScreenerRun | None
    not_run: Unknown | None
    picked: int
    top: list[TopPick]
    withheld: bool

    @classmethod
    def of(cls, d: ideas.IdeaScreener, ctx: ReadContext) -> Self:
        return cls(
            screener=Screener.of(d.screener, ctx),
            run=ScreenerRun.of(d.run, ctx) if d.run is not None else None,
            not_run=Unknown.of(d.not_run) if d.not_run is not None else None,
            picked=d.picked,
            top=[TopPick.of(r, ctx) for r in d.top],
            withheld=d.withheld,
        )


@strawberry.type(
    description="One screener's pick of an idea: its `position` in the screener's run, the "
    "`score` it earns under the Ideas rule (weight over position: a site screener's first pick "
    "is 1, the viewer's own screener weighs 3) and the `decision` it gave"
)
class PickedBy:
    config_id: str
    owner: str
    own: bool
    position: int
    score: float
    decision: str

    @classmethod
    def of(cls, d: ideas.PickedBy) -> Self:
        return cls(
            config_id=d.config_id,
            owner=d.owner,
            own=d.own,
            position=d.position,
            score=d.score,
            decision=d.decision,
        )


@strawberry.type(
    description="A stored display value of an idea's best pick: a screener column or a "
    "criterion's value, by name"
)
class IdeaMetric:
    name: str
    value: JSON

    @classmethod
    def of(cls, d: ideas.IdeaMetric) -> Self:
        return cls(name=d.name, value=JSON(d.value))


@strawberry.type(
    description="A ticker some screener picked, served from its `best` pick only. `score`: that "
    "pick's, the idea's place in the list; `pickedBy`: every screener that picked it, the best "
    "first; `metrics` and `watchOut` (ids: flags, `liquidity_risk`, `earnings_before_expiry`) "
    "are the best pick's; `regime` and `sizeMultiplier`: the session's label and the size of "
    "the best pick, as the run stamped them (null: gate off, regime unknown, or a run before "
    "the stamp)"
)
class Idea:
    rank: int
    instrument_id: str
    instrument: Instrument | None
    score: float
    best: ScreenResult
    picked_by: list[PickedBy]
    regime: str | None
    size_multiplier: float | None
    metrics: list[IdeaMetric]
    watch_out: list[str]

    @classmethod
    def of(cls, d: ideas.Idea, ctx: ReadContext) -> Self:
        return cls(
            rank=d.rank,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            score=d.score,
            best=ScreenResult.of(d.best, ctx),
            picked_by=[PickedBy.of(p) for p in d.picked_by],
            regime=d.regime,
            size_multiplier=d.size_multiplier,
            metrics=[IdeaMetric.of(m) for m in d.metrics],
            watch_out=list(d.watch_out),
        )


@strawberry.type(
    description="A ticker one screener picked and the regime gate held back: that screener's "
    "PAUSED row, whose `reasons` say why"
)
class PausedIdea:
    instrument_id: str
    instrument: Instrument | None
    result: ScreenResult

    @classmethod
    def of(cls, d: ideas.PausedIdea, ctx: ReadContext) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            result=ScreenResult.of(d.result, ctx),
        )


@strawberry.type(
    description="The ideas for the session: `screeners` (the user's own first, then by id), "
    "`items` one page of the `total` ideas (`nextCursor`, for the `after` "
    "argument, starts the next; null on the last page, `hasMore` false), `paused` the first "
    "`first` of `pausedTotal` picks the regime gate held back on the first page only (never "
    "counted in `total`)"
)
class Ideas:
    session: dt.date
    screeners: list[IdeaScreener]
    total: int
    items: list[Idea]
    paused_total: int
    paused: list[PausedIdea]
    next_cursor: str | None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Whether another page follows this one"
    )
    def has_more(self) -> bool:
        return self.next_cursor is not None

    @classmethod
    def of(cls, d: ideas.Ideas, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            screeners=[IdeaScreener.of(s, ctx) for s in d.screeners],
            total=d.total,
            items=[Idea.of(i, ctx) for i in d.items],
            paused_total=d.paused_total,
            paused=[PausedIdea.of(p, ctx) for p in d.paused],
            next_cursor=d.next_cursor,
        )
