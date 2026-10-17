"""Match a sentence to the phrasebook's structured entries and, when they cover all of it, say
what it means without the model. ``structured_matches`` returns every structured entry the
sentence says (``retrieval.phrase_matches``); ``resolves_fully`` returns the criteria only when
the structured entries claim every content word of the sentence (a number, an unknown word or a
free-text entry's word leaves a gap), no matched entry is ambiguous (alternatives) and no two
criteria disagree (the same field read twice, or two that can never both hold:
``consistency.compatible``); else ``None`` and the model answers. A word that flips or splits a
meaning (negation, a comparative, "or") is never filler: it is a gap unless a structured wording
covers that very word, so "uptrend stocks without earnings this week" goes to the model.
Longest wording first, so "breaking out to highs" is not also "breaking out".
``resolve`` also says where each entry's wording is in the sentence (``Claimed``), for the
shortcut ``draft_screen`` takes when the phrasebook resolves a sentence (``shortcut.py``).
``resolve_clauses`` is the same for a sentence with a "but" or "while" between conditions
(ADR 0041, amended 2026-10-17): split at the and-type connectors (``clauses.py``), each clause
resolved fully on its own, one claim (one part) per clause."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.phrasebook.clauses import split
from algotrade.services.drafting.phrasebook.consistency import compatible
from algotrade.services.drafting.retrieval import STOP_WORDS, phrase_matches, stem

_WORD = re.compile(r"[a-z0-9]+")
# Words that change what a sentence asks: retrieval skips them as filler, resolving must not.
MEANING_WORDS = frozenset(
    [
        *("without", "no", "not", "never", "except", "excluding", "exclude", "non", "but", "nor"),
        *("less", "more", "least", "most", "fewer", "higher", "lower", "than", "or", "over"),
        *(
            "under",
            "above",
            "below",
            "neither",
            "either",
            "versus",
            "vs",
            "then",
            "after",
            "before",
            "followed",
            "by",
        ),
        *("from", "to", "about", "around", "within", "between"),  # ranges and approximations
    ]
)
_MEANING = frozenset(stem(w) for w in MEANING_WORDS) | MEANING_WORDS
FILLER = frozenset(w for w in STOP_WORDS if w not in _MEANING)


def is_structured(phrase: Phrase) -> bool:
    return bool(phrase.criteria or phrase.alternatives)


def structured_matches(sentence: str, phrasebook: Sequence[Phrase]) -> tuple[Phrase, ...]:
    """The structured entries ``sentence`` says, in file order."""
    return tuple(p for p in phrasebook if is_structured(p) and phrase_matches(sentence, p))


@dataclass(frozen=True)
class _Claim:
    start: int  # token indices
    end: int
    order: int
    phrase: Phrase


@dataclass(frozen=True)
class Claimed:
    """One entry's wording as the sentence says it: ``start`` / ``end`` are code-point offsets
    into the sentence (the slice is the trader's own words)."""

    phrase: Phrase
    start: int
    end: int
    criteria: tuple[dict[str, Any], ...] | None = None  # a clause's, when it holds several entries

    def answers(self) -> list[dict[str, Any]]:
        """What this claim says, in answer shape: its clause's criteria, else its entry's."""
        if self.criteria is not None:
            return [dict(c) for c in self.criteria]
        return [c.as_answer() for c in self.phrase.criteria]


@dataclass(frozen=True)
class Resolution:
    """What structured entries make of a whole sentence: the ``criteria`` (file order, answer
    shape) and the ``claims`` behind them in sentence order."""

    criteria: tuple[dict[str, Any], ...]
    claims: tuple[Claimed, ...]


def _cover(tokens: list[str], phrasebook: Sequence[Phrase]) -> tuple[list[bool], list[_Claim]]:
    """Which tokens structured wordings claim (longest first, then file order, no overlap) and
    the claims that took them, in token order."""
    claims: list[_Claim] = []
    for order, phrase in enumerate(phrasebook):
        for say in phrase.say if is_structured(phrase) else ():
            want = [stem(w) for w in _WORD.findall(say.lower())]
            for i in range(len(tokens) - len(want) + 1):
                if want and tokens[i : i + len(want)] == want:
                    claims.append(_Claim(i, i + len(want), order, phrase))
    taken = [False] * len(tokens)
    chosen: list[_Claim] = []
    for c in sorted(claims, key=lambda c: (-(c.end - c.start), c.order, c.start)):
        if not any(taken[c.start : c.end]):
            taken[c.start : c.end] = [True] * (c.end - c.start)
            chosen.append(c)
    return taken, sorted(chosen, key=lambda c: c.start)


def _merged(phrases: Sequence[Phrase]) -> tuple[dict[str, Any], ...] | None:
    """The entries' criteria once each, ``None`` when two read one field and op differently or
    no value can satisfy them all."""
    out: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for phrase in phrases:
        for criterion in phrase.criteria:
            answer = criterion.as_answer()
            key = (criterion.field, criterion.op)
            if key not in seen:
                seen[key] = answer
                out.append(answer)
            elif seen[key] != answer:
                return None
    return tuple(out) if compatible(out) else None


def _resolution(sentence: str, phrasebook: Sequence[Phrase]) -> Resolution | None:
    lowered = sentence.lower()
    found = list(_WORD.finditer(lowered))
    tokens = [stem(m.group()) for m in found]
    taken, accepted = _cover(tokens, phrasebook)
    gap = any(not t and w not in FILLER for t, w in zip(taken, tokens, strict=True))
    by_order = {c.order: c.phrase for c in accepted}
    chosen = [by_order[o] for o in sorted(by_order)]  # each entry once, file order
    if not chosen or gap or any(p.alternatives for p in chosen):  # alternatives: ask
        return None
    merged = _merged(chosen)
    if merged is None:
        return None
    claims = tuple(
        Claimed(c.phrase, found[c.start].start(), found[c.end - 1].end()) for c in accepted
    )
    return Resolution(merged, claims)


def resolves_fully(
    sentence: str, phrasebook: Sequence[Phrase]
) -> tuple[dict[str, Any], ...] | None:
    """The criteria (answer shape, ``PhraseCriterion.as_answer``) of the sentence when
    structured entries with exact thresholds cover every content word of it, else ``None``."""
    resolution = _resolution(sentence, phrasebook)
    return None if resolution is None else resolution.criteria


def resolve(sentence: str, phrasebook: Sequence[Phrase]) -> Resolution | None:
    """``resolves_fully`` with where each entry's wording is in ``sentence``; ``None`` also for a
    sentence whose lower-casing changes its length (offsets would not point at its own words)."""
    if len(sentence.lower()) != len(sentence):
        return None
    return _resolution(sentence, phrasebook)


def resolve_clauses(sentence: str, phrasebook: Sequence[Phrase]) -> Resolution | None:
    """The sentence resolved clause by clause (ADR 0041, amended 2026-10-17): split at the
    and-type connectors (``clauses.split``), every clause resolved fully on its own, the
    criteria of the clauses never on one field twice and all able to hold together; one claim
    per clause (its words run from its first entry's wording to its last), the connectors
    between them left to the parts as joins. ``None`` for a sentence that is one clause (``resolve``
    has it), a clause the entries do not resolve, or clauses that share a field."""
    if len(sentence.lower()) != len(sentence):
        return None
    found = list(_WORD.finditer(sentence.lower()))
    taken, _ = _cover([stem(m.group()) for m in found], phrasebook)
    ranges = split(found, taken)
    if len(ranges) < 2:
        return None
    claims: list[Claimed] = []
    criteria: list[dict[str, Any]] = []
    for first, last in ranges:
        begin, finish = found[first].start(), found[last - 1].end()
        clause = _resolution(sentence[begin:finish], phrasebook)
        if clause is None:
            return None
        if {c["field"] for c in clause.criteria} & {c["field"] for c in criteria}:
            return None  # the same field in two clauses: two readings of one thing
        criteria += clause.criteria
        claims.append(
            Claimed(
                clause.claims[0].phrase,
                begin + clause.claims[0].start,
                begin + clause.claims[-1].end,
                clause.criteria,
            )
        )
    return Resolution(tuple(criteria), tuple(claims)) if compatible(criteria) else None
