"""``/screeners``: a user's rule screen (draft, versions, schedule, preset pin) and the
bodies of its writes."""

from typing import Any

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class PresetPin(Schema):
    preset_id: str
    pinned: int | None = Field(description="the preset version the screen extends")
    current: int | None = Field(description="the site preset's version now")
    rebase_available: bool


class ScreenerDetail(Schema):
    screener_id: str
    user: str
    draft: dict[str, Any] | None = Field(description="the Builder's working copy")
    draft_error: str | None = Field(description="why the draft would not finalise")
    versions: list[int]
    latest: int | None
    schedule: str | None
    preset: PresetPin | None
    hash: str | None = Field(description="the latest version (else the site preset) resolved")
    layers: list[str]
    resolved: dict[str, Any] | None
    error: str | None = Field(description="why that does not resolve (e.g. rebase needed)")


class ScreenerVersion(Schema):
    version: int
    document: dict[str, Any]


class Finalised(Schema):
    screener_id: str
    version: int
    hash: str


class Draft(Schema):
    screener_id: str
    document: dict[str, Any]


class DraftBody(BaseModel):
    document: dict[str, Any] = Field(
        description="the screen's TOML keys as JSON (version and schedule are managed)"
    )


class CopyBody(BaseModel):
    preset: str = Field(description="the site rule-screen preset to extend (pinned)")


class ScheduleBody(BaseModel):
    schedule: str | None = Field(description='"nightly", or null to switch it off')


class Schedule(Schema):
    screener_id: str
    schedule: str | None
