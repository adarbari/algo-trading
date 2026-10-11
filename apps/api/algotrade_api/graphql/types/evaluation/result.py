"""``EdgeResult`` (the sections of an edge's result page, ADR 0064, ADR 0065): the evidence curve
with its live stroke, the drawdown, the rolling starts, the monthly map and the decay with its
live bar, every one about the SAME run and basis as the verdict (``edge_evidence.basis``: never
passed in, so a page cannot mismatch them). Each section is a lazily resolved field, so a page
that selects one reads only its rows; the run's series is read once per request and shared.
A section with nothing to show carries an ``unknown`` (public kind and Guide term; the chain
behind it, and the table a lost input lost, only for an admin): never an empty list or a zero.
Every number and sentence is the read model's; the browser derives nothing."""

import asyncio
import datetime as dt
from typing import Any, Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_evidence import (
    capacity,
    costs,
    curve,
    decay,
    drawdown,
    live,
    rolling,
)
from algotrade.services.read.edge_evidence.basis import (
    BasisSummary,
    OfficialBasis,
    official_basis,
    summary_of,
)
from algotrade.services.read.edge_evidence.series import BasisSeries, load_basis_series
from algotrade.services.read.edge_evidence.slices import horizons, regimes
from algotrade.services.read.evaluation import edges
from algotrade.services.read.values import Unknown as ReadUnknown
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.evaluation.edge_costs import EdgeCapacity, EdgeCosts
from algotrade_api.graphql.types.evaluation.edge_slices import EdgeHorizons, EdgeRegimes
from algotrade_api.graphql.types.evaluation.verdict import EdgeDecay
from algotrade_api.graphql.types.instruments.feature import Unknown


def _unknown(found: ReadUnknown | None) -> Unknown | None:
    return Unknown.of(found) if found is not None else None


@strawberry.type(
    description="One window of the curve: decided at `decision`, known at `exit` (the x: never "
    "the decision), on `period`'s side of the split (in_sample, out_of_sample, or all for a run "
    "with no split), its `value` and the `cumulative` curve; `baseValue` and `baseCumulative` "
    "the field's (null: no base line, or not stored; a window with no base value leaves it null "
    "there); `trades` its picks; `weight` its share in the sums (below 1 where windows overlap): "
    "`value` and the cumulatives are weighted"
)
class CurvePoint:
    decision: dt.date
    exit: dt.date
    period: str
    value: float
    cumulative: float
    base_value: float | None
    base_cumulative: float | None
    trades: int
    weight: float

    @classmethod
    def of(cls, d: curve.CurvePoint) -> Self:
        return cls(
            decision=d.decision,
            exit=d.exit,
            period=d.period,
            value=d.value,
            cumulative=d.cumulative,
            base_value=d.base_value,
            base_cumulative=d.base_cumulative,
            trades=d.trades,
            weight=d.weight,
        )


@strawberry.type(
    description="A span of windows that hold no number, `from` to `to` (exit sessions, the "
    "curve's x), and why in public words "
    "(`kind`: excluded_coverage, lost_input, no_picks). The line joins over it; it is never a "
    "zero. `unknown` is set for lost_input: its admin cause names the table the screen lost"
)
class CurveGap:
    start: dt.date = strawberry.field(name="from")
    end: dt.date = strawberry.field(name="to")
    kind: str
    unknown: Unknown | None

    @classmethod
    def of(cls, d: curve.CurveGap) -> Self:
        return cls(start=d.start, end=d.end, kind=d.kind, unknown=_unknown(d.unknown))


@strawberry.type(
    description="One signal session of the live stroke: its settled trades plotted at their "
    "`sell` session with the session's `value` and the `cumulative` stroke from its anchor"
)
class LivePoint:
    sell: dt.date
    value: float
    cumulative: float
    trades: int

    @classmethod
    def of(cls, d: live.LivePoint) -> Self:
        return cls(sell=d.sell, value=d.value, cumulative=d.cumulative, trades=d.trades)


@strawberry.type(
    description="The live stroke: the edge's settled paper trades on the basis, as the session "
    "knew them, laid on the curve. `state`: recorded (trades have settled; `points` can be "
    "fewer than `sessions`), none (no settled trade yet) or oos_hidden "
    "(a copy's out-of-sample result is withheld). `since` the first signal session, `anchor` the "
    "backtest's cumulative value it starts from (added by the server), `closed` settled trades "
    "over `sessions` signal sessions"
)
class EdgeLive:
    state: str
    since: dt.date | None
    anchor: float | None
    closed: int
    sessions: int
    points: list[LivePoint]

    @classmethod
    def of(cls, d: live.EdgeLive) -> Self:
        return cls(
            state=d.state,
            since=d.since,
            anchor=d.anchor,
            closed=d.closed,
            sessions=d.sessions,
            points=[LivePoint.of(p) for p in d.points],
        )


