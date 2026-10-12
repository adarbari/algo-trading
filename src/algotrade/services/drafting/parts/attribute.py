"""Which part an item belongs to (ADR 0041, amended 2026-10-11), deterministically and in this
order: the part the model tagged it with (when that part was located), else the part whose words
contain the item's ``span`` (an unresolved term, a missing request), else the first part whose
words say a phrasebook entry for the item's field, else a catch-all: ``kept`` for a criterion
carried over from the Builder's current document, ``unplaced`` for the rest. A tag that names no
located part is not an error: the item goes down the same list."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.parts.model import KEPT_ID, UNPLACED_ID, Item
from algotrade.services.drafting.parts.spans import locate
from algotrade.services.drafting.retrieval import phrase_matches


@dataclass(frozen=True)
class Placed:
    """The words of one located part, for the fallback steps."""

    id: str
    words: str


def attribute(
    items: Sequence[Item], placed: Sequence[Placed], phrasebook: Sequence[Phrase]
) -> tuple[dict[str, list[Item]], int]:
    """The items of each part id (and ``KEPT_ID`` / ``UNPLACED_ID``), in item order, and how
    many were placed by the model's own tag."""
    known = {p.id for p in placed}
    by_field: dict[str, list[Phrase]] = {}
    for phrase in phrasebook:
        for name in phrase.fields:
            by_field.setdefault(name, []).append(phrase)
    out: dict[str, list[Item]] = {}
    tagged = 0
    for item in items:
        if item.tag in known:
            out.setdefault(str(item.tag), []).append(item)
            tagged += 1
            continue
        target = _by_span(item, placed) or _by_phrasebook(item, placed, by_field)
        out.setdefault(target or (KEPT_ID if item.carried else UNPLACED_ID), []).append(item)
    return out, tagged


def _by_span(item: Item, placed: Sequence[Placed]) -> str | None:
    if not item.span:
        return None
    return next((p.id for p in placed if locate(p.words, item.span) is not None), None)


def _by_phrasebook(
    item: Item, placed: Sequence[Placed], by_field: Mapping[str, Sequence[Phrase]]
) -> str | None:
    phrases = by_field.get(item.field or "", ())
    if not phrases:
        return None
    return next(
        (p.id for p in placed if any(phrase_matches(p.words, phrase) for phrase in phrases)), None
    )
