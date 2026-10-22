"""``EdgeVerdict`` (an edge's verdict from its official result, ED8) with its criteria and its
year-by-year rows, and ``EdgeSource`` / ``EdgeDefinition`` (what the edge page says about how
the edge is defined): every number and sentence is the read model's, none is derived by a page."""

from datetime import date
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.evaluation import decay, edges, evidence, robustness
from algotrade.services.read.evaluation import verdict as read


@strawberry.type(description="A source the edge rests on; `url` is empty when it has none")
class EdgeSource:
    title: str
    url: str

    @classmethod
    def of(cls, d: edges.EdgeSource) -> Self:
        return cls(title=d.title, url=d.url)


@strawberry.type(description="One quality-bar answer: `key` names the question, `text` the answer")
class EdgeAnswer:
    key: str
    text: str

    @classmethod
    def of(cls, d: edges.EdgeAnswer) -> Self:
        return cls(key=d.key, text=d.text)


@strawberry.type(
    description="What the builder edits, as the layered document resolves: `topK` (null: every "
    "qualified name), `universe` (a preset's name; empty: an inline selection), the outcome's "
    "`kind`, `benchmark`, `startOffsetSessions` and `costBps`, the `qualityBar` answers, and "
    "`own`: the user's own document as JSON (empty for a site edge), which a save extends "
    "because a save replaces the whole document"
)
class EdgeSettings:
    top_k: int | None
    universe: str
    kind: str
    benchmark: str
    start_offset_sessions: int
    cost_bps: float | None
    quality_bar: list[EdgeAnswer]
    own: JSON

    @classmethod
    def of(cls, d: edges.EdgeSettings) -> Self:
        return cls(
            top_k=d.top_k,
            universe=d.universe,
            kind=d.kind,
            benchmark=d.benchmark,
            start_offset_sessions=d.start_offset_sessions,
            cost_bps=d.cost_bps,
            quality_bar=[EdgeAnswer.of(a) for a in d.quality_bar],
            own=JSON(dict(d.own)),
        )


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
    "and its `status` (pass, fail, not_measured, not_applicable: nothing to test, as decoys "
    "that are not declared; it counts neither for nor against the level); `level`: the "
    "verdict it gates (promising, works)"
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
    description="One calendar year of the verdict's basis, or the part of it on one side of the "
    "split (`partial`: a year the split falls in is two rows, in-sample then out-of-sample); "
    '`label` names the row ("2026 Jan-Mar") and it spans `fromDate` to `toDate`; `period`: '
    "in_sample, out_of_sample or both (an older run's year the split falls inside); `liftPts`: "
    "win rate minus base rate, in points"
)
class VerdictYear:
    year: str
    period: str
    label: str
    from_date: date
    to_date: date
    partial: bool
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
            label=d.label,
            from_date=d.from_date,
            to_date=d.to_date,
            partial=d.partial,
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            decile_spread=d.decile_spread,
            trades=d.trades,
        )


@strawberry.type(
    description="The basis's figures over one `period` (in_sample, out_of_sample or all); "
    "`liftPts`: win rate minus base rate, in points; `thin`: the out-of-sample column has "
    "fewer trades than the verdict needs; `referenceRate` (the risk-neutral rate of a win) and "
    "`touchRate` (picks whose strike was touched) only an expires-out-of-the-money outcome has. "
    "A figure not stored is null"
)
class VerdictColumn:
    period: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    trades: int | None
    decile_spread: float | None
    decile_t: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    thin: bool
    reference_rate: float | None
    touch_rate: float | None
    picks_t: float | None

    @classmethod
    def of(cls, d: read.VerdictColumn) -> Self:
        return cls(
            period=d.period,
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            trades=d.trades,
            decile_spread=d.decile_spread,
            decile_t=d.decile_t,
            sharpe=d.sharpe,
            deflated_sharpe=d.deflated_sharpe,
            pbo=d.pbo,
            thin=d.thin,
            reference_rate=d.reference_rate,
            touch_rate=d.touch_rate,
            picks_t=d.picks_t,
        )


