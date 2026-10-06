"""``Ideas``: one row per ticker the user's screeners picked for the session, ranked by their
screener priority, with every pick; and each screener with its run (or ``notRun``), its picked
count and best picks over the whole run (computed on the server, never from a page)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import ideas
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.screens.result import ScreenResult
from algotrade_api.graphql.types.screens.screener import Screener, ScreenerRun


@strawberry.type(
    description="One of the user's screeners on the Ideas page: its run for the session "
    "(else `notRun`: NOT_RUN), how many tickers it picked and its best picks, over the run"
)
class IdeaScreener:
    screener: Screener
    run: ScreenerRun | None
    not_run: Unknown | None
    picked: int
    top: list[ScreenResult]

    @classmethod
    def of(cls, d: ideas.IdeaScreener, ctx: ReadContext) -> Self:
        return cls(
            screener=Screener.of(d.screener, ctx),
            run=ScreenerRun.of(d.run, ctx) if d.run is not None else None,
            not_run=Unknown.of(d.not_run) if d.not_run is not None else None,
            picked=d.picked,
            top=[ScreenResult.of(r, ctx) for r in d.top],
        )


@strawberry.type(
    description="A ticker some screener picked: its picks, best screener first. `regime` and "
    "`sizeMultiplier`: the session's label and the size of its best pick, as the run stamped "
    "them (null: gate off, regime unknown, or a run before the stamp)"
)
class Idea:
    rank: int
    instrument_id: str
    instrument: Instrument | None
    picks: list[ScreenResult]
    regime: str | None
    size_multiplier: float | None

    @classmethod
    def of(cls, d: ideas.Idea, ctx: ReadContext) -> Self:
        return cls(
            rank=d.rank,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            picks=[ScreenResult.of(p, ctx) for p in d.picks],
            regime=d.regime,
            size_multiplier=d.size_multiplier,
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
    description="The ideas for the session: `screeners` in the user's priority order (then the "
    "rest by id), `items` the first `limit` of `total` picked tickers, `paused` the first `limit` "
    "of `pausedTotal` picks the regime gate held back (never counted in `total`)"
)
class Ideas:
    session: dt.date
    priority: list[str]
    screeners: list[IdeaScreener]
    total: int
    items: list[Idea]
    paused_total: int
    paused: list[PausedIdea]

    @classmethod
    def of(cls, d: ideas.Ideas, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            priority=list(d.priority),
            screeners=[IdeaScreener.of(s, ctx) for s in d.screeners],
            total=d.total,
            items=[Idea.of(i, ctx) for i in d.items],
            paused_total=d.paused_total,
            paused=[PausedIdea.of(p, ctx) for p in d.paused],
        )
