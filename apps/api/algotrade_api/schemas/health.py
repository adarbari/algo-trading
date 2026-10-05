"""``GET /health``: the storage kind, the latest session, the stored tables and versions;
and the shared base model every area uses."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base for every response model: built from the library's dataclasses by attribute."""

    model_config = ConfigDict(from_attributes=True)


class Health(Schema):
    status: str = "ok"
    storage: str
    latest_session: date | None
    tables: list[str]
    versions: dict[str, str]