@strawberry.type(
    description="One count of trades still short: `have` of `needed` (`oos`: out-of-sample "
    "trades, else the whole history's), `remaining` to come, `state` of its projection "
    "(projected, beyond_projection, not_stored, unprojectable, oos_hidden), `expectedBy` the "
    "exit of the trade that completes it at `fillRatio` of the decision sessions measured and "
    "one trade every `cadenceSessions` sessions"
)
class CountProjection:
    criterion: str
    oos: bool
    have: int
    needed: int
    remaining: int
    state: str
    expected_by: date | None
    fill_ratio: float | None
    cadence_sessions: int | None

    @classmethod
    def of(cls, d: evidence.CountProjection) -> Self:
        return cls(
            criterion=d.criterion, oos=d.oos, have=d.have, needed=d.needed,
            remaining=d.remaining, state=d.state, expected_by=d.expected_by,
            fill_ratio=d.fill_ratio, cadence_sessions=d.cadence_sessions,
        )  # fmt: skip


@strawberry.type(
    description="The verdict with the count of the outlook's test met (`needed` trades), on "
    "today's figures: its `level`, `reasons` it is not better (the failing tests, in words) and "
    "the server's `sentence`. An estimate, never an input to the verdict"
)
class AtTarget:
    needed: int
    level: str
    reasons: list[str]
    sentence: str

    @classmethod
    def of(cls, d: evidence.AtTarget) -> Self:
        return cls(needed=d.needed, level=d.level, reasons=list(d.reasons), sentence=d.sentence)


@strawberry.type(
    description="What would change the verdict: `criterion` (the first test not passed; "
    "`level`: the verdict it gates) in `sentence`. `projections` every count of trades still "
    "short (Promising's and Works's), `nextClose` the exit of the next trade to close (the first "
    "stored exit after the run) and, for a count, `atTarget` the verdict once it is met. For a "
    "count of trades (`trades`, `works_trades`) `have` of `needed` and `remaining` to come, and "
    "`projectionState`: "
    "projected (`expectedBy`: the exit of the trade that completes the count, at `fillRatio` of "
    "the decision sessions measured), beyond_projection (the count needs more sessions than the "
    "run stored), not_stored (an older run), unprojectable (an event schedule), oos_hidden. An "
    "estimate, never an input to the verdict. Null for the other tests: a t statistic is not "
    "projected"
)
class EdgeOutlook:
    criterion: str
    level: str
    sentence: str
    have: int | None
    needed: int | None
    remaining: int | None
    projection_state: str | None
    expected_by: date | None
    fill_ratio: float | None
    cadence_sessions: int | None
    projections: list[CountProjection]
    next_close: date | None
    at_target: AtTarget | None

    @classmethod
    def of(cls, d: evidence.EdgeOutlook) -> Self:
        return cls(
            criterion=d.criterion,
            level=d.level,
            sentence=d.sentence,
            have=d.have,
            needed=d.needed,
            remaining=d.remaining,
            projection_state=d.projection_state,
            expected_by=d.expected_by,
            fill_ratio=d.fill_ratio,
            cadence_sessions=d.cadence_sessions,
            projections=[CountProjection.of(p) for p in d.projections],
            next_close=d.next_close,
            at_target=AtTarget.of(d.at_target) if d.at_target else None,
        )


