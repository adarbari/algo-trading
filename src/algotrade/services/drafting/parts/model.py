"""The shapes of the explained parts (ADR 0041, amended 2026-10-11): ``Part`` as the draft serves
it, ``Item`` as the attribution sees an item of the answer, the part id and tag rules, and the
caps. No logic beyond reading a tag."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeGuard

KINDS = ("applied", "formula", "needs_choice", "not_available", "not_understood")
ORIGINS = ("words", "gap", "kept", "unplaced")  # words: a part of the model, located; gap: words
# no part covers; kept / unplaced: catch-alls with no words
READING_SOURCES = ("model", "server")
GROUPS = ("criteria", "dropped", "formulas", "unresolved", "missing", "suggestions", "rank")

MAX_PARTS = 12  # parts that carry words (the model's located ones and the not-understood gaps)
MAX_WORDS = 200  # characters of a part's words
MAX_READING = 160  # characters of a part's reading
KEPT_ID = "kept"  # the catch-all parts: criteria carried over from ``current`` / tied to no words
UNPLACED_ID = "unplaced"
_ID = re.compile(r"^p[0-9]{1,3}$")  # what the model may call a part


@dataclass(frozen=True)
class Part:
    """One explained part of the sentence. ``words`` is the server's exact slice of the sentence
    (never the model's copy), ``start`` / ``end`` its offsets in UTF-16 code units (what the
    browser counts), both 0 and ``words`` empty for a catch-all part (``origin`` ``kept`` or
    ``unplaced``); a gap (``origin`` ``gap``) has words and offsets and no refs.
    ``reading_source`` is ``model`` when ``reading`` is the model's, ``server`` when the server
    wrote it (a draft the phrasebook made, from its entries' criteria) or when it is absent
    (the model's disagreed with the criteria: the web shows the rows alone). The refs name items
    of the same draft: the ids of criteria in the document and of the dropped ones, formula
    names, unresolved terms, the key (or new slug) of missing requests and suggestion ids;
    ``rank`` is true when the document's tie-break is this part's."""

    id: str
    words: str
    start: int
    end: int
    reading: str | None
    reading_source: str
    kind: str
    origin: str
    criteria: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    formulas: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    rank: bool = False


@dataclass(frozen=True)
class Item:
    """An item of the draft that belongs to a part. ``group`` is one of ``GROUPS`` and ``ref``
    its id there; ``tag`` the part id the model gave it; ``span`` the words the model quoted
    (unresolved, missing); ``field`` its catalogue field (the phrasebook step); ``carried`` a
    criterion equal to one of ``current``; ``numbers`` the values and numbers in names a reading
    of its part may cite (``consistency``)."""

    group: str
    ref: str
    tag: str | None = None
    span: str | None = None
    field: str | None = None
    carried: bool = False
    numbers: tuple[float, ...] = ()


@dataclass(frozen=True)
class PartsStats:
    """How the parts were made, for the golden scoring (never served): ``items`` (not the
    criteria kept from ``current``) attributed by
    the model's own tag, by a fallback, or to a catch-all; ``spans`` the model's parts and how
    many were located; ``not_understood`` the parts nothing points at (the model's own and the
    gaps between them); ``readings`` the model readings given and how many kept."""

    items: int = 0
    by_model: int = 0
    by_fallback: int = 0
    spans: int = 0
    located: int = 0
    not_understood: int = 0
    readings: int = 0
    readings_kept: int = 0


def part_tag(item: Any) -> str | None:
    """The part id ``item`` (a raw answer item) names in ``part``, if it is a well-formed one."""
    tag = item.get("part") if isinstance(item, Mapping) else None
    return tag if isinstance(tag, str) and _ID.match(tag) else None


def is_part_id(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(_ID.match(value))