@strawberry.type(
    description="The evidence curve of the verdict's basis: what its picks earned, window by "
    "window, added up (`kind` cumulative_excess in a return `unit`; excess_wins for an outcome "
    "with no return: wins above what the base rate predicts), against what the field earned. "
    "`splitFrom` where the out-of-sample side starts, `hidden` a copy's withheld out-of-sample "
    "result (the points are in-sample only), `gaps` the spans that hold no number and `live` the "
    "settled paper trades. `unknown`: why there is no curve (then the rest is empty)"
)
class EdgeCurve:
    kind: str | None
    unit: str | None
    split_from: dt.date | None
    hidden: bool
    points: list[CurvePoint]
    gaps: list[CurveGap]
    live: EdgeLive | None
    unknown: Unknown | None

    @classmethod
    def of(cls, d: curve.EdgeCurve) -> Self:
        return cls(
            kind=d.kind,
            unit=d.unit,
            split_from=d.split_from,
            hidden=d.hidden,
            points=[CurvePoint.of(p) for p in d.points],
            gaps=[CurveGap.of(g) for g in d.gaps],
            live=EdgeLive.of(d.live) if d.live is not None else None,
            unknown=_unknown(d.unknown),
        )


@strawberry.type(
    description="The curve's distance below its running high at `exit`: `depth` is 0 or negative"
)
class UnderwaterPoint:
    exit: dt.date
    depth: float

    @classmethod
    def of(cls, d: drawdown.UnderwaterPoint) -> Self:
        return cls(exit=d.exit, depth=d.depth)


@strawberry.type(
    description="One drop of the curve: from the high at `peak` down `depth` (positive) to "
    "`trough` and back to `recovered` (null: not yet)"
)
class DrawdownEpisode:
    peak: dt.date
    trough: dt.date
    recovered: dt.date | None
    depth: float

    @classmethod
    def of(cls, d: drawdown.DrawdownEpisode) -> Self:
        return cls(peak=d.peak, trough=d.trough, recovered=d.recovered, depth=d.depth)


@strawberry.type(
    description="How far the curve fell and how much it moves: the `points` below its high, its "
    "deepest `episodes`, the deepest drop of each side of the split (`maxInSample`, "
    "`maxOutOfSample`: positive; the out-of-sample side from its own first window) and the "
    "annualised volatility of the windows of each side (null: fewer than two windows). Measured "
    "on the per-window curve, so it understates a dip inside a window. `state`: measured, "
    "not_a_return (the outcome has no return to fall) or not_stored (no series: `unknown` says "
    "why)"
)
class EdgeDrawdown:
    state: str
    unit: str | None
    points: list[UnderwaterPoint]
    episodes: list[DrawdownEpisode]
    max_in_sample: float | None
    max_out_of_sample: float | None
    vol_in_sample: float | None
    vol_out_of_sample: float | None
    unknown: Unknown | None

    @classmethod
    def of(cls, d: drawdown.EdgeDrawdown) -> Self:
        return cls(
            state=d.state,
            unit=d.unit,
            points=[UnderwaterPoint.of(p) for p in d.points],
            episodes=[DrawdownEpisode.of(e) for e in d.episodes],
            max_in_sample=d.max_in_sample,
            max_out_of_sample=d.max_out_of_sample,
            vol_in_sample=d.vol_in_sample,
            vol_out_of_sample=d.vol_out_of_sample,
            unknown=_unknown(d.unknown),
        )


@strawberry.type(
    description="The windows decided from `start` (a January 1st) to the end: `trades` of them, "
    "their pooled `liftPts` (win rate minus base rate, in points) and, for a return outcome, "
    "their mean `meanExcess`"
)
class EdgeRollingStart:
    start: dt.date
    trades: int
    lift_pts: float | None
    mean_excess: float | None

    @classmethod
    def of(cls, d: rolling.RollingStart) -> Self:
        return cls(start=d.start, trades=d.trades, lift_pts=d.lift_pts, mean_excess=d.mean_excess)


@strawberry.type(
    description="The lift from the start of each calendar year forward, earliest first: how the "
    "result depends on when you began. `unknown`: why there are none"
)
class EdgeRollingStarts:
    unit: str | None
    starts: list[EdgeRollingStart]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: rolling.EdgeRollingStarts) -> Self:
        return cls(
            unit=d.unit,
            starts=[EdgeRollingStart.of(s) for s in d.starts],
            unknown=_unknown(d.unknown),
        )


@strawberry.type(
    description="One calendar `month` (its first day): the sum of the `value` of the `trades` "
    "(windows) that closed in it, on `period`'s side of the split (both: it holds both)"
)
class EdgeMonth:
    month: dt.date
    value: float
    trades: int
    period: str

    @classmethod
    def of(cls, d: rolling.MonthRow) -> Self:
        return cls(month=d.month, value=d.value, trades=d.trades, period=d.period)


@strawberry.type(
    description="What the curve gained or lost in each calendar month (the heat map), earliest "
    "first, in `unit`. `unknown`: why there are none"
)
class EdgeMonthly:
    unit: str | None
    months: list[EdgeMonth]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: rolling.EdgeMonthly) -> Self:
        return cls(
            unit=d.unit, months=[EdgeMonth.of(m) for m in d.months], unknown=_unknown(d.unknown)
        )


