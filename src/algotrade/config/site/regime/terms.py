"""A card's linked how-line (``config/site/regime/cards.toml`` ``how`` and ``terms``): the
sentence split into ``TextPart``s, each a run of plain text or one linked term, so a page
renders it without searching the text itself (ADR 0038: the browser derives nothing).

Rules, each failing with the card named: every term's text occurs exactly once in the
sentence as a whole word or phrase (``VIX`` does not match inside ``VIX3M``), not counting
where it sits inside a longer term (``VIX`` inside ``three-month VIX``); two terms never
partly overlap; every link is ``https``."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from algotrade.core.model.errors import ConfigurationError


@dataclass(frozen=True)
class TextPart:
    """A run of the sentence: plain text (``url`` ``None``) or a linked term."""

    text: str
    url: str | None = None


@dataclass(frozen=True)
class Term:
    """A phrase of the sentence and the ``https`` page that explains it."""

    text: str
    url: str


def https(url: str, where: str) -> str:
    """``url`` when it is an ``https`` URL with a host, else a ``ConfigurationError``."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigurationError(f"{where}: expected an https URL, got {url!r}")
    return url


def _spans(sentence: str, text: str) -> list[tuple[int, int]]:
    pattern = re.compile(rf"(?<!\w){re.escape(text)}(?!\w)")
    return [(m.start(), m.end()) for m in pattern.finditer(sentence)]


def split(sentence: str, terms: tuple[Term, ...], where: str) -> tuple[TextPart, ...]:
    """``sentence`` as parts, each term linked at its one occurrence (longest terms first, so a
    shorter term inside a longer one is not an occurrence of its own)."""
    repeated = sorted({t.text for t in terms if [u.text for u in terms].count(t.text) > 1})
    if repeated:
        raise ConfigurationError(f"{where} terms: declared more than once: {repeated}")
    claimed: list[tuple[int, int, str]] = []
    for term in sorted(terms, key=lambda t: -len(t.text)):
        own = []
        for start, end in _spans(sentence, term.text):
            if any(c[0] <= start and end <= c[1] for c in claimed):
                continue  # inside a longer term: that term's link
            hit = next((c for c in claimed if start < c[1] and c[0] < end), None)
            if hit is not None:
                other = sentence[hit[0] : hit[1]]
                raise ConfigurationError(f"{where} terms: {term.text!r} overlaps {other!r}")
            own.append((start, end))
        if len(own) != 1:
            raise ConfigurationError(
                f"{where} terms: {term.text!r} must occur exactly once in how, found {len(own)}"
            )
        claimed.append((*own[0], term.url))
    parts: list[TextPart] = []
    at = 0
    for start, end, url in sorted(claimed):
        if start > at:
            parts.append(TextPart(sentence[at:start]))
        parts.append(TextPart(sentence[start:end], url))
        at = end
    if at < len(sentence):
        parts.append(TextPart(sentence[at:]))
    return tuple(parts)
