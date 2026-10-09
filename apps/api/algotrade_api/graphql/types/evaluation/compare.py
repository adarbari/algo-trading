"""``EdgeCompare`` (a user's edge against the one it extends and its baselines, ADR 0053 amendment
2026-10-09): the figures are the read model's, in-sample only while the edge's out-of-sample
result is withheld (``oosHidden``); the browser derives and filters nothing."""

from typing import Self

import strawberry

from algotrade.services.read.evaluation import versions as read


@strawberry.type(
    description="One period's figures of a screen at a horizon (null: not stored): win rate, "
    "base rate, lift in points, decile spread and the independent sessions (`trades`)"
)
class CompareFigures:
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None

    @classmethod
    def of(cls, d: read.Figures) -> Self:
        return cls(
            win_rate=d.win_rate,
            base_rate=d.base_rate,
            lift_pts=d.lift_pts,
            decile_spread=d.decile_spread,
            trades=d.trades,
        )


@strawberry.type(
    description="One line of the comparison: `kind` is this (the edge's latest run of yours), "
    "extended (the edge it is a copy of, its official result) or baseline; `basis` the screen "
    "and holding period; `outOfSample` is null while it is hidden (`oosHidden`) or not stored"
)
class CompareRow:
    kind: str
    label: str
    edge_id: str | None
    run_id: str | None
    basis: str
    in_sample: CompareFigures | None
    out_of_sample: CompareFigures | None
    oos_hidden: bool

    @classmethod
    def of(cls, d: read.CompareRow) -> Self:
        return cls(
            kind=d.kind,
            label=d.label,
            edge_id=d.edge_id,
            run_id=d.run_id,
            basis=d.basis,
            in_sample=CompareFigures.of(d.in_sample) if d.in_sample else None,
            out_of_sample=CompareFigures.of(d.out_of_sample) if d.out_of_sample else None,
            oos_hidden=d.oos_hidden,
        )


@strawberry.type(
    description="A user's edge against the edge it extends and its baselines. `oosHidden`: its "
    "out-of-sample figures are withheld until the user shows them (Follow, or the reveal); "
    "`reason` says why `rows` is empty"
)
class EdgeCompare:
    edge_id: str
    extends: str | None
    oos_hidden: bool
    reason: str
    rows: list[CompareRow]

    @classmethod
    def of(cls, d: read.EdgeCompare) -> Self:
        return cls(
            edge_id=d.edge_id,
            extends=d.extends,
            oos_hidden=d.oos_hidden,
            reason=d.reason,
            rows=[CompareRow.of(r) for r in d.rows],
        )