@strawberry.type(
    description="The run and the basis every section of the result reads: the verdict's own "
    "(the declared screen and holding period, else the best in-sample, fixed before the "
    "out-of-sample period was read). `variant` and `horizonSessions` are null with no basis "
    "(`unknown` says why); `splitFrom` where the run's out-of-sample side starts; `oosHidden` a "
    "copy's out-of-sample result is withheld"
)
class ResultBasis:
    run_id: str | None
    variant: str | None
    horizon_sessions: int | None
    split_from: dt.date | None
    oos_hidden: bool
    unknown: Unknown | None

    @classmethod
    def of(cls, d: BasisSummary) -> Self:
        return cls(
            run_id=d.run_id,
            variant=d.variant,
            horizon_sessions=d.horizon_sessions,
            split_from=d.split_from,
            oos_hidden=d.oos_hidden,
            unknown=_unknown(d.unknown),
        )


@strawberry.type(
    description="The sections of an edge's result, each about the verdict's own run and basis. "
    "Select only the sections the page shows: each is read on its own. `date` of the query "
    "resolves the session only for the live stroke and the live bar (ADR 0036): the backtest "
    "part is read by run"
)
class EdgeResult:
    id: str
    edge: strawberry.Private[edges.Edge]
    ctx: strawberry.Private[ReadContext]
    cache: strawberry.Private[dict[str, Any]]

    @classmethod
    def of(cls, d: edges.Edge, ctx: ReadContext) -> Self:
        return cls(id=d.id, edge=d, ctx=ctx, cache={})

    async def _basis(self) -> OfficialBasis:
        if "basis" not in self.cache:
            self.cache["basis"] = asyncio.ensure_future(
                off_loop(official_basis, self.ctx, self.edge)
            )
        found: OfficialBasis = await self.cache["basis"]
        return found

    async def _series(self) -> BasisSeries | ReadUnknown:
        if "series" not in self.cache:
            self.cache["series"] = asyncio.ensure_future(self._load_series())
        found: BasisSeries | ReadUnknown = await self.cache["series"]
        return found

    async def _load_series(self) -> BasisSeries | ReadUnknown:
        basis = await self._basis()
        return await off_loop(load_basis_series, self.ctx, basis)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The run and basis every section reads"
    )
    async def basis(self, info: Info) -> ResultBasis:
        return ResultBasis.of(summary_of(await self._basis()))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The evidence curve with the live stroke"
    )
    async def curve(self, info: Info) -> EdgeCurve:
        basis, series = await self._basis(), await self._series()
        return EdgeCurve.of(await off_loop(curve.load_curve, self.ctx, self.edge, basis, series))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The drawdown and the volatility of the windows"
    )
    async def drawdown(self, info: Info) -> EdgeDrawdown:
        return EdgeDrawdown.of(drawdown.load_drawdown(await self._series()))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The lift from each year's start forward"
    )
    async def rolling_starts(self, info: Info) -> EdgeRollingStarts:
        return EdgeRollingStarts.of(rolling.load_rolling_starts(await self._series()))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The calendar months of the curve (the heat map)"
    )
    async def monthly(self, info: Info) -> EdgeMonthly:
        return EdgeMonthly.of(rolling.load_monthly(await self._series()))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The decay of the edge's number, the paper's figure then the in-sample, "
        "out-of-sample and live bars of the verdict's basis; null: the verdict has no basis"
    )
    async def decay(self, info: Info) -> EdgeDecay | None:
        series = await self._series()
        found = await off_loop(decay.load_decay, self.ctx, self.edge, series)
        return EdgeDecay.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="How the verdict's basis holds up under trading costs (ADR 0064): the win "
        "rate, lift and mean excess return at each round-trip cost the harness measured, the "
        "break-even cost and the decile spread. `state` says why there is none "
        "(not_a_cost_outcome: the outcome is not a return)"
    )
    async def costs(self, info: Info) -> EdgeCosts:
        basis = await self._basis()
        return EdgeCosts.of(await off_loop(costs.load_edge_costs, self.ctx, self.edge, basis))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="How much money the basis's picks can take (ADR 0064): the median 20-day "
        "dollar volume of the counted picks and how many trade below the site's floor, per period"
    )
    async def capacity(self, info: Info) -> EdgeCapacity:
        basis = await self._basis()
        found = await off_loop(capacity.load_edge_capacity, self.ctx, self.edge, basis)
        return EdgeCapacity.of(found)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The verdict's basis in each market regime: win rate, base rate, lift and "
        "trades per regime, whole run only (the split's two sides are not stored)"
    )
    async def regimes(self, info: Info) -> EdgeRegimes:
        basis = await self._basis()
        return EdgeRegimes.of(await off_loop(regimes.load_regimes, self.ctx, basis))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The verdict's screen at every holding period: in-sample, out-of-sample and "
        "whole-history lift with trades, the basis marked, and the date each out-of-sample "
        "count is expected to reach the verdict's bar"
    )
    async def horizons(self, info: Info) -> EdgeHorizons:
        basis = await self._basis()
        found = await off_loop(horizons.load_horizons, self.ctx, self.edge, basis)
        return EdgeHorizons.of(found)
