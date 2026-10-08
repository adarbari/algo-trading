"""``TrackRecord``: a screener's frozen-period record from the canonical run of an edge that
lists it (the frozen slice only; an exploratory run never reaches it)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.evaluation import track_record
from algotrade_api.graphql.types.instruments.feature import Unknown


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
    description="A screener's record over one edge's frozen period, from the edge's canonical "
    "run (the latest site run whose split is the edge's `frozenFrom`); never an exploratory "
    "run. `runLabel` names the run; `runId`, the range, `splitFrom` and `knowledgeTs` disclose "
    "it; `afterSession`: the run committed after the request's session. "
    "`notRun` says why there is none (NOT_RUN); null: it has one"
)
class TrackRecord:
    screener_id: str
    edge_id: str
    edge_name: str
    not_run: Unknown | None
    run_id: str | None
    run_label: str | None
    range_from: dt.date | None
    range_to: dt.date | None
    split_from: dt.date | None
    knowledge_ts: dt.datetime | None
    horizons: list[TrackHorizon]
    after_session: bool

    @classmethod
    def of(cls, d: track_record.TrackRecord) -> Self:
        return cls(
            screener_id=d.screener_id,
            edge_id=d.edge_id,
            edge_name=d.edge_name,
            not_run=Unknown.of(d.not_run) if d.not_run is not None else None,
            run_id=d.run_id,
            run_label=d.run_label,
            range_from=d.range_from,
            range_to=d.range_to,
            split_from=d.split_from,
            knowledge_ts=d.knowledge_ts,
            horizons=[TrackHorizon.of(h) for h in d.horizons],
            after_session=d.after_session,
        )
