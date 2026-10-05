"""``NightlyRun`` (one session's nightly workflow, step by step), ``RunDetail`` (one run record:
items summarised, failures grouped by reason) and ``RunItem`` (one item with its status)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.ops import runs


@strawberry.type(description="One step of a nightly run: `counts` its result counts as recorded")
class RunStep:
    name: str
    status: str
    duration_s: float | None
    reason: str | None
    error: str | None
    counts: JSON

    @classmethod
    def of(cls, d: runs.RunStep) -> Self:
        return cls(
            name=d.name,
            status=d.status,
            duration_s=d.duration_s,
            reason=d.reason,
            error=d.error,
            counts=JSON(d.counts),
        )


@strawberry.type(
    description="One session's nightly run: `status` queued, running, complete, partial or "
    "failed; `steps` in workflow order; `problems` why it is partial or failed"
)
class NightlyRun:
    run_id: str
    session: dt.date
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    duration_s: float | None
    steps: list[RunStep]
    problems: list[str]

    @classmethod
    def of(cls, d: runs.NightlyRun) -> Self:
        return cls(
            run_id=d.run_id,
            session=d.session,
            status=d.status,
            started_at=d.started_at,
            finished_at=d.finished_at,
            duration_s=d.duration_s,
            steps=[RunStep.of(s) for s in d.steps],
            problems=list(d.problems),
        )


@strawberry.type(
    description="Items not fine, grouped by a normalised `reason` (code + message without ids, "
    "URLs, dates or numbers): `examples` item keys (at most 10), `statuses` the distinct "
    "statuses as recorded (at most 10)"
)
class FailureGroup:
    reason: str
    count: int
    examples: list[str]
    statuses: list[str]

    @classmethod
    def of(cls, d: runs.FailureGroup) -> Self:
        return cls(
            reason=d.reason,
            count=d.count,
            examples=list(d.examples),
            statuses=list(d.statuses),
        )


@strawberry.type(
    description="One run record: `job` (daily_bars, option_chains, nightly, screen-...), "
    "`itemsByStatus` status code -> count (most common first), `failures` largest group "
    "first, `stats` as recorded (counts, audit, errors)"
)
class RunDetail:
    run_id: str
    job: str
    session: dt.date
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    duration_s: float | None
    items_total: int
    items_by_status: JSON
    failures: list[FailureGroup]
    stats: JSON

    @classmethod
    def of(cls, d: runs.RunDetail) -> Self:
        return cls(
            run_id=d.run_id,
            job=d.job,
            session=d.session,
            status=d.status,
            started_at=d.started_at,
            finished_at=d.finished_at,
            duration_s=d.duration_s,
            items_total=d.items_total,
            items_by_status=JSON(d.items_by_status),
            failures=[FailureGroup.of(g) for g in d.failures],
            stats=JSON(d.stats),
        )


@strawberry.type(
    description="One item of a run: `key` (a ticker, an instrument id, a step, a check), its "
    "status `code` (STALE_DATA) and `status` as recorded, with its detail after a colon"
)
class RunItem:
    key: str
    code: str
    status: str

    @classmethod
    def of(cls, d: runs.RunItem) -> Self:
        return cls(key=d.key, code=d.code, status=d.status)
