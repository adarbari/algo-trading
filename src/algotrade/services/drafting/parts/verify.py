"""``doubts``: what a deterministic read of a draft's parts doubts about the model's work (ADR
0041, amended 2026-10-17). A draft the validator accepts can still have misread the sentence
(the 2026-10-17 judge: words split off a condition as "not understood", an "or" left out of the
words, a criterion tied to no words, "X or Y" drafted as two ANDed criteria). Each doubt is a
``kind`` (one of ``KINDS``), the part it is about and a message written to the model, so the
chain repairs once on the same member and then asks a stronger one; a draft the phrasebook made
never reaches this (it never asks a model). Pure: reads the draft's parts and the connectors'
vocabulary, calls nothing."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.services.drafting.parts.connectors import AND_NOT, OR, read
from algotrade.services.drafting.parts.model import Part

UNMAPPED_WORDS = "unmapped_words"
CONNECTOR_LEFT_OUT = "connector_left_out"
UNPLACED = "unplaced"
OR_NOT_FORMULA = "or_not_formula"
UNIVERSE_NOUNS = frozenset(
    {"stock", "stocks", "equity", "equities", "share", "shares", "etf", "etfs", "fund", "funds",
     "adr", "adrs"}
)  # fmt: skip  # a gap of only these is no doubt when the draft types the universe
KINDS = (UNMAPPED_WORDS, CONNECTOR_LEFT_OUT, UNPLACED, OR_NOT_FORMULA)

_TOKEN = re.compile("[\\w'\\u2019/.%+-]+")  # a field-ish token ("p/e", "52-week") stays whole


@dataclass(frozen=True)
class Doubt:
    """One doubt: its ``kind``, the part ``ref`` (an id) or words it is about, and the
    ``message`` that tells the model what to change."""

    kind: str
    ref: str
    message: str


def doubts(parts: Sequence[Part] | None, typed: bool = False) -> tuple[Doubt, ...]:
    """The doubts about a draft whose explained ``parts`` are given (none: no parts, no
    doubts). ``typed``: the draft has an ``instrument.security_type`` criterion, so a gap that is
    only a universe noun ("stocks") loses nothing; without one it stays a doubt."""
    found: list[Doubt] = []
    for part in parts or ():
        if part.origin == "unplaced":
            found.append(_unplaced(part))
        elif part.kind == "not_understood" and part.origin in ("gap", "words"):
            if part.origin == "gap" and (logic := _left_out(part)):
                found.append(_connector(part, logic))
            elif (words := content_words(part.words)) and not (
                typed and part.origin == "gap" and set(words) <= UNIVERSE_NOUNS
            ):
                found.append(_unmapped(part))
        elif _or_without_formula(part):
            found.append(_or_not_formula(part))
    return tuple(found)


def content_words(words: str) -> list[str]:
    """The words of ``words`` that are neither glue nor a connector."""
    tokens = [t.lower().strip(".'\u2019") for t in _TOKEN.findall(words)]
    tokens = [t for t in tokens if any(c.isalnum() for c in t)]
    return [t for t, (kind, _) in zip(tokens, read(tokens), strict=True) if kind == "content"]


def _or_without_formula(part: Part) -> bool:
    if part.origin != "words" or part.formulas or part.unresolved or len(part.criteria) < 2:
        return False
    tokens = [t.lower() for t in _TOKEN.findall(part.words)]
    return any(
        kind == "join" and logic == OR and token == "or"
        for token, (kind, logic) in zip(tokens, read(tokens), strict=True)
    )


def _unmapped(part: Part) -> Doubt:
    words = " ".join(content_words(part.words))
    return Doubt(
        UNMAPPED_WORDS, part.id,
        f"the words '{part.words}' are in no part of the draft (nothing maps '{words}'): map "
        "them (a criterion, a formula, a missing request or an unresolved term) or quote them "
        "in the part whose condition they belong to",
    )  # fmt: skip


def _left_out(part: Part) -> str | None:
    """The or / negation connector a gap carries as its join or begins with, else ``None``."""
    if part.join in (OR, AND_NOT):
        return part.join
    tokens = [t.lower() for t in _TOKEN.findall(part.words)][:3]
    kinds = read(tokens)
    return kinds[0][1] if kinds and kinds[0][0] == "join" and kinds[0][1] != "and" else None


def _connector(part: Part, logic: str) -> Doubt:
    keep = (
        "keep 'X or Y' as one part (one boolean formula)"
        if logic == OR
        else "keep the negation inside the words of the condition it negates"
    )
    return Doubt(
        CONNECTOR_LEFT_OUT, part.id,
        f"the connector in '{part.join_words or part.words}' was left out of the words of a part, "
        f"so '{part.words}' reads as not understood: {keep}",
    )  # fmt: skip


def _unplaced(part: Part) -> Doubt:
    refs = ", ".join((*part.criteria, *part.formulas, *part.missing, *part.unresolved))
    return Doubt(
        UNPLACED, part.id,
        f"{refs or 'an item'} is tied to no words: tag it with the part whose words ask for it, "
        "or drop it if the sentence does not ask for it",
    )  # fmt: skip


def _or_not_formula(part: Part) -> Doubt:
    return Doubt(
        OR_NOT_FORMULA, part.id,
        f"the words '{part.words}' say 'or' but are drafted as {len(part.criteria)} criteria, "
        "which a rule screen ANDs: 'or' needs one boolean formula",
    )  # fmt: skip


def kinds_of(found: Sequence[Doubt]) -> tuple[str, ...]:
    """The kinds of ``found`` in order, one per doubt (what a served draft records)."""
    return tuple(d.kind for d in found)
