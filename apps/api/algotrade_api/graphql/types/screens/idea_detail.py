"""``IdeaDetail``: one idea's page (ADR 0083 amendment 2026-11-01 (b)): the setup it is shown
under and the other setups that picked it, then the sections: why it is here, the historical
exit rule, the evidence, what could go wrong and the setup to learn. Decided on the server
(services/read/ideas/detail.py); a section with a missing input carries its `unknown`."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.ideas import detail, inverse
from algotrade_api.graphql.types.evaluation.exit_rule import ExitRule
from algotrade_api.graphql.types.events.instrument_events import AheadEvent
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.screens.ideas import IdeaMetric
from algotrade_api.graphql.types.screens.result import CriterionResult
from algotrade_api.graphql.types.screens.setup_ideas import IdeaTab


@strawberry.type(
    description="A qualifying setup that picked the idea: its `place` among the setup's picks, "
    "`tab` and verdict `level` (works or promising)"
)
class InstrumentSetup:
    edge_id: str
    edge_name: str
    tab: IdeaTab
    level: str
    place: int

    @classmethod
    def of(cls, d: inverse.InstrumentSetup) -> Self:
        return cls(
            edge_id=d.edge_id,
            edge_name=d.edge_name,
            tab=IdeaTab(d.tab),
            level=d.level,
            place=d.place,
        )


@strawberry.type(
    description="Why the name is here: the setup's `thesis` and `mechanism`, its `basisScreener`'s "
    "`decision` for the name and the `criteria` it met; `unknown` when the pick's row could "
    "not be read"
)
class IdeaWhy:
    thesis: str
    mechanism: str
    basis_screener: str
    decision: str | None
    criteria: list[CriterionResult]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: detail.IdeaWhy) -> Self:
        return cls(
            thesis=d.thesis,
            mechanism=d.mechanism,
            basis_screener=d.basis_screener,
            decision=d.decision,
            criteria=[CriterionResult.of(c) for c in d.criteria],
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )


@strawberry.type(
    description="The stored verdict headline of the setup: every figure is backtested "
    "(hypothetical), never a forecast. `liftPts`: the out-of-sample lift in points; `oosTrades` "
    "and `trades`: the trades behind it; null: not measured"
)
class IdeaEvidence:
    level: str
    result: str
    basis: str | None
    basis_horizon: int | None
    lift_pts: float | None
    lift: float | None
    trades: int | None
    oos_trades: int | None

    @classmethod
    def of(cls, d: detail.IdeaEvidence) -> Self:
        return cls(
            level=d.level,
            result=d.result,
            basis=d.basis,
            basis_horizon=d.basis_horizon,
            lift_pts=d.lift_pts,
            lift=d.lift,
            trades=d.trades,
            oos_trades=d.oos_trades,
        )


@strawberry.type(
    description="What could go wrong: `persistence` (why the setup's edge should last, so what "
    "would end it), the name's own earnings `events` before the hold ends on `holdEnds`, and the "
    "pick's `watchOut` ids; `unknown` when the hold is not known"
)
class IdeaRisks:
    persistence: str
    hold_ends: dt.date | None
    events: list[AheadEvent]
    watch_out: list[str]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: detail.IdeaRisks) -> Self:
        return cls(
            persistence=d.persistence,
            hold_ends=d.hold_ends,
            events=[AheadEvent.of(e) for e in d.events],
            watch_out=list(d.watch_out),
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )


@strawberry.type(
    description="One idea's page for the session, shown under `setup` (the best that picked "
    "it, or the one asked for); `setups` lists every qualifying setup that picked it. `learn` is "
    "the setup's id, the key of its Guide entry"
)
class IdeaDetail:
    session: dt.date
    instrument_id: str
    instrument: Instrument | None
    tab: IdeaTab
    setup: InstrumentSetup
    setups: list[InstrumentSetup]
    why: IdeaWhy
    exit_rule: ExitRule
    evidence: IdeaEvidence
    risks: IdeaRisks
    learn: str
    metrics: list[IdeaMetric]

    @classmethod
    def of(cls, d: detail.IdeaDetail, ctx: ReadContext) -> Self:
        return cls(
            session=d.session,
            instrument_id=d.instrument_id,
            instrument=Instrument.of(d.instrument, ctx) if d.instrument is not None else None,
            tab=IdeaTab(d.tab),
            setup=InstrumentSetup.of(d.setup),
            setups=[InstrumentSetup.of(s) for s in d.setups],
            why=IdeaWhy.of(d.why),
            exit_rule=ExitRule.of(d.exit_rule),
            evidence=IdeaEvidence.of(d.evidence),
            risks=IdeaRisks.of(d.risks),
            learn=d.learn,
            metrics=[IdeaMetric.of(m) for m in d.metrics],
        )
