"""Which fields a sentence needs in the drafting prompt (docs/drafting/describe-it-plan.md, "Token
and latency budget"): the whole catalogue, field guide and phrasebook were ~110k tokens, so the
prompt carries a compact index of every field and, in detail, only a per-sentence slice. The
selection is deterministic code, no model: (a) the fields of every phrasebook phrase the sentence
says (always all of them), (b) a word match of the sentence against field names, guide intents and
descriptions (word boundaries, simple stemming, stop words, rarer words count more), (c) the
fields a selected field's guide caveats name, (d) a few core fields every screen touches. A
missed field must never turn into a false "missing", so the match is generous; the cap
(``MAX_FIELDS``) bounds only the non-phrasebook picks of (b) and (c). Pure: reads nothing,
calls no model."""

import math
import re
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.site.field_guide import FieldGuideSettings
from algotrade.config.site.llm import Phrase
from algotrade.services.read.instruments.catalogue import FeatureInfo

MAX_FIELDS = 25  # fields picked by words and cross references (phrasebook fields come on top)
FIRST_WORD_PICKS = 12  # word-match picks taken before cross references
MAX_CROSS_REFERENCES = 8  # fields added because a selected field's caveat names them
CORE_FIELDS = (
    "instrument.status",
    "instrument.security_type",
    "instrument.asset_class",
    "instrument.is_etf",
    "instrument.optionable",
    "instrument.sector",
    "instrument.exchange",
    "instrument.in_sp500",
    "rollup.price_stats@v2.close",
    "rollup.price_stats@v2.adv_usd_20d",
    "rollup.volume@v1.session_volume",
    "rollup.volume@v1.dollar_volume",
    "rollup.volume@v1.adv_shares_20d",
    "feature.market_cap",
)
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "over",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "under",
        "up",
        "with",
        "without",
        "who",
        "which",
        "what",
        "when",
        "where",
        "while",
        "show",
        "find",
        "give",
        "want",
        "need",
        "stocks",
        "stock",
        "names",
        "name",
        "only",
        "just",
        "all",
        "any",
        "some",
        "more",
        "most",
        "least",
        "less",
        "than",
        "about",
        "within",
        "around",
        "between",
        "each",
        "every",
        "get",
        "list",
        "screen",
        "trader",
    ]
)


_COMPARISON = frozenset(
    (
        "above", "below", "over", "under", "at", "than",
        "greater", "less", "least", "most", "between", "within",
    )
)  # fmt: skip
_WORD = re.compile(r"[a-z0-9]+")
_PIECE = re.compile(r"[a-z]+|\d+")
_UNIT = re.compile(r"(\d+)[\s-]*(day|days|d|week|weeks|w|session|sessions)\b")
_UNIT_LETTER = {"day": "d", "days": "d", "session": "d", "sessions": "d", "week": "w", "weeks": "w"}
_NAME_NOISE = frozenset({"rollup", "feature", "instrument"})
_VERSION = re.compile(r"^v\d+$")
FIELD_REF = re.compile(r"[a-z_]+\.[A-Za-z0-9_@.]*[A-Za-z0-9_]")


def stem(word: str) -> str:
    """A crude stem: plural, ``ing``, ``ed`` and ``ly`` endings off a word of 5+ letters."""
    for ending in ("ing", "ies", "ed", "es", "ly", "s"):
        if len(word) > len(ending) + 3 and word.endswith(ending):
            return word[: -len(ending)] + ("y" if ending == "ies" else "")
    return word


def words_of(text: str, vocab: Collection[str] = ()) -> list[str]:
    """Lower-case words of ``text``, letters and digits split apart (``SMA50`` -> sma, 50), a
    number with a day / week unit joined (``200 day`` -> ``200d``), and stemmed. A bare number is
    kept when it follows a word of ``vocab`` (field-name words: ``IV 30`` finds ``iv30``) that is
    not a comparison (``above 20`` names no field) and always after a unit."""
    lowered = text.lower()
    out: list[str] = []
    for m in _UNIT.finditer(lowered):
        unit = _UNIT_LETTER.get(m.group(2), m.group(2))
        out += [m.group(1) + unit, m.group(1)]
    lowered = _UNIT.sub(" ", lowered)
    previous = ""
    for piece in _PIECE.findall(lowered):
        if piece.isdigit():
            if stem(previous) in vocab and previous not in _COMPARISON:
                out.append(piece)
        else:
            out.append(stem(piece))
        previous = piece
    return out


def content_words(text: str, vocab: Collection[str] = ()) -> set[str]:
    """The words of ``text`` that can name a field (no stop words)."""
    return {w for w in words_of(text, vocab) if w not in STOP_WORDS}


