"""A user's rule screens as the Builder reads them: ``ScreenListing`` (one of their screens),
``ScreenDetail`` (a screen's draft, versions, preset pin and resolved working copy) and
``ScreenVersion`` (a finalised version's document). Writes stay REST (ADR 0029)."""

from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.screens import documents


@strawberry.type(
    description="The site preset a screen extends: `pinned` the version it extends (null: not "
    "copied yet), `current` the preset's version now"
)
class PresetPin:
    preset_id: str
    pinned: int | None
    current: int | None
    rebase_available: bool

    @classmethod
    def of(cls, d: documents.PresetPin) -> Self:
        return cls(
            preset_id=d.preset_id,
            pinned=d.pinned,
            current=d.current,
            rebase_available=d.rebase_available,
        )


@strawberry.type(
    description="One of the user's screens: `status` FINAL (has a finalised version) or DRAFT "
    "(a draft only); `presetId` the site preset it extends"
)
class ScreenListing:
    screener_id: str
    status: str
    latest: int | None
    has_draft: bool
    preset_id: str | None

    @classmethod
    def of(cls, d: documents.ScreenListing) -> Self:
        return cls(
            screener_id=d.screener_id,
            status=d.status,
            latest=d.latest,
            has_draft=d.has_draft,
            preset_id=d.preset_id,
        )


@strawberry.type(
    description="A screen of the user (or a preset not copied yet): the `draft` and why it "
    "would not finalise (`draftError`), its `versions`, the `preset` it is pinned to, the "
    "latest version resolved (`hash`, `layers`, `resolved`, `error`) and `working`, the rule "
    "keys the Builder edits"
)
class ScreenDetail:
    screener_id: str
    user: str
    draft: JSON | None
    draft_error: str | None
    versions: list[int]
    latest: int | None
    preset: PresetPin | None
    hash: str | None
    layers: list[str]
    resolved: JSON | None
    error: str | None
    working: JSON | None

    @classmethod
    def of(cls, d: documents.ScreenDetail) -> Self:
        return cls(
            screener_id=d.screener_id,
            user=d.user,
            draft=JSON(d.draft) if d.draft is not None else None,
            draft_error=d.draft_error,
            versions=list(d.versions),
            latest=d.latest,
            preset=PresetPin.of(d.preset) if d.preset is not None else None,
            hash=d.hash,
            layers=list(d.layers),
            resolved=JSON(d.resolved) if d.resolved is not None else None,
            error=d.error,
            working=JSON(d.working) if d.working is not None else None,
        )


@strawberry.type(description="A finalised (immutable) version of a screen and its document")
class ScreenVersion:
    version: int
    document: JSON

    @classmethod
    def of(cls, d: documents.ScreenVersion) -> Self:
        return cls(version=d.version, document=JSON(d.document))
