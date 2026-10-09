"""``/edges/{id}``: the bodies and answers of a user's edge writes (copy, save, delete, state).
Reading an edge, its state, runs and comparison is GraphQL (``Query.edge``)."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class CopyEdgeBody(BaseModel):
    new_id: str = Field(description="the id of the copy (1-64 of a-z, 0-9, _ and -)")
    as_version: bool = Field(
        default=False,
        description="a new version: the copy is a trial that would replace the edge",
    )


class SaveEdgeBody(BaseModel):
    document: dict[str, Any] = Field(
        description="the edge's TOML keys as JSON: `extends` and the settings it changes "
        "(a `[follow]` table in it is ignored: the state has its own call)"
    )


class EdgeDocument(Schema):
    edge_id: str
    document: dict[str, Any]


class StateBody(BaseModel):
    state: str | None = Field(
        default=None,
        description="researching | following | rejected | retired | trial; none keeps it",
    )
    reason: str = Field(default="", description="why: a rejection needs one, a retirement may")
    reveal_oos: bool = Field(
        default=False, description="show the copy's out-of-sample result (it is hidden until then)"
    )


class EdgeState(Schema):
    edge_id: str
    state: str
    since: date | None
    reason: str
    replaces: str | None
    labels: list[str]
    oos_revealed: bool
