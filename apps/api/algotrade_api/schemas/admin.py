"""``/admin``: ingestion completeness (dataset x session) and one cell's drill-down."""

from datetime import date

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


class CellDetail(Schema):
    cell: Cell
    job: str
    groups: list[FailureGroup]
    runs: list[RunDetail]