def name_words(name: str) -> set[str]:
    """The words of a field name (``rollup.price_stats@v2.ret_20d`` -> price, stat, ret, 20d,
    20; ``sma_50`` -> sma, 50); the section word and the version are noise."""
    out: set[str] = set()
    for part in re.split(r"[.@_]+", name.lower()):
        if not part or part in _NAME_NOISE or _VERSION.match(part):
            continue
        for piece in _PIECE.findall(part):
            if len(piece) > 1 or piece.isdigit():
                out.add(piece if piece.isdigit() else stem(piece))
        digits = re.match(r"^(\d+)[dwmy]$", part)
        if digits:
            out.add(part)
    return out


def phrase_matches(sentence: str, phrase: Phrase) -> bool:
    """Whether the sentence says any of the phrase's words (a run of whole, stemmed words)."""
    have = [stem(w) for w in _WORD.findall(sentence.lower())]
    for say in phrase.say:
        want = [stem(w) for w in _WORD.findall(say.lower())]
        if want and any(have[i : i + len(want)] == want for i in range(len(have) - len(want) + 1)):
            return True
    return False


@dataclass(frozen=True)
class Slice:
    """What a sentence gets in detail: ``fields`` (sorted names, core fields included),
    ``brief`` (the fields among them that get no caveats: the weaker word matches and the
    core fields no word asked for), ``phrases`` (the matched phrasebook entries, file order)."""

    fields: tuple[str, ...]
    brief: frozenset[str]
    phrases: tuple[Phrase, ...]


def select_slice(
    sentence: str,
    infos: Sequence[FeatureInfo],
    phrasebook: Iterable[Phrase] = (),
    guide: FieldGuideSettings | None = None,
) -> Slice:
    """The slice of ``sentence`` over the catalogue ``infos``. Deterministic: the same inputs
    give the same slice whatever the order of ``infos``."""
    names = {i.name for i in infos}
    matched = tuple(p for p in phrasebook if phrase_matches(sentence, p))
    phrase_fields = {f for p in matched for f in p.fields if f in names}
    ranked = [n for n in _ranked(sentence, infos, guide) if n not in phrase_fields]
    full: dict[str, None] = dict.fromkeys(ranked[:FIRST_WORD_PICKS])
    crossed = _cross_references(sorted(phrase_fields | full.keys()), names, guide)
    full.update(dict.fromkeys(n for n in crossed if n not in phrase_fields))
    full = dict(list(full.items())[: FIRST_WORD_PICKS + MAX_CROSS_REFERENCES])
    tail = [n for n in ranked[FIRST_WORD_PICKS:] if n not in full]
    brief = tail[: max(0, MAX_FIELDS - len(full))]
    core = {n for n in CORE_FIELDS if n in names}
    keep = phrase_fields | full.keys()
    weak = frozenset((set(brief) | core) - keep)
    return Slice(tuple(sorted(keep | weak)), weak, matched)


def _ranked(
    sentence: str, infos: Sequence[FeatureInfo], guide: FieldGuideSettings | None
) -> list[str]:
    """Field names by how well the sentence's words match them, best first (ties by name):
    a word in the name counts double; a word in the description or a guide intent once; a word
    that is in few fields counts more."""
    infos = [i for i in infos if i.scope == "site"]  # the caller's own are always in full
    by_name = {i.name: i for i in infos}
    in_name = {n: name_words(n) for n in by_name}
    wanted = content_words(sentence, set().union(*in_name.values()))
    if not wanted:
        return []
    intents: Mapping[str, str] = {}
    if guide is not None:
        intents = {e.name: " ".join(u.intent for u in e.uses) for e in guide.fields}
    in_text = {
        n: content_words(f"{i.description} {intents.get(n, '')}") - in_name[n]
        for n, i in by_name.items()
    }
    df = Counter(w for n in by_name for w in in_name[n] | in_text[n])
    total = len(by_name)
    weight = {w: math.log(1 + total / df[w]) for w in df}
    scored = []
    for n in by_name:
        score = sum(2 * weight[w] for w in wanted & in_name[n]) + sum(
            weight[w] for w in wanted & in_text[n]
        )
        if score > 0:
            scored.append((-score, n))
    return [n for _, n in sorted(scored)]


def _cross_references(
    selected: Sequence[str], names: set[str], guide: FieldGuideSettings | None
) -> list[str]:
    """Catalogue fields that the guide caveats of ``selected`` fields name (one level, sorted)."""
    if guide is None:
        return []
    chosen = set(selected)
    found: set[str] = set()
    for entry in guide.fields:
        if entry.name in chosen:
            for text in entry.caveats:
                found.update(m for m in FIELD_REF.findall(text) if m in names)
    return sorted(found - chosen)
