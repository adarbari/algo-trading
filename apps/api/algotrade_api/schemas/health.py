"""``GET /health``: the storage kind, the latest session, the stored tables and versions, the
build identity (the API's, the served web's, the checkout's and what disagrees, ADR 0044);
and the shared base model every area uses."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from algotrade.services.read.availability.cause import ADMIN_CAUSE


class Schema(BaseModel):
    """Base for every response model: built from the library's dataclasses by attribute."""

    model_config = ConfigDict(from_attributes=True)


class BuildStamp(Schema):
    git_sha: str
    schema_hash: str
    at: datetime | None  # the API: started; the web: built; the checkout: none


class Build(Schema):
    api: BuildStamp
    web: BuildStamp | None  # None: no web served, or a build without its stamp
    checkout: BuildStamp | None
    stale: bool
    mismatches: list[str]  # each with its fix (restart the API, rebuild the web)


class Health(Schema):
    status: str = "ok"
    storage: str
    latest_session: date | None
    tables: list[str] = Field(
        description="the stored tables (admins only: empty for anyone else, ADR 0056)",
        json_schema_extra={ADMIN_CAUSE: []},
    )
    versions: dict[str, str]
    build: Build
