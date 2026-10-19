"""``GuideProse``: Guide prose split at the catalogue names it mentions (ADR 0051; the browser
does not parse text, ADR 0038): the segments in order, each plain text, one field or one
source marker."""

from typing import Self

import strawberry

from algotrade.services.read.guide import prose


@strawberry.type(
    description="A run of Guide prose: `field` is the catalogue name it is (then `text` is "
    "that name), `source` the 1-based number of the page's source it cites (then `text` is the "
    "marker as written, `[^n]`), null for plain text"
)
class GuideProseSegment:
    text: str
    field: str | None
    source: int | None

    @classmethod
    def of(cls, d: prose.ProseSegment) -> Self:
        return cls(text=d.text, field=d.field, source=d.source)


@strawberry.type(
    description="Guide prose and its `segments` in order (joined, they are `text`): each plain "
    "text, a catalogue name in the caller's catalogue (matched exactly as written) or, on a page "
    "with sources, a source marker"
)
class GuideProse:
    text: str
    segments: list[GuideProseSegment]

    @classmethod
    def of(cls, d: prose.LinkedProse) -> Self:
        return cls(text=d.text, segments=[GuideProseSegment.of(s) for s in d.segments])