@strawberry.type(
    description="How much evidence the verdict has: `oosTrades` out-of-sample against `needed` "
    "(from there it can say Promising or Not working; `reached`: it has them), "
    "`worksOosNeeded` the out-of-sample count Works asks, `wholeTrades` against `wholeNeeded` "
    "the whole history's, and `checks` the criteria that say whether the result is real"
)
class EvidenceProgress:
    oos_trades: int
    needed: int
    works_oos_needed: int
    whole_trades: int
    whole_needed: int
    reached: bool
    checks: list[VerdictCriterion]
    outlook: EdgeOutlook | None

    @classmethod
    def of(cls, d: evidence.EvidenceProgress) -> Self:
        return cls(
            oos_trades=d.oos_trades,
            needed=d.needed,
            works_oos_needed=d.works_oos_needed,
            whole_trades=d.whole_trades,
            whole_needed=d.whole_needed,
            reached=d.reached,
            checks=[VerdictCriterion.of(c) for c in d.checks],
            outlook=EdgeOutlook.of(d.outlook) if d.outlook else None,
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
    description="The Sharpe ratio after the multiple-testing haircut (Harvey and Liu): the "
    "stored `sharpe` (per trade, not annualised) over `sessions` trades is `haircutSharpe` once "
    "`trials` variants tried are counted, `cut` (0 to 1) the share lost; `method` names the "
    "adjustment (bonferroni: Holm's value for the best of the trials) and `summary` is the "
    "sentence. `siteTrials`, `siteHaircutSharpe` and `siteCut` are the same adjustment for every "
    "variant tried across every site edge (null: not counted). "
    "Null: not stored, or the Sharpe ratio is not above zero"
)
class EdgeHaircut:
    sharpe: float
    haircut_sharpe: float
    cut: float
    trials: int
    sessions: int
    method: str
    summary: str
    site_trials: int | None
    site_haircut_sharpe: float | None
    site_cut: float | None

    @classmethod
    def of(cls, d: robustness.EdgeHaircut) -> Self:
        return cls(
            sharpe=d.sharpe,
            haircut_sharpe=d.haircut_sharpe,
            cut=d.cut,
            trials=d.trials,
            sessions=d.sessions,
            method=d.method,
            summary=d.summary,
            site_trials=d.site_trials,
            site_haircut_sharpe=d.site_haircut_sharpe,
            site_cut=d.site_cut,
        )


@strawberry.type(
    description="The figure the literature reports for the edge: `measure` (mean_excess, "
    "decile_spread or lift_pts) equal to `value` over `horizonSessions`, from `source` over "
    "`sample` years (null: not stated); `leg`: what the figure is of (long_short or long)"
)
class EdgePublished:
    measure: str
    value: float
    horizon_sessions: int
    source: EdgeSource
    sample: int | None
    leg: str

    @classmethod
    def of(cls, d: edges.EdgePublished) -> Self:
        return cls(
            measure=d.measure,
            value=d.value,
            horizon_sessions=d.horizon_sessions,
            source=EdgeSource.of(d.source),
            sample=d.sample,
            leg=d.leg,
        )


@strawberry.type(
    description="What to expect of the paper's figure once traded: `value` is the published "
    "figure less the `haircut` (0 to 1) of its `leg` (long_short or long), in the decay's "
    "unit; `realised` the out-of-sample bar's figure and `share` its share of `value` (null "
    "where the bar has none); `summary` is the sentence. Display only, no verdict reads it"
)
class ExpectedFigure:
    leg: str
    haircut: float
    value: float
    realised: float | None
    share: float | None
    summary: str

    @classmethod
    def of(cls, d: decay.ExpectedFigure) -> Self:
        return cls(
            leg=d.leg,
            haircut=d.haircut,
            value=d.value,
            realised=d.realised,
            share=d.share,
            summary=d.summary,
        )


@strawberry.type(
    description="One bar of the decay: `period` (published, in_sample, out_of_sample, live: the "
    "settled paper trades, on `Query.edgeResult.decay` only), its `value` (null unless `state` is "
    "measured) over `n` (the trades, or the decile sessions of a decile spread, or the live "
    "signal sessions; null for the paper's) and the `state` that says why a value is missing "
    "(not_stored, not_comparable: another holding period than the paper's, oos_hidden, "
    "not_given: the document publishes no figure, not_measured_live: a decile spread cannot be "
    "measured from the paper record)"
)
class DecayBar:
    period: str
    value: float | None
    n: int | None
    state: str

    @classmethod
    def of(cls, d: decay.DecayBar) -> Self:
        return cls(period=d.period, value=d.value, n=d.n, state=d.state)


