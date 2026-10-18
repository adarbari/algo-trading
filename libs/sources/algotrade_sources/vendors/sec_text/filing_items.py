"""A 10-K / 10-Q document -> plain text -> its item sections (edge build D10). Pure functions: no
network, no storage, no clock.

**Text** (``html_to_text``): the inline-XBRL HTML SEC serves as ``primaryDocument`` is read with
the standard library's ``HTMLParser`` (no new dependency). Block tags break a line, table cells are
joined by a space, ``script`` / ``style`` / ``head`` and the hidden XBRL header (``ix:header``,
``display:none``) are dropped, runs of white space (``&nbsp;`` too) collapse to one space, and the
lines that are only a page number or the running "Table of Contents" back-link are removed, so two
years of the same filing differ only where the words differ.

**Items** (``extract_items``): the well-known "Item 1A." header patterns, written here (the GPL-3
EDGAR-CRAWLER is never imported or vendored). A header is a line that starts with ``Item <n>[A-C]``
(optionally ``PART II`` before it), whose title is short, starts with a capital and is not a
cross-reference ("... of this Annual Report", "see ..."). The table of contents and the body both
hold the headers, so for each item the candidate with the LONGEST section wins (a section runs to
the next header of a later item, or, for the last of a run such as the contents' final entry, to
the numbering starting over; a repeated header of the same item, a page header, does not cut it).
A 10-K's ids are ``1``, ``1A``, ``7`` ...; a 10-Q's carry the part (``I-2`` MD&A, ``I-3`` market
risk, ``II-1`` legal proceedings, ``II-1A`` risk factors): the part comes from the ``PART`` header
lines, or, with none, from the item number falling back to ``1`` after Part I.

**Quality** per row, never guessed text: ``OK``; ``SHORT`` (under ``MIN_CHARS``: "None",
"Not applicable", an incorporation by reference, or a table-of-contents entry; kept as found);
``TRUNCATED`` (over ``MAX_CHARS``: cut, a runaway section); ``NOT_FOUND`` (a wanted item with no
header: no text, a reason); ``NO_ITEMS`` (no header of the form at all, one row with a null item:
a partial amendment or a layout the patterns do not read). ``PARSER_VERSION`` goes up with any
change that can change a stored text: the task stores it with every row and treats a new version
as a revision known only from the day it ran, never from the filing's acceptance.
"""

import re
from collections.abc import Collection
from html.parser import HTMLParser
from typing import Any

from algotrade_sources.framework.series import (
    FILING_TEXT_PARSER_VERSION,
    TEN_K_ITEMS,
    TEN_Q_ITEMS,
    is_quarterly,
    item_order,
)

PARSER_VERSION = FILING_TEXT_PARSER_VERSION
METHOD = "item_headers"
MIN_CHARS = 200  # under this a section is flagged SHORT
MAX_CHARS = 1_500_000  # over this it is cut and flagged TRUNCATED (a runaway section)
OK, SHORT, TRUNCATED, NOT_FOUND, NO_ITEMS = "OK", "SHORT", "TRUNCATED", "NOT_FOUND", "NO_ITEMS"

