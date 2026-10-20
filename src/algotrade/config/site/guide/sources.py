"""The Guide's inline source marker and the ``[[sources]]`` list it points into (ADR 0051; spec
``docs/ui/guide.md`` "Sources in the text"): a prose string carries ``[^n]`` where the claim it
backs is said, ``n`` the 1-based position of an entry in the same file's ``[[sources]]``
(``title``, an https ``url`` that may be left out when no verified page exists, ``note``: what
the source shows). The one definition of the marker (``MARKER``), of how a source table is read
(``sources_of``), of ``plain`` text and of the checks every file with sources shares
(``check_markers``: each marker names a source that exists). That every source is cited at
least once is a fitness test over the shipped files. The server turns a marker into a
``SOURCE`` segment of the linked prose (``services/read/guide/prose.py``); the browser never
reads one."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from algotrade.config.site.fields import Table, unique
from algotrade.core.model.errors import ConfigurationError

MARKER = re.compile(r"\[\^(\d+)\]")
SOURCE_KEYS = ("title", "url", "note")


@dataclass(frozen=True)
class GuideSource:
    """One source: ``title`` (the citation), ``url`` (https; ``None``: no verified page) and
    ``note`` (what it shows)."""

    title: str
    url: str | None
    note: str


def markers(text: str) -> list[int]:
    """The source numbers ``text`` cites, in order (repeats kept)."""
    return [int(m.group(1)) for m in MARKER.finditer(text)]


def plain(text: str) -> str:
    """``text`` without its markers (for search and snippets, which show words only)."""
    return MARKER.sub("", text)


def sources_of(t: Table) -> tuple[GuideSource, ...]:
    """``[[sources]]`` of ``t``: known keys, non-empty text, an https url (or none), no url
    twice."""
    found = tuple(_source(s) for s in t.tables("sources"))
    unique(t.where, "source urls", (s.url for s in found if s.url is not None))
    return found


def check_markers(where: str, texts: Iterable[str], count: int) -> None:
    """Every marker of ``texts`` names one of the ``count`` sources (1-based)."""
    for text in texts:
        for n in markers(text):
            if not 1 <= n <= count:
                raise ConfigurationError(
                    f"{where}: marker [^{n}] but there are {count} sources (1 to {count})"
                )


def _source(t: Table) -> GuideSource:
    t.only(SOURCE_KEYS)
    url = t.line("url") if t.raw("url") is not None else None
    if url is not None and (not url.startswith("https://") or " " in url):
        raise ConfigurationError(f"{t.where} url: expected an https url, got {url!r}")
    return GuideSource(t.line("title"), url, t.line("note"))
