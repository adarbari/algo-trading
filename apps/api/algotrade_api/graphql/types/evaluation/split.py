"""``EvaluationSplit``: the user's train / test split, the frozen periods of the edges they see
and the latest session a split may name (the write is ``PUT /evaluation/split``)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.evaluation import split


@strawberry.type(description="One edge's frozen period: the first session of its test slice")
class FrozenPeriod:
    edge_id: str
    frozen_from: dt.date

    @classmethod
    def of(cls, d: split.FrozenPeriod) -> Self:
        return cls(edge_id=d.edge_id, frozen_from=d.frozen_from)


@strawberry.type(
    description="The user's own `splitFrom` (null: none set, so each edge's frozen period is "
    "the split), the `frozenPeriods` of the edges they see and the `latestSession` a split "
    "may name. A run under a personal split is exploratory"
)
class EvaluationSplit:
    split_from: dt.date | None
    frozen_periods: list[FrozenPeriod]
    latest_session: dt.date

    @classmethod
    def of(cls, d: split.EvaluationSplit) -> Self:
        return cls(
            split_from=d.split_from,
            frozen_periods=[FrozenPeriod.of(p) for p in d.frozen_periods],
            latest_session=d.latest_session,
        )
