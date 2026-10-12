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
Not wired into ``draft_screen`` yet."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.llm import Phrase
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
    start: int
    end: int
    order: int
    phrase: Phrase


def _cover(tokens: list[str], phrasebook: Sequence[Phrase]) -> tuple[list[bool], list[Phrase]]:
    """Which tokens structured wordings claim (longest first, then file order, no overlap) and
    the entries that claimed them, in file order."""
    claims: list[_Claim] = []
    for order, phrase in enumerate(phrasebook):
        for say in phrase.say if is_structured(phrase) else ():
            want = [stem(w) for w in _WORD.findall(say.lower())]
            for i in range(len(tokens) - len(want) + 1):
                if want and tokens[i : i + len(want)] == want:
                    claims.append(_Claim(i, i + len(want), order, phrase))
    taken = [False] * len(tokens)
    chosen: dict[int, Phrase] = {}
    for c in sorted(claims, key=lambda c: (-(c.end - c.start), c.order, c.start)):
        if not any(taken[c.start : c.end]):
            taken[c.start : c.end] = [True] * (c.end - c.start)
            chosen[c.order] = c.phrase
    return taken, [chosen[o] for o in sorted(chosen)]


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


def resolves_fully(
    sentence: str, phrasebook: Sequence[Phrase]
) -> tuple[dict[str, Any], ...] | None:
    """The criteria (answer shape, ``PhraseCriterion.as_answer``) of the sentence when
    structured entries with exact thresholds cover every content word of it, else ``None``."""
    tokens = [stem(w) for w in _WORD.findall(sentence.lower())]
    taken, chosen = _cover(tokens, phrasebook)
    gap = any(not t and w not in FILLER for t, w in zip(taken, tokens, strict=True))
    if not chosen or gap or any(p.alternatives for p in chosen):  # alternatives: ask
        return None
    return _merged(chosen)