_BLOCK = frozenset(
    {"p", "div", "br", "tr", "li", "ul", "ol", "table", "hr", "center", "pre", "blockquote",
     "section", "article", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6"}
)  # fmt: skip
_CELL = frozenset({"td", "th"})
_SKIP = frozenset({"script", "style", "head", "title", "ix:header"})
_HIDDEN = re.compile(r"display\s*:\s*none", re.IGNORECASE)
_SPACES = str.maketrans(dict.fromkeys("\xa0\u2002\u2003\u2009\u200a\u200b\u202f\u2007\ufeff", " "))
_PAGE = re.compile(r"^(?:page\s+)?[-\u2013]?\s*(?:[A-Z]-)?\d{1,3}\s*[-\u2013]?$", re.IGNORECASE)
_CONTENTS = re.compile(r"^(?:back to )?(?:table of contents|index)$", re.IGNORECASE)


class _Text(HTMLParser):
    """Collects the visible text, one line per block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip: dict[str, int] = {}
        self._hidden = 0  # nesting depth inside a ``display:none`` div

    def _skipping(self) -> bool:
        return self._hidden > 0 or any(self._skip.values())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip[tag] = self._skip.get(tag, 0) + 1
        elif tag == "div" and self._hidden:
            self._hidden += 1
        elif tag == "div" and _HIDDEN.search(dict(attrs).get("style") or ""):
            self._hidden = 1
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip.get(tag):
            self._skip[tag] -= 1
        elif tag == "div" and self._hidden:
            self._hidden -= 1
        if tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _CELL:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skipping():
            self.parts.append(data)


def decode(document: bytes) -> str:
    """UTF-8 when it is, else Windows-1252 (older filings); never an error."""
    try:
        return document.decode("utf-8")
    except UnicodeDecodeError:
        return document.decode("cp1252", errors="replace")


def html_to_text(document: bytes) -> str:
    """The visible text of ``document`` (module doc): one paragraph or table row a line."""
    parser = _Text()
    parser.feed(decode(document))
    parser.close()
    lines = []
    for raw in "".join(parser.parts).translate(_SPACES).splitlines():
        line = " ".join(raw.split())
        if line and not _PAGE.match(line) and not _CONTENTS.match(line):
            lines.append(line)
    return "\n".join(lines)


_PART = re.compile(r"^part\s+(?P<part>iv|iii|ii|i)\b\s*(?:[.:,\u2013\u2014-]|$)", re.IGNORECASE)
_ITEM = re.compile(
    r"^(?:part\s+(?P<part>iv|iii|ii|i)\b[\s.,:\u2013\u2014-]*)?"
    r"items?\s*(?P<num>\d{1,2})(?P<suffix>[a-c])?(?![a-z0-9])\s*[.:\u2013\u2014-]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
_CROSS_REFERENCE = re.compile(r"\b(?:of this|of part|in this|see|refer to)\b", re.IGNORECASE)
MAX_TITLE = 160  # a longer line after "Item 7." is a sentence, not a header


def _is_header_title(title: str) -> bool:
    """A header's title is short, starts with a capital (or a digit/quote) or is empty, and is no
    cross-reference."""
    if len(title) > MAX_TITLE or _CROSS_REFERENCE.search(title):
        return False
    return not title or not title[0].islower()


def _marks(text: str, quarterly: bool) -> list[tuple[int, int, str]]:
    """(line start, title start, item id) of every header line, in document order."""
    order = set(TEN_Q_ITEMS if quarterly else TEN_K_ITEMS)
    marks: list[tuple[int, int, str]] = []
    part, last = "I", 0
    pos = 0
    for line in text.split("\n"):
        start, pos = pos, pos + len(line) + 1
        if quarterly and (found := _PART.match(line)) and len(line) <= 90:
            part, last = found["part"].upper(), 0
            continue
        head = _ITEM.match(line)
        if head is None or not _is_header_title(head["title"]):
            continue
        number = int(head["num"])
        if quarterly:
            if head["part"]:
                part = head["part"].upper()
            elif number < last and part == "I":  # no PART line: the numbers start over in Part II
                part = "II"
            last = number
        item = (
            f"{part}-{number}{(head['suffix'] or '').upper()}"
            if quarterly
            else (f"{number}{(head['suffix'] or '').upper()}")
        )
        if item in order:
            marks.append((start, start + head.start("title"), item))
    return marks


def sections(text: str, form: str) -> dict[str, str]:
    """Item id -> its text (module doc: the longest candidate per item) for every item the
    headers of ``text`` name."""
    order = {item: i for i, item in enumerate(item_order(form))}
    marks = _marks(text, is_quarterly(form))
    best: dict[str, tuple[int, int, int]] = {}
    for i, (_, body, item) in enumerate(marks):
        later = marks[i + 1 :]
        end = next((s for s, _, other in later if order[other] > order[item]), None)
        if end is None:  # the last of its run: the numbering starting over ends it (the contents)
            end = next((s for s, _, other in later if order[other] < order[item]), len(text))
        if item not in best or end - body >= best[item][0]:  # a tie goes to the later one
            best[item] = (end - body, body, end)
    return {item: text[body:end].strip() for item, (_, body, end) in best.items()}


def _row(item: str | None, text: str | None, quality: str, reason: str | None) -> dict[str, Any]:
    return {
        "item": item,
        "text": text,
        "char_count": len(text or ""),
        "quality": quality,
        "reason": reason,
        "method": METHOD,
        "parser_version": PARSER_VERSION,
    }


def extract_items(document: bytes, form: str, wanted: Collection[str]) -> list[dict[str, Any]]:
    """``extract_text`` of ``document``'s visible text."""
    return extract_text(html_to_text(document), form, wanted)


def extract_text(text: str, form: str, wanted: Collection[str]) -> list[dict[str, Any]]:
    """The rows of ``wanted`` items found in ``text`` (module doc), in filing order: each
    ``FILING_TEXT_COLUMNS`` key. A text with no item header at all is one row with a null item
    (``NO_ITEMS``); a wanted item without a header is a ``NOT_FOUND`` row."""
    found = sections(text, form)
    if not found:
        return [_row(None, None, NO_ITEMS, "no Item headers found in the document")]
    rows = []
    for item in item_order(form):
        if item not in wanted:
            continue
        body = found.get(item)
        if body is None:
            rows.append(_row(item, None, NOT_FOUND, "no header for this item"))
        elif len(body) > MAX_CHARS:
            rows.append(_row(item, body[:MAX_CHARS], TRUNCATED, f"cut at {MAX_CHARS} characters"))
        elif len(body) < MIN_CHARS:
            rows.append(_row(item, body, SHORT, f"{len(body)} characters"))
        else:
            rows.append(_row(item, body, OK, None))
    return rows
