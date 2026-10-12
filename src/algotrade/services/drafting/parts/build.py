"""``build_parts``: the explained parts of one draft (ADR 0041, amended 2026-10-11). The model's
``parts`` are located in the sentence (``spans``, in order; one that is not found, overlaps or is
malformed is dropped and its items go down the fallback), the words nobody covers become
``not_understood`` parts, every item is attributed (``attribute``), the kind of a part comes
from what it holds (never from the model): a term to choose ``needs_choice`` over a formula over
a missing request or a dropped criterion (``not_available``) over a plain criterion (``applied``),
nothing ``not_understood``; suggestions and the model's reading never change it. The reading is
kept only when its numbers are the part's (``consistency``); the stats leave out the criteria
kept from ``current`` (the model rightly tags them with nothing). Caps: ``MAX_PARTS`` parts with
words, ``MAX_WORDS`` characters of words, ``MAX_READING`` of reading. ``None`` when the model
gave no parts, or none could be located: the draft is then served as it was before parts."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.parts.attribute import Placed, attribute
from algotrade.services.drafting.parts.consistency import (
    reading_consistent,
    stated,
)
from algotrade.services.drafting.parts.model import (
    KEPT_ID,
    MAX_PARTS,
    MAX_READING,
    MAX_WORDS,
    UNPLACED_ID,
    Item,
    Part,
    PartsStats,
    is_part_id,
)
from algotrade.services.drafting.parts.spans import Span, gaps, locate, utf16

CHECKED = (
    "criteria",
    "dropped",
    "formulas",
    "unresolved",
    "missing",
    "rank",
)  # a reading's numbers


@dataclass(frozen=True)
class _Located:
    id: str
    span: Span
    reading: str | None


def build_parts(
    sentence: str, raw: Any, items: Sequence[Item], phrasebook: Sequence[Phrase]
) -> tuple[tuple[Part, ...], PartsStats] | None:
    """The parts of ``sentence`` for the model's ``raw`` parts and the draft's ``items``, with
    how they were made; ``None`` when there are none to serve."""
    located, considered = _located(sentence, raw)
    if not located:
        return None
    word_gaps = gaps(sentence, [p.span for p in located])
    while len(located) + len(word_gaps) > MAX_PARTS:  # the last part's words become a gap
        located = located[:-1]
        word_gaps = gaps(sentence, [p.span for p in located])
    placed = [Placed(p.id, sentence[p.span.start : p.span.end]) for p in located]
    assigned, tagged = attribute(items, placed, phrasebook)
    parts: list[tuple[int, Part]] = []
    kept = 0
    given = 0
    for p, where in zip(located, placed, strict=True):
        mine = assigned.get(p.id, [])
        part = _part(sentence, p.id, p.span, where.words, p.reading, mine, "words")
        given += bool(p.reading)
        kept += part.reading_source == "model"
        parts.append((p.span.start, part))
    for n, gap in enumerate(word_gaps, 1):
        words = sentence[gap.start : gap.end]
        parts.append((gap.start, _part(sentence, f"g{n}", gap, words, None, [], "gap")))
    ordered = [part for _, part in sorted(parts, key=lambda t: t[0])]
    for catch, origin in ((KEPT_ID, "kept"), (UNPLACED_ID, "unplaced")):
        if assigned.get(catch):
            ordered.append(_part(sentence, catch, None, "", None, assigned[catch], origin))
    held = sum(len(v) for k, v in assigned.items() if k not in (KEPT_ID, UNPLACED_ID))
    lost = sum(p.kind == "not_understood" for p in ordered)
    asked = len(items) - len(assigned.get(KEPT_ID, ()))  # a kept criterion has no words to tag
    stats = PartsStats(asked, tagged, held - tagged, considered, len(located), lost, given, kept)
    return tuple(ordered), stats


def _located(sentence: str, raw: Any) -> tuple[list[_Located], int]:
    """The model's parts found in the sentence in order, and how many were well formed."""
    found: list[_Located] = []
    considered = 0
    seen: set[str] = set()
    cursor = 0
    for item in (raw if isinstance(raw, list) else [])[:MAX_PARTS]:
        if not isinstance(item, Mapping):
            continue
        pid, words = item.get("id"), item.get("words")
        if not is_part_id(pid) or pid in seen or not isinstance(words, str) or not words.strip():
            continue
        seen.add(pid)
        considered += 1
        span = locate(sentence, words, cursor)
        if span is None or span.end - span.start > MAX_WORDS:
            continue
        cursor = span.end
        reading = item.get("reading")
        found.append(_Located(pid, span, reading if isinstance(reading, str) else None))
    return found, considered


def _part(
    sentence: str,
    pid: str,
    span: Span | None,
    words: str,
    reading: str | None,
    mine: Sequence[Item],
    origin: str,
) -> Part:
    refs: dict[str, list[str]] = {}
    for item in mine:
        refs.setdefault(item.group, []).append(item.ref)
    kind = _kind(refs)
    text, source = _reading(reading, mine, words, kind)
    start, end = (utf16(sentence, span.start), utf16(sentence, span.end)) if span else (0, 0)
    return Part(
        pid, words, start, end, text, source, kind, origin,
        tuple(refs.get("criteria", ())), tuple(refs.get("dropped", ())),
        tuple(refs.get("formulas", ())), tuple(refs.get("unresolved", ())),
        tuple(refs.get("missing", ())), tuple(refs.get("suggestions", ())), "rank" in refs,
    )  # fmt: skip


def _kind(refs: Mapping[str, list[str]]) -> str:
    if refs.get("unresolved"):
        return "needs_choice"
    if refs.get("formulas"):
        return "formula"
    if refs.get("missing") or refs.get("dropped"):
        return "not_available"
    if refs.get("criteria") or refs.get("rank"):
        return "applied"
    return "not_understood"  # suggestions alone do not make a part understood


def _reading(
    reading: str | None, mine: Sequence[Item], words: str, kind: str
) -> tuple[str | None, str]:
    """The reading kept (clipped) and its source: the model's when it has refs to hold it to and
    states no number they lack, else ``None`` from the server."""
    text = " ".join(reading.split())[:MAX_READING].rstrip() if reading else ""
    if not text or kind == "not_understood":
        return None, "server"
    allowed = [n for item in mine if item.group in CHECKED for n in item.numbers]
    if not any(item.group in ("criteria", "formulas", "unresolved") for item in mine):
        allowed += stated(words)  # a part with no rows of its own may repeat its words' numbers
    return (text, "model") if reading_consistent(text, allowed) else (None, "server")
