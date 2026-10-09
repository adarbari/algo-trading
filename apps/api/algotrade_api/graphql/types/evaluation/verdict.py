"""``EdgeVerdict`` (an edge's verdict from its official result, ED8) with its criteria and its
year-by-year rows, and ``EdgeSource`` / ``EdgeDefinition`` (what the edge page says about how
the edge is defined): every number and sentence is the read model's, none is derived by a page."""

from typing import Self

import strawberry

from algotrade.services.read.evaluation import edges, robustness
from algotrade.services.read.evaluation import verdict as read


@strawberry.type(description="A source the edge rests on; `url` is empty when it has none")
class EdgeSource:
    title: str
    url: str

    @classmethod
    def of(cls, d: edges.EdgeSource) -> Self:
        return cls(title=d.title, url=d.url)


@strawberry.type(
    description="How the edge is defined, as sentences: `picks` (when it fires, how many), "
    "`trade` (entry, holding periods, costs, what a win is), `compare` (universe and "
    "baselines) and `test` (where the out-of-sample period starts)"
)
class EdgeDefinition:
    picks: str
    trade: str
    compare: str
    test: str

    @classmethod
    def of(cls, d: edges.EdgeDefinition) -> Self:
        return cls(picks=d.picks, trade=d.trade, compare=d.compare, test=d.test)


@strawberry.type(
    description="One test of the verdict: the `value` measured, the `threshold` it must reach "
    "and its `status` (pass, fail, not_measured); `level`: the verdict it gates (promising, "
    "works)"
)
class VerdictCriterion:
    id: str
    label: str
    value: str
    threshold: str
    status: str
    level: str

    @classmethod
    def of(cls, d: read.VerdictCriterion) -> Self:
        return cls(
            id=d.id,
            label=d.label,
            value=d.value,
            threshold=d.threshold,
            status=d.status,
            level=d.level,
        )


@strawberry.type(
    description="One calendar year of the verdict's basis; `period`: in_sample, out_of_sample "
    "or both (the split falls inside the year); `liftPts`: win rate minus base rate, in points"
)
class VerdictYear:
    year: str
    period: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None

    @classmethod
    def of(cls, d: read.YearRow) -> Self:
        return cls(
            year=d.year,
            period=d.period,
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            decile_spread=d.decile_spread,
            trades=d.trades,
        )


@strawberry.type(
    description="One bin of the random-pick backtests' lifts: `start` (inclusive) to `end` "
    "(exclusive; inclusive for the last bin), `count` draws"
)
class RobustnessBin:
    start: float
    end: float
    count: int

    @classmethod
    def of(cls, d: robustness.RobustnessBin) -> Self:
        return cls(start=d.start, end=d.end, count=d.count)


@strawberry.type(
    description="The edge's out-of-sample `lift` among `draws` backtests of random picks (same "
    "holding period): `beats` the share of them it is above (0 to 1), `bins` their lifts for "
    "the distribution, `summary` the sentence. Null: the run drew none"
)
class Robustness:
    lift: float
    draws: int
    beats: float
    bins: list[RobustnessBin]
    summary: str

    @classmethod
    def of(cls, d: robustness.Robustness) -> Self:
        return cls(
            lift=d.lift,
            draws=d.draws,
            beats=d.beats,
            bins=[RobustnessBin.of(b) for b in d.bins],
            summary=d.summary,
        )


@strawberry.type(
    description="An edge's verdict, judged on its official result (the canonical run): "
    "`verdict` is works, promising, not_working, not_enough_data or waiting_on_data; `rationale` "
    "the first failing criterion in words; `headline` the page's sentence and `result` the "
    "list's one-liner; `basis` the screen and holding period it rests on. The figures are the "
    "basis's out-of-sample ones (`trades`: the whole result's); `liftPts` is win rate minus "
    "base rate in points, `lift` the ratio. `criteria` and `years` feed the details panel; "
    "`trials` the variants tried on the edge, `deciles` the in-sample mean outcome of each tenth "
    "of the screen's ranking, best-ranked first (empty: not stored, never zeros), `robustness` "
    "the lift among random-pick backtests"
)
class EdgeVerdict:
    verdict: str
    rationale: str
    headline: str
    result: str
    basis: str | None
    trades: int | None
    oos_trades: int | None
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    lift: float | None
    decile_spread: float | None
    decile_t: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    criteria: list[VerdictCriterion]
    years: list[VerdictYear]
    trials: int | None
    deciles: list[float | None]
    robustness: Robustness | None

    @classmethod
    def of(cls, d: read.EdgeVerdict) -> Self:
        return cls(
            verdict=d.verdict,
            rationale=d.rationale,
            headline=d.headline,
            result=d.result,
            basis=d.basis,
            trades=d.trades,
            oos_trades=d.oos_trades,
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            lift=d.lift,
            decile_spread=d.decile_spread,
            decile_t=d.decile_t,
            sharpe=d.sharpe,
            deflated_sharpe=d.deflated_sharpe,
            pbo=d.pbo,
            criteria=[VerdictCriterion.of(c) for c in d.criteria],
            years=[VerdictYear.of(y) for y in d.years],
            trials=d.trials,
            deciles=list(d.deciles),
            robustness=Robustness.of(d.robustness) if d.robustness else None,
        )
