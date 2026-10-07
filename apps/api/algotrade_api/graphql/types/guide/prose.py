"""``GuideProse``: Guide prose split at the catalogue names it mentions (ADR 0051; the browser
does not parse text, ADR 0038): the segments in order, each plain text or one field."""

from typing import Self

import strawberry

from algotrade.services.read.guide import prose


@strawberry.type(
    description="A run of Guide prose: `field` is the catalogue name it is (then `text` is "
    "that name), null for plain text"
)
class GuideProseSegment:
    text: str
    field: str | None

    @classmethod
    def of(cls, d: prose.ProseSegment) -> Self:
        return cls(text=d.text, field=d.field)


@strawberry.type(
    description="Guide prose and its `segments` in order (joined, they are `text`): each plain "
    "text or a catalogue name in the caller's catalogue, matched exactly as written"
)
class GuideProse:
    text: str
    segments: list[GuideProseSegment]

    @classmethod
    def of(cls, d: prose.LinkedProse) -> Self:
        return cls(text=d.text, segments=[GuideProseSegment.of(s) for s in d.segments])
