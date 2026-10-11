"""``EdgeCosts`` and ``EdgeCapacity`` (ADR 0064 decision 5), thin types over
``services/read/edge_evidence``: how an edge's official result holds up under trading costs, and
how much money its picks can take. Every number and state is the read model's."""

from typing import Self

import strawberry

from algotrade.services.read.edge_evidence import capacity, costs


@strawberry.type(
    description="One period at one round-trip cost of `bp` basis points: the `winRate`, "
    "`baseRate`, `liftPts` (win rate less base rate, in points) and `meanExcess` (the picks' mean "
    "return over the benchmark, a fraction, net of `bp`) over `sessions` independent sessions "
    "and `picks` picks; `assumed`: this is the edge document's own cost, the one every other "
    "figure of the page is net of"
)
class CostLevel:
    period: str
    bp: float
    assumed: bool
    sessions: int | None
    picks: int | None
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    mean_excess: float | None

    @classmethod
    def of(cls, d: costs.CostLevel) -> Self:
        return cls(
            period=d.period, bp=d.bp, assumed=d.assumed, sessions=d.sessions, picks=d.picks,
            win_rate=d.win_rate, base_rate=d.base_rate, lift_pts=d.lift_pts,
            mean_excess=d.mean_excess,
        )  # fmt: skip


@strawberry.type(
    description="One period (all, in_sample, out_of_sample) of the cost sensitivity: its `state` "
    "(measured, not_stored, oos_hidden), the `breakEvenBp` (the round-trip cost at which the "
    "picks' mean excess return is zero, exact: cost is linear in the mean) and the "
    "`decileSpread` (top tenth less bottom tenth; the same at every cost, both tenths pay it)"
)
class CostPeriod:
    period: str
    state: str
    break_even_bp: float | None
    decile_spread: float | None

    @classmethod
    def of(cls, d: costs.CostPeriod) -> Self:
        return cls(
            period=d.period, state=d.state, break_even_bp=d.break_even_bp,
            decile_spread=d.decile_spread,
        )  # fmt: skip


@strawberry.type(
    description="How the official result of an edge at the verdict's basis (`variant`, "
    "`horizon` sessions) holds up under trading costs: `state` (measured, not_stored: an older "
    "run, not_a_cost_outcome: the outcome is not a return, oos_hidden), `assumedBp` the "
    "document's own cost, the `levels` by period then cost and one `periods` row per period"
)
class EdgeCosts:
    state: str
    variant: str | None
    horizon: int | None
    assumed_bp: float
    levels: list[CostLevel]
    periods: list[CostPeriod]

    @classmethod
    def of(cls, d: costs.EdgeCosts) -> Self:
        return cls(
            state=d.state, variant=d.variant, horizon=d.horizon, assumed_bp=d.assumed_bp,
            levels=[CostLevel.of(lv) for lv in d.levels],
            periods=[CostPeriod.of(p) for p in d.periods],
        )  # fmt: skip


@strawberry.type(
    description="One period of the capacity: the `advMedian` (dollars) of the 20-day average "
    "dollar volume of the `advKnown` counted picks that have one (of `picks`), `advLow` of them "
    "below the site's floor; its `state` (measured, not_stored, oos_hidden)"
)
class CapacityPeriod:
    period: str
    state: str
    picks: int | None
    adv_median: float | None
    adv_known: int | None
    adv_low: int | None

    @classmethod
    def of(cls, d: capacity.CapacityPeriod) -> Self:
        return cls(
            period=d.period, state=d.state, picks=d.picks, adv_median=d.adv_median,
            adv_known=d.adv_known, adv_low=d.adv_low,
        )  # fmt: skip


@strawberry.type(
    description="How much money the picks of an edge's official result (the verdict's basis: "
    "`variant`, `horizon` sessions) can take: `floorUsd` is the site's low-liquidity floor today "
    "and `periods` one row per period; `state` is measured when any period is, else not_stored"
)
class EdgeCapacity:
    state: str
    variant: str | None
    horizon: int | None
    floor_usd: float
    periods: list[CapacityPeriod]

    @classmethod
    def of(cls, d: capacity.EdgeCapacity) -> Self:
        return cls(
            state=d.state, variant=d.variant, horizon=d.horizon, floor_usd=d.floor_usd,
            periods=[CapacityPeriod.of(p) for p in d.periods],
        )  # fmt: skip
