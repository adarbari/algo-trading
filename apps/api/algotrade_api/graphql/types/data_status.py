"""``DataStatus``: how complete the served session's data is, for every viewer (the top bar's
pill). Public: a state, per-dataset shares and the count of the viewer's screeners it touches;
the gap of an ``UNKNOWN`` dataset is the shared ``Unavailable`` (a public kind), whose ``cause``
chain stays behind ``AdminCause`` (ADR 0056)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.availability import data_status
from algotrade_api.graphql.types.availability import Unavailable

strawberry.enum(data_status.DatasetName, description="A dataset the data status reports")
strawberry.enum(data_status.DatasetState, description="How much of a dataset the session has")
strawberry.enum(data_status.DataState, description="What the session's data amounts to")


@strawberry.type(
    description="One dataset on the session: `present` of `expected` (`share`, 0 to 1), graded "
    "as `status`; UNKNOWN (no record, never 0%) carries `unavailable` in public words"
)
class DatasetStatus:
    name: data_status.DatasetName
    status: data_status.DatasetState
    present: int | None
    expected: int | None
    share: float | None
    unavailable: list[Unavailable]

    @classmethod
    def of(cls, d: data_status.DatasetStatus) -> Self:
        return cls(
            name=d.name,
            status=d.status,
            present=d.present,
            expected=d.expected,
            share=d.share,
            unavailable=[Unavailable.of(u) for u in d.unavailable],
        )


@strawberry.type(
    description="The data of the served session in one object (every viewer): `state`, "
    "`knowledgeTs` (when the session completed; null: not yet), the `datasets`, and how many of "
    "the viewer's `totalScreeners` have no run, a partial run or a run without a required table "
    "(`affectedScreeners`)"
)
class DataStatus:
    state: data_status.DataState
    knowledge_ts: dt.datetime | None
    datasets: list[DatasetStatus]
    affected_screeners: int
    total_screeners: int

    @classmethod
    def of(cls, d: data_status.DataStatus) -> Self:
        return cls(
            state=d.state,
            knowledge_ts=d.knowledge_ts,
            datasets=[DatasetStatus.of(x) for x in d.datasets],
            affected_screeners=d.affected_screeners,
            total_screeners=d.total_screeners,
        )
