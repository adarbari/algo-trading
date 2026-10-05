"""``/screeners``: a user's rule screen (draft, versions, preset pin) and the
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
    preset: PresetPin | None
    hash: str | None = Field(description="the latest version (else the site preset) resolved")
    layers: list[str]
    resolved: dict[str, Any] | None
    error: str | None = Field(description="why that does not resolve (e.g. rebase needed)")
    working: dict[str, Any] | None = Field(
        None,
        description="the working copy's rule keys (criteria, flags, ...) resolved through its "
        "layers: the draft when it resolves, else the latest version, else the preset",
    )


class ScreenerListItem(Schema):
    screener_id: str
    status: str = Field(description="FINAL (has a finalised version) or DRAFT (a draft only)")
    latest: int | None
    has_draft: bool = Field(description="a working copy exists (beside a finalised version too)")
    preset_id: str | None = Field(description="the site preset the screen extends")


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
        description="the screen's TOML keys as JSON (the version is managed)"
    )


class CopyBody(BaseModel):
    preset: str = Field(description="the site rule-screen preset to extend (pinned)")
