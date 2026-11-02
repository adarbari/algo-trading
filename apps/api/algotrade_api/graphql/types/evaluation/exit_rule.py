"""``ExitRule``: the exit rule a setup publishes for a pick (ADR 0083 decision 3; an option
setup's declared exits, ADR 0088 decision 19), from
``services/read/evaluation/positions/exit_rule.py``."""

from datetime import date
from typing import Self

import strawberry

from algotrade.services.read.evaluation.positions import exit_rule
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(exit_rule.StopKind, description="Where a published stop comes from")
strawberry.enum(exit_rule.StopBasis, description="What a published stop's `fraction` is of")


@strawberry.type(
    description="A stop. `fraction` of its `basis`: below the entry reference close (ENTRY), a "
    "multiple of the credit (CREDIT) or a share of the collateral (COLLATERAL); HISTORY: the "
    "level that `1 - beyond` of the setup's winning trades never passed, on `winners` trades; "
    "DECLARED: the setup's own rule; FALLBACK: `multiple` x `atr` (ATR(14), usd per share), "
    "not from this setup's history"
)
class Stop:
    kind: exit_rule.StopKind
    fraction: float | None
    atr: float | None
    multiple: float | None
    winners: int | None
    beyond: float | None
    basis: exit_rule.StopBasis

    @classmethod
    def of(cls, d: exit_rule.Stop) -> Self:
        return cls(
            kind=d.kind, fraction=d.fraction, atr=d.atr, multiple=d.multiple,
            winners=d.winners, beyond=d.beyond, basis=d.basis,
        )  # fmt: skip


@strawberry.type(
    description="A setup's historical exit rule at the served session: the `stop` and the "
    "`holdSessions` (the verdict's basis horizon), each null only with `unknown` saying why "
    "(never filled from an older value; none of it is read from a run that ends after the "
    "served session). `winners`: the basis's winning long trades read; `inSampleOnly`: the "
    "run hides its out-of-sample trades, so only in-sample winners were read. An option "
    "setup's declared `takeProfit` (a share of the credit; for a share setup a rise of the "
    "entry price: see `takeProfitBasis`), `exitDte` (calendar days to expiry) and the "
    "`conditionFields` of its exit condition; its hold is the earlier of the basis horizon "
    "and the `expiry` when one was given"
)
class ExitRule:
    edge_id: str
    stop: Stop | None
    hold_sessions: int | None
    unknown: Unknown | None
    winners: int
    in_sample_only: bool
    take_profit: float | None
    take_profit_basis: exit_rule.StopBasis | None
    exit_dte: int | None
    condition_fields: list[str]
    expiry: date | None

    @classmethod
    def of(cls, d: exit_rule.ExitRule) -> Self:
        return cls(
            edge_id=d.edge_id,
            stop=Stop.of(d.stop) if d.stop is not None else None,
            hold_sessions=d.hold_sessions,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            winners=d.winners,
            in_sample_only=d.in_sample_only,
            take_profit=d.take_profit,
            take_profit_basis=d.take_profit_basis,
            exit_dte=d.exit_dte,
            condition_fields=list(d.condition_fields),
            expiry=d.expiry,
        )
