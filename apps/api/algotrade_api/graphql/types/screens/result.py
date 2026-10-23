"""``ScreenResult``: what a screener's run stored for one instrument (rank, decision, score,
reasons, flags, each criterion's outcome and value, the screen's display columns, what changed
since the previous run), and who the instrument is (typed identity; its per-session values are
``instrument.features(names)``); ``ScreenResultPage``: one page of a run as a review table,
with the catalogue columns the reader added, columnar as a ``FeatureTable``."""

from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read import values
from algotrade.services.read.availability.cause import UnavailableKind, kind_texts
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.screens import results as stored
from algotrade.services.read.screens import screeners as stored_screeners
from algotrade_api.graphql.types.availability import KindText, Unavailable
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument


@strawberry.type(
    description="What one edge that lists the screener does with a pick of its run, decided by "
    "the server by the harness's own rule: `counts` the edge would take it, and the `code` "
    "that says why (counts; paused: the regime gate held it back; not_qualified: a rule "
    "failed or it was not picked; below_top_k: qualified but past the edge's `topK`; withheld: "
    "its rank is withheld from the viewer), `place` its place among the run's qualified rows. "
    "It does not read an outcome: it says what the edge would take, not what it has earned"
)
class PickEdge:
    edge_id: str
    edge_name: str
    counts: bool
    code: str
    top_k: int | None
    place: int | None

    @classmethod
    def of(cls, d: pick_edges.PickEdge) -> Self:
        return cls(
            edge_id=d.edge_id,
            edge_name=d.edge_name,
            counts=d.counts,
            code=d.code,
            top_k=d.top_k,
            place=d.place,
        )


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
    group: str | None

    @classmethod
    def of(cls, d: stored.CriterionResult) -> Self:
        return cls(
            id=d.id,
            field=d.field,
            mode=d.mode,
            outcome=d.outcome,
            value=JSON(d.value),
            distance=d.distance,
            group=d.group,
        )


@strawberry.type(
    description="A group of criteria (ADR 0071): its `kind` (`all`, `any` or `none`), its "
    "`members` (criterion and group ids, in funnel order) and its `parent` group (null: a "
    "gate). In a result, `outcome` is the group's PASS / NEAR / FAIL / MISSING for the "
    "instrument and `decidedBy` the member that decided it; both are null in a screen's "
    "definition"
)
class ScreenGroup:
    id: str
    kind: str
    members: list[str]
    parent: str | None
    outcome: str | None
    decided_by: str | None

    @classmethod
    def of(cls, d: stored_screeners.ScreenGroup) -> Self:
        return cls(
            id=d.id,
            kind=d.kind,
            members=list(d.members),
            parent=d.parent,
            outcome=d.outcome,
            decided_by=d.decided_by,
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
    "`previousDecision`: the previous run's. `regime` / `sizeMultiplier`: the session's regime "
    "label and the size the gate applied, as the run stamped them (null: gate off, regime "
    "unknown, or a run before the stamp); a PAUSED row says why first in `reasons`"
)
class ScreenResult:
    run_id: str
    config_id: str
    instrument_id: str
    instrument: Instrument | None
    rank: int | None
    decision: str
    score: float | None
    tie_break: float | None
    reasons: str
    flags: list[str]
    criteria: list[CriterionResult]
    columns: list[ResultColumn]
    change: str | None
    previous_decision: str | None
    regime: str | None
    size_multiplier: float | None
    groups: list[ScreenGroup]
    counts_toward: list[PickEdge] = strawberry.field(
        description="Each edge that lists the screener and whether it counts this row (empty: "
        "none does); filled on `ScreenerRun.results` only"
    )

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
            regime=d.regime,
            size_multiplier=d.size_multiplier,
            groups=[ScreenGroup.of(g) for g in d.groups],
            counts_toward=[PickEdge.of(e) for e in d.counts_toward],
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
    "exactly when `unknown[i][j]` says why (`reasons[i][j]`: its NullReason when EXPLAINED; "
    "`kinds[i][j]`: its public kind, how a cell is drawn). "
    "`unavailable`: what the tables the search and sort read have nothing for the session "
    "leave out"
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
    kinds: list[list[UnavailableKind | None]]
    unavailable: list[Unavailable]

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
            kinds=[list(row) for row in d.kinds],
            unavailable=[Unavailable.of(u) for u in d.unavailable],
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The words of each kind `kinds` uses: how a cell's kind reads"
    )
    def kind_texts(self) -> list[KindText]:
        return [KindText.of(t) for t in kind_texts(self.kinds)]
