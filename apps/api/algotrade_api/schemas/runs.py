"""``/runs``: nightly run summaries and one run's detail."""

from datetime import date, datetime
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Schema


class Step(Schema):
    name: str
    status: str
    duration_s: float | None
    reason: str | None
    error: str | None
    counts: dict[str, Any]


class NightlyRun(Schema):
    run_id: str
    session: date
    status: str = Field(description="queued | running | complete | partial | failed")
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    steps: list[Step] = Field(description="the workflow's steps in order")
    problems: list[str] = Field(description="why the run is partial or failed")


class FailureGroup(Schema):
    reason: str = Field(
        description="normalised: code + message without ids, URLs, dates or numbers"
    )
    count: int
    examples: list[str] = Field(
        description="item keys (tickers, instrument ids, steps), at most 10"
    )
    statuses: list[str] = Field(description="distinct statuses as recorded, at most 10")


class RunDetail(Schema):
    run_id: str
    job: str = Field(
        description="the run-record job (daily_bars, option_chains, nightly, screen-...)"
    )
    session: date
    status: str = Field(description="queued | running | complete | partial | failed")
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None = Field(description="finished - started, seconds (null while running)")
    items_total: int
    items_by_status: dict[str, int] = Field(
        description="item status code -> count, most common first"
    )
    failures: list[FailureGroup] = Field(
        description="items not fine, grouped by normalised reason, largest first"
    )
    stats: dict[str, Any] = Field(description="the run's stats as recorded (counts, audit, errors)")
