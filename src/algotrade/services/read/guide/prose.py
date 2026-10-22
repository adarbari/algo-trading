"""Guide prose split for linking (ADR 0051; ADR 0038: the browser does not parse text): a
text becomes ``LinkedProse``, its segments in order, each plain text or one catalogue name
(``field``) the text mentions. A name matches exactly as written (``feature.atr_pct``,
``rollup.momentum@v1.rel_volume``) and only when the catalogue it is given holds it (site
prose: the site's); a trailing dot is the sentence's. A page that has sources
(``sources=<count>``) also gets its source markers ``[^n]`` (``config/site/guide/sources.py``) as
their own segments, ``n`` naming one of its ``count`` sources; without a count a marker is plain
text (the pages not yet written with sources). Joining the segments' text gives the text back
unchanged. The one splitter of the Guide: the field page's related fields come from it too."""

import re
from collections.abc import Container, Iterable
from dataclasses import dataclass

from algotrade.config.site.guide.sources import MARKER

# A token a catalogue name could be: letters, digits, ``_``, ``@`` and dots.
_TOKEN = re.compile(r"[A-Za-z0-9_@.]+")


@dataclass(frozen=True)
class ProseSegment:
    """A run of ``text``; ``field`` is set when the run is a catalogue name (then
    ``text == field``); ``source`` when it is a source marker (then ``text`` is the marker as
    written, ``[^n]``, and ``source`` is ``n``)."""

    text: str
    field: str | None = None
    source: int | None = None


@dataclass(frozen=True)
class LinkedProse:
    text: str
    segments: tuple[ProseSegment, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """The catalogue names mentioned, in order (repeats kept)."""
        return tuple(s.field for s in self.segments if s.field is not None)

    @property
    def sources(self) -> tuple[int, ...]:
        """The source numbers cited, in order (repeats kept)."""
        return tuple(s.source for s in self.segments if s.source is not None)


def name_tokens(text: str) -> list[str]:
    """Every word of ``text`` that could be a catalogue name (it has a dot inside it; a
    trailing dot is the sentence's), in order: the one tokeniser of the Guide's prose."""
    return [t for t in (m.group().rstrip(".") for m in _TOKEN.finditer(text)) if "." in t]


def link_prose(text: str, names: Container[str], sources: int | None = None) -> LinkedProse:
    """``text`` split at every name of ``names`` it mentions and, given ``sources`` (how many
    the page has), at every marker naming one of them (module docstring)."""
    if sources is None:
        return LinkedProse(text, tuple(_names(text, names)))
    segments: list[ProseSegment] = []
    start = 0
    for marker in MARKER.finditer(text):
        n = int(marker.group(1))
        if not 1 <= n <= sources:
            continue
        segments += _names(text[start : marker.start()], names)
        segments.append(ProseSegment(marker.group(), source=n))
        start = marker.end()
    segments += _names(text[start:], names)
    return LinkedProse(text, tuple(segments))


def _names(text: str, names: Container[str]) -> list[ProseSegment]:
    """``text`` split at the catalogue names it mentions."""
    segments: list[ProseSegment] = []
    start = 0
    for match in _TOKEN.finditer(text):
        name = match.group().rstrip(".")
        if "." not in name or name not in names:
            continue
        if match.start() > start:
            segments.append(ProseSegment(text[start : match.start()]))
        segments.append(ProseSegment(name, name))
        start = match.start() + len(name)
    if start < len(text):
        segments.append(ProseSegment(text[start:]))
    return segments


def mentions(texts: Iterable[str], names: Container[str]) -> list[str]:
    """Every catalogue name of ``names`` that ``texts`` mention, in order (repeats kept)."""
    return [f for text in texts for f in link_prose(text, names).fields]
