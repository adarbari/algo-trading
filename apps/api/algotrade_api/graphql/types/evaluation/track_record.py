"""``TrackRecord``: a screener's frozen-period record from the canonical run of an edge that
lists it (the frozen slice only; an exploratory run never reaches it)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.evaluation import track_record


@strawberry.type(
    description="The frozen slice at one horizon: hit rate against the base rate, the lift, the "
    "independent `sessions` behind them and the `picks` counted"
)
class TrackHorizon:
    horizon_sessions: int
    hit_rate: float | None
    base_rate: float | None
    lift: float | None
    sessions: int | None
    picks: int | None

    @classmethod
    def of(cls, d: track_record.TrackHorizon) -> Self:
        return cls(
            horizon_sessions=d.horizon_sessions,
            hit_rate=d.hit_rate,
            base_rate=d.base_rate,
            lift=d.lift,
            sessions=d.sessions,
            picks=d.picks,
        )


@strawberry.type(
    description="A screener's record over its edge's frozen period, from the edge's canonical "
    "run (the latest site run whose split is the edge's `frozenFrom`); never an exploratory "
    "run. `runLabel` names the run; `runId`, the range, `splitFrom` and `knowledgeTs` disclose it"
)
class TrackRecord:
    screener_id: str
    edge_id: str
    run_id: str
    run_label: str
    range_from: dt.date | None
    range_to: dt.date
    split_from: dt.date | None
    knowledge_ts: dt.datetime
    horizons: list[TrackHorizon]

    @classmethod
    def of(cls, d: track_record.TrackRecord) -> Self:
        return cls(
            screener_id=d.screener_id,
            edge_id=d.edge_id,
            run_id=d.run_id,
            run_label=d.run_label,
            range_from=d.range_from,
            range_to=d.range_to,
            split_from=d.split_from,
            knowledge_ts=d.knowledge_ts,
            horizons=[TrackHorizon.of(h) for h in d.horizons],
        )