@strawberry.type(
    description="The decay of one statistic: the paper's figure (`published`) against the "
    "harness's in-sample and out-of-sample ones (`bars`, in that order after the paper's) at the "
    "verdict's `basisHorizon`; `measure` is read in `unit` (return: a fraction; points). "
    "`published` is null when the edge's document gives no figure (the paper's bar is then "
    "not_given and `measure` is lift_pts); `expected` is the figure after the haircut of its "
    "leg beside the out-of-sample bar (null without a published figure)"
)
class EdgeDecay:
    measure: str
    unit: str
    published: EdgePublished | None
    basis_horizon: int
    bars: list[DecayBar]
    expected: ExpectedFigure | None

    @classmethod
    def of(cls, d: decay.EdgeDecay) -> Self:
        return cls(
            measure=d.measure,
            unit=d.unit,
            published=EdgePublished.of(d.published) if d.published else None,
            basis_horizon=d.basis_horizon,
            bars=[DecayBar.of(b) for b in d.bars],
            expected=ExpectedFigure.of(d.expected) if d.expected else None,
        )


@strawberry.type(
    description="An edge's verdict, judged on its official result (the canonical run): "
    "`verdict` is works, promising, not_working, not_enough_data, waiting_on_data or "
    "diagnostic_only; `rationale` "
    "the first failing criterion in words; `headline` the page's sentence and `result` the "
    "list's one-liner; `basis` the screen and holding period it rests on (`basisWhy`: for a "
    "basis chosen among several, the in-sample lifts it was chosen on). The figures are the "
    "basis's out-of-sample ones (`trades`: the whole result's); `liftPts` is win rate minus "
    "base rate in points, `lift` the ratio. `criteria` and `years` feed the details panel; "
    "`trials` the variants tried on the edge, `deciles` the in-sample mean outcome of each tenth "
    "of the screen's ranking, best-ranked first (empty: not stored, never zeros), `robustness` "
    "the lift among random-pick backtests; `columns` the basis's figures in-sample, "
    "out-of-sample and over all (empty: no result yet); `evidence` the trades against what the "
    "verdict needs; `haircut` the basis's Sharpe ratio after the variants tried; `decay` the "
    "paper's figure against the in- and out-of-sample ones; `side` the basis's outcome side: long, "
    "short (the bottom of the ranking, after an assumed borrow cost) or long_short (a spread: "
    "diagnostic, never a verdict basis)"
)
class EdgeVerdict:
    verdict: str
    rationale: str
    headline: str
    result: str
    basis: str | None
    basis_why: str
    side: str
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
    columns: list[VerdictColumn]
    evidence: EvidenceProgress | None
    haircut: EdgeHaircut | None
    decay: EdgeDecay | None

    @classmethod
    def of(cls, d: read.EdgeVerdict) -> Self:
        return cls(
            verdict=d.verdict,
            rationale=d.rationale,
            headline=d.headline,
            result=d.result,
            basis=d.basis,
            basis_why=d.basis_why,
            side=d.side,
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
            columns=[VerdictColumn.of(c) for c in d.columns],
            evidence=EvidenceProgress.of(d.evidence) if d.evidence else None,
            haircut=EdgeHaircut.of(d.haircut) if d.haircut else None,
            decay=EdgeDecay.of(d.decay) if d.decay else None,
        )


@strawberry.type(
    description="The headline of an edge's verdict, what the edges list shows: the same `verdict`, "
    "`result`, `basis`, `trades` and `lift` as `Edge.verdict` (the one judge, the same run), "
    "without the haircut, decay, robustness, years, columns or evidence the list never reads, "
    "so it is read at a fraction of the cost; `oosTrades`, `liftPts`: the out-of-sample session "
    "count and the win rate over the base rate in points"
)
class EdgeSummary:
    verdict: str
    result: str
    basis: str | None
    trades: int | None
    oos_trades: int | None
    lift: float | None
    lift_pts: float | None

    @classmethod
    def of(cls, d: read.EdgeSummary) -> Self:
        return cls(
            verdict=d.verdict,
            result=d.result,
            basis=d.basis,
            trades=d.trades,
            oos_trades=d.oos_trades,
            lift=d.lift,
            lift_pts=d.lift_pts,
        )
