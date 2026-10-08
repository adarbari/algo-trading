"""``Market``: the market the regime describes (``MKT:US``) for the session, and its values by
catalogue name (``features(names)``, ADR 0047): the market-entity groups'
``market.<group>@vN.<col>`` fields, each a ``FeatureValue`` (the instrument value type) for
exactly the session, and ``history(names, start, end, points)``: stored fields over a window,
bucketed (numbers) or merged into segments (flags, labels) on the server."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.market import buckets, market
from algotrade.services.read.market import history as history_read
from algotrade.services.read.market.features import load_market_feature_values
from algotrade_api.graphql.limits import MAX_NAMES, MaxItems
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.instruments.feature import FeatureValue


@strawberry.type(description="One point of a numeric history; `value` null is a gap")
class HistoryPoint:
    session: dt.date
    value: float | None

    @classmethod
    def of(cls, d: buckets.Point) -> Self:
        return cls(session=d.session, value=d.value)


@strawberry.type(
    description="Consecutive sessions `start..end` (the first and last of the run) with one "
    "`value`: ON / OFF / UNKNOWN for a flag, the label text for a label, UNKNOWN where "
    "nothing is stored"
)
class HistorySegment:
    start: dt.date
    end: dt.date
    value: str

    @classmethod
    def of(cls, d: buckets.Segment) -> Self:
        return cls(start=d.start, end=d.end, value=d.value)


@strawberry.type(
    description="One market field over a window. A number: `points` (oldest first), one "
    "bucket of `bucketSessions` consecutive sessions yielding its minimum and its maximum at "
    "their own sessions; a null `value` is a gap that breaks the line; `segments` is empty. A "
    "flag or a label: `segments`, `points` empty, `bucketSessions` 1"
)
class SeriesHistory:
    name: str
    bucket_sessions: int
    points: list[HistoryPoint]
    segments: list[HistorySegment]

    @classmethod
    def of(cls, d: history_read.SeriesHistory) -> Self:
        return cls(
            name=d.name,
            bucket_sessions=d.bucket_sessions,
            points=[HistoryPoint.of(p) for p in d.points],
            segments=[HistorySegment.of(s) for s in d.segments],
        )


@strawberry.type(
    description="A market (`marketId` `MKT:US`) for the session. Per-session values (breadth, "
    "trend, the regime's inputs) are market catalogue features: `features(names)`"
)
class Market:
    session: dt.date
    market_id: str
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: market.Market, ctx: ReadContext) -> Self:
        return cls(session=d.session, market_id=d.market_id, ctx=ctx)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The values of `names` (market catalogue fields: "
        "`market.<group>@v<N>.<column>`, or a `feature.<name>` over them; in the order "
        "asked) for the session; a name outside the market's catalogue is an UNKNOWN_FEATURE "
        "error",
        extensions=[MaxItems("names", MAX_NAMES)],
    )
    async def features(self, info: Info, names: list[str]) -> list[FeatureValue]:
        found = await off_loop(load_market_feature_values, self.ctx, names)  # reads partitions
        return [FeatureValue.of(v) for v in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The history of `names` (stored market fields only: `market.<group>@v<N>."
        "<column>`; a `feature.*` name is a BAD_REQUEST, it would be computed for thousands of "
        "sessions) over the exchange sessions of `start..end` (`end` is cut to the session's "
        "date), each session from its own partition: one with no stored row is a gap, never "
        "carried forward. Numbers come as at most `points` points (2 to 5000); flags and labels "
        "as `segments`",
        extensions=[MaxItems("names", MAX_NAMES)],
    )
    async def history(
        self, info: Info, names: list[str], start: dt.date, end: dt.date, points: int = 600
    ) -> list[SeriesHistory]:
        # Off the event loop: a range read of one partition per session.
        found = await off_loop(
            history_read.load_market_history, self.ctx, names, start, end, points
        )
        return [SeriesHistory.of(h) for h in found]
