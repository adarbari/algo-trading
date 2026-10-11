"""``EdgeResult.regimes`` and ``EdgeResult.horizons`` (ADR 0064, "where it worked"): thin types
over ``services/read/edge_evidence/slices``: the verdict's basis by market regime and its screen
at every holding period. Every figure, flag, date and state is the read model's."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.edge_evidence.slices import figures, horizons, regimes


@strawberry.type(
    description="One period (all, in_sample, out_of_sample) of a slice: its `state` (measured, "
    "not_stored, oos_hidden) and, when measured, the `winRate` and `baseRate` (fractions), "
    "`liftPts` (win rate less base rate, in points), `trades` (independent sessions) and `thin` "
    "(fewer trades than the verdict needs out of sample)"
)
class SliceFigure:
    period: str
    state: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    trades: int | None
    thin: bool

    @classmethod
    def of(cls, d: figures.SliceFigure) -> Self:
        return cls(
            period=d.period, state=d.state, win_rate=d.win_rate, base_rate=d.base_rate,
            lift_pts=d.lift_pts, trades=d.trades, thin=d.thin,
        )  # fmt: skip


@strawberry.type(description="One market `regime` label and its `figures` by period")
class RegimeRow:
    regime: str
    figures: list[SliceFigure]

    @classmethod
    def of(cls, d: regimes.RegimeRow) -> Self:
        return cls(regime=d.regime, figures=[SliceFigure.of(f) for f in d.figures])


@strawberry.type(
    description="The verdict's basis (`variant` at `horizon` sessions) in each market regime, "
    "least to most severe. The harness stores a regime over the whole run, so a regime's "
    "in_sample and out_of_sample figures are not_stored. `state`: measured, not_stored (a run "
    "from before the regime rows, or none) or oos_hidden (a copy's out-of-sample result is "
    "withheld, and the regime rows hold it)"
)
class EdgeRegimes:
    state: str
    variant: str | None
    horizon: int | None
    rows: list[RegimeRow]

    @classmethod
    def of(cls, d: regimes.EdgeRegimes) -> Self:
        return cls(
            state=d.state, variant=d.variant, horizon=d.horizon,
            rows=[RegimeRow.of(r) for r in d.rows],
        )  # fmt: skip


@strawberry.type(
    description="When a holding period's out-of-sample count reaches the `needed` trades: "
    "`state` (projected, not_stored, beyond_projection, unprojectable, oos_hidden, reached), "
    "`have` and `remaining` trades and, when projected, `expectedBy` (the exit of the trade "
    "that completes the count) at `fillRatio` of the decision sessions measured. An estimate"
)
class OosBy:
    state: str
    needed: int
    have: int | None
    remaining: int | None
    expected_by: dt.date | None
    fill_ratio: float | None

    @classmethod
    def of(cls, d: horizons.OosBy) -> Self:
        return cls(
            state=d.state, needed=d.needed, have=d.have, remaining=d.remaining,
            expected_by=d.expected_by, fill_ratio=d.fill_ratio,
        )  # fmt: skip


@strawberry.type(
    description="One holding period of `horizon` sessions: `basis` is the verdict's own pre-chosen "
    "test; any other row is not the pre-chosen test, one of several tries. Its `figures` by "
    "period and `oosBy`"
)
class HorizonRow:
    horizon: int
    basis: bool
    figures: list[SliceFigure]
    oos_by: OosBy

    @classmethod
    def of(cls, d: horizons.HorizonRow) -> Self:
        return cls(
            horizon=d.horizon, basis=d.basis, figures=[SliceFigure.of(f) for f in d.figures],
            oos_by=OosBy.of(d.oos_by),
        )  # fmt: skip


@strawberry.type(
    description="The verdict's screen (`variant`) at every holding period the run measured, "
    "shortest first, the basis marked; `needed` is the verdict's out-of-sample trades. `state`: "
    "measured or not_stored"
)
class EdgeHorizons:
    state: str
    variant: str | None
    needed: int
    rows: list[HorizonRow]

    @classmethod
    def of(cls, d: horizons.EdgeHorizons) -> Self:
        return cls(
            state=d.state, variant=d.variant, needed=d.needed,
            rows=[HorizonRow.of(r) for r in d.rows],
        )  # fmt: skip
