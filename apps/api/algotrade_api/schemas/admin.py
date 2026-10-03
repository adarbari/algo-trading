"""``/admin``: ingestion completeness (dataset x session), one cell's drill-down and the live
verification vs IBKR."""

from datetime import date
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Schema
from algotrade_api.schemas.runs import FailureGroup, RunDetail


class Cell(Schema):
    dataset: str
    session: date
    status: str
    present: int
    expected: int | None
    basis: str
    run_ids: list[str]


class Completeness(Schema):
    sessions: list[date]
    datasets: list[str]
    cells: list[Cell]
    last_closed: date = Field(
        description="the exchange's last closed session; later than the last of `sessions` "
        "means the store is stale"
    )


class CellDetail(Schema):
    cell: Cell
    job: str
    groups: list[FailureGroup]
    runs: list[RunDetail]


class CheckCounts(Schema):
    check: str
    counts: dict[str, int] = Field(description="PASS / WARN / FAIL / NA -> rows")


class Verification(Schema):
    session: date = Field(description="the partition shown: latest on or before the date")
    run_ids: list[str]
    instruments: int
    counts: dict[str, int] = Field(description="PASS / WARN / FAIL / NA over every row")
    by_check: list[CheckCounts] = Field(description="most failures first")
    failing: list[dict[str, Any]] = Field(
        description="FAIL then WARN rows (at most 50), largest diff first: instrument_id, "
        "symbol, check, status, ours, theirs, diff, tolerance, note"
    )
