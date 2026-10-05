"""``ScreenResult``: what a screener's run stored for one instrument (rank, decision, score,
reasons, flags, each criterion's outcome and value, the screen's display columns), and who the
instrument is (typed identity; its per-session values are ``instrument.features(names)``)."""

from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import results
from algotrade_api.graphql.types.instrument import Instrument


@strawberry.type(
    description="What one criterion judged: the value (null: missing), PASS / NEAR / FAIL / "
    "MISSING and, for a near miss or a fail, how far from passing"
)
class CriterionResult:
    id: str
    field: str
    mode: str
    outcome: str
    value: JSON | None
    distance: float | None

    @classmethod
    def of(cls, d: results.CriterionResult) -> Self:
        return cls(
            id=d.id,
            field=d.field,
            mode=d.mode,
            outcome=d.outcome,
            value=JSON(d.value),
            distance=d.distance,
        )


@strawberry.type(description="One of the screen's display columns for the instrument")
class ResultColumn:
    name: str
    value: JSON | None

    @classmethod
    def of(cls, d: results.ResultColumn) -> Self:
        return cls(name=d.name, value=JSON(d.value))


@strawberry.type(
    description="One instrument's row of a screener's run; `instrument` is null when the "
    "session's reference snapshot does not have it"
)
class ScreenResult:
    run_id: str
    config_id: str
    instrument_id: str
    instrument: Instrument | None
    rank: int
    decision: str
    score: float | None
    tie_break: float | None
    reasons: str
    flags: list[str]
    criteria: list[CriterionResult]
    columns: list[ResultColumn]

    @classmethod
    def of(cls, d: results.ScreenResult, ctx: ReadContext) -> Self:
        return cls(
            run_id=d.run_id,
            config_id=d.config_id,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            rank=d.rank,
            decision=d.decision,
            score=d.score,
            tie_break=d.tie_break,
            reasons=d.reasons,
            flags=list(d.flags),
            criteria=[CriterionResult.of(c) for c in d.criteria],
            columns=[ResultColumn.of(c) for c in d.columns],
        )
