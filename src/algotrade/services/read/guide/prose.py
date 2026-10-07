"""Guide prose split for linking (ADR 0051; ADR 0038: the browser does not parse text): a
text becomes ``LinkedProse``, its segments in order, each plain text or one catalogue name
(``field``) the text mentions. A name matches exactly as written (``feature.atr_pct``,
``rollup.momentum@v1.rel_volume``) and only when the caller's catalogue holds it; a trailing
dot is the sentence's. Joining the segments' text gives the text back unchanged. The one
splitter of the Guide: the field page's related fields come from it too."""

import re
from collections.abc import Container, Iterable
from dataclasses import dataclass

# A token a catalogue name could be: letters, digits, ``_``, ``@`` and dots.
_TOKEN = re.compile(r"[A-Za-z0-9_@.]+")


@dataclass(frozen=True)
class ProseSegment:
    """A run of ``text``; ``field`` is set when the run is a catalogue name (then
    ``text == field``)."""

    text: str
    field: str | None = None


@dataclass(frozen=True)
class LinkedProse:
    text: str
    segments: tuple[ProseSegment, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """The catalogue names mentioned, in order (repeats kept)."""
        return tuple(s.field for s in self.segments if s.field is not None)


def link_prose(text: str, names: Container[str]) -> LinkedProse:
    """``text`` split at every name of ``names`` it mentions (module docstring)."""
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
    return LinkedProse(text, tuple(segments))


def mentions(texts: Iterable[str], names: Container[str]) -> list[str]:
    """Every catalogue name of ``names`` that ``texts`` mention, in order (repeats kept)."""
    return [f for text in texts for f in link_prose(text, names).fields]
