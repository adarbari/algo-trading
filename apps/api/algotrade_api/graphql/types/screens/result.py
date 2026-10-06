"""``ScreenResult``: what a screener's run stored for one instrument (rank, decision, score,
reasons, flags, each criterion's outcome and value, the screen's display columns, what changed
since the previous run), and who the instrument is (typed identity; its per-session values are
``instrument.features(names)``); ``ScreenResultPage``: one page of a run as a review table,
with the catalogue columns the reader added, columnar as a ``FeatureTable``."""

from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read import values
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import results as stored
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument


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
    def of(cls, d: stored.CriterionResult) -> Self:
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
    def of(cls, d: stored.ResultColumn) -> Self:
        return cls(name=d.name, value=JSON(d.value))


@strawberry.type(
    description="One instrument's row of a screener's run; `instrument` is null when the "
    "session's reference snapshot does not have it. `change`: `new` (picked now, not by the "
    "previous run) or `dropped` (the reverse); null when the same or not compared (Ideas); "
    "`previousDecision`: the previous run's"
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
    change: str | None
    previous_decision: str | None

    @classmethod
    def of(cls, d: stored.ScreenResult, ctx: ReadContext) -> Self:
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
            change=d.change,
            previous_decision=d.previous_decision,
        )


@strawberry.type(description="How many tickers of a run are `new` or `dropped`")
class ChangeCount:
    change: str
    count: int

    @classmethod
    def of(cls, d: stored.ChangeCount) -> Self:
        return cls(change=d.change, count=d.count)


@strawberry.type(
    description="One page of a run's rows matching the filters, in the sort order (`total`: "
    "every page). `rows[i][j]` is the catalogue column `columns[j]` for `results[i]`, null "
    "exactly when `unknown[i][j]` says why (`reasons[i][j]`: its NullReason when EXPLAINED). "
    "`missing`: tables the search and sort read with "
    "nothing for the session"
)
class ScreenResultPage:
    run_id: str
    sort: str
    total: int
    page: int
    size: int
    columns: list[FeatureInfo]
    results: list[ScreenResult]
    rows: list[list[JSON | None]]
    unknown: list[list[values.UnknownCode | None]]
    reasons: list[list[values.NullReason | None]]
    missing: list[str]

    @classmethod
    def of(cls, d: stored.ResultPage, ctx: ReadContext) -> Self:
        return cls(
            run_id=d.run_id,
            sort=d.sort,
            total=d.total,
            page=d.page,
            size=d.size,
            columns=[FeatureInfo.of(c) for c in d.columns],
            results=[ScreenResult.of(r, ctx) for r in d.results],
            rows=[[JSON(v) for v in row] for row in d.rows],
            unknown=[list(row) for row in d.unknown],
            reasons=[list(row) for row in d.reasons],
            missing=list(d.missing),
        )
