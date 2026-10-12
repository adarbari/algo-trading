"""``algotrade-api golden candidates``: the golden-set candidates an owner may curate, picked from
the chains of ``chains.golden_candidates`` with the sampling hygiene of docs/drafting/
describe-it-plan.md ("Learning from iteration"): newest first, near-duplicate sentences removed,
at most ``per_user_month`` per user and month, then taken round-robin by feature group so a heavy
user or a common screen does not dominate; each card carries a coverage count by feature group and
by operator (the intent a criterion expresses) and flags sentences that look like holdings.

The cards hold REAL trader sentences: they are printed only to the owner's terminal and never
written to the repo (the public-repo rule, ADR 0066; ``curate`` takes the owner's paraphrases).
Pure: rows in, cards out; the caller loads the rows through the viewer-filtered
``load_drafting_events``, as the admin."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from algotrade.services.feedback.chains import golden_candidates

DEFAULT_PER_USER_MONTH = 5
DEFAULT_LIMIT = 20
GRAM = 5  # words of a run that may not be shared with a real sentence
NEAR_DUPLICATE = 0.8  # token overlap (``overlap``) at or above which two sentences are one
SCOPE_PREFIXES = ("instrument.status", "instrument.security_type")  # scaffolding, not coverage
UNKNOWN_GROUP = "(unreadable criteria)"

# Upper-case words that are indicators or jargon, not a ticker.
JARGON_WORDS = (
    "RSI SMA EMA MACD ATR ADV IV DTE ETF ETFS PE EPS ROE ROA FCF PEG OTM ITM ATM VWAP AND OR "
    "NOT USD US YTD TTM EV EBITDA IPO SEC NYSE NASDAQ SP ADX OBV"
)
JARGON = frozenset(JARGON_WORDS.split())
_SHARES_OF = re.compile(r"\b\d[\d,.]*\s*(?:shares?|sh|contracts?|lots?)\b", re.IGNORECASE)
_TICKER_NUMBER = re.compile(r"\b[A-Z]{1,5}\s+\$?\d[\d,.]*\b")
_CASHTAG = re.compile(r"\$[A-Za-z]{1,5}\b")
_CAPS = re.compile(r"\b[A-Z]{2,5}\b")


def tokens(text: str) -> frozenset[str]:
    """The lower-case alphanumeric words of ``text``."""
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def normalised(text: str) -> str:
    """``text`` as its words in order, one space apart: what a verbatim copy compares equal on."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def overlap(a: str, b: str) -> float:
    """Shared words over the words of the longer sentence (0 when either has none): 1.0 when the
    two have the same words, however cased or punctuated; a short sentence inside a long one
    scores low (the 5-word runs of ``grams`` catch a partial copy)."""
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def grams(text: str, size: int = GRAM) -> set[tuple[str, ...]]:
    """The runs of ``size`` consecutive words of ``text`` (the anti-leak rule of the golden set)."""
    words = normalised(text).split()
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def feature_group(field: str) -> str:
    """The feature group a catalogue field belongs to: ``rollup.<group>@vN`` for a rollup column,
    else its first segment (``feature``, ``instrument``)."""
    parts = field.split(".")
    return ".".join(parts[:2]) if parts[0] == "rollup" and len(parts) > 2 else parts[0]


def holding_flags(sentence: str) -> list[str]:
    """Why ``sentence`` may name a position: share counts, ``$CASHTAG``s, a ticker with a
    number, or an upper-case word that is not market jargon. Advisory: the owner decides."""
    flags = [m.group(0) for m in _SHARES_OF.finditer(sentence)]
    flags += [m.group(0) for m in _CASHTAG.finditer(sentence)]
    for m in _TICKER_NUMBER.finditer(sentence):
        if m.group(0).split()[0] not in JARGON:
            flags.append(m.group(0))
    flags += [w for w in _CAPS.findall(sentence) if w not in JARGON]
    return sorted(set(flags))


def criteria_table(snapshot: Any) -> Mapping[str, Any]:
    """The ``criteria`` table of a stored snapshot; empty when it is missing or was truncated."""
    table = snapshot.get("criteria") if isinstance(snapshot, Mapping) else None
    return table if isinstance(table, Mapping) else {}


def _fields_ops(snapshot: Any) -> list[tuple[str, str]]:
    return [
        (str(c.get("field", "")), str(c.get("op", "")))
        for c in criteria_table(snapshot).values()
        if isinstance(c, Mapping)
    ]


def _when(case: Mapping[str, Any]) -> datetime:
    latest: datetime = max(s["ts"] for s in case["sentences"])
    return latest


def _card(case: Mapping[str, Any]) -> dict[str, Any]:
    pairs = [
        (f, o) for f, o in _fields_ops(case["final_criteria"]) if not f.startswith(SCOPE_PREFIXES)
    ]
    groups = sorted({feature_group(f) for f, _ in pairs}) or [UNKNOWN_GROUP]
    sentences = [s["sentence"] or "" for s in case["sentences"]]
    return {
        "chain_id": case["source_event"],
        "session_id": case["chain_id"],
        "source_events": case["source_events"],
        "user": case["user"],
        "date": _when(case).date().isoformat(),
        "when": _when(case).isoformat(),
        "sentences": sentences,
        "criteria_in_force": [s["current_criteria"] for s in case["sentences"]],
        "final_criteria": case["final_criteria"],
        "groups": groups,
        "intents": sorted({o for _, o in pairs if o}),
        "holding_flags": sorted({f for s in sentences for f in holding_flags(s)}),
    }


def _usable(case: Mapping[str, Any]) -> bool:
    return bool(case["sentences"]) and bool(criteria_table(case["final_criteria"]))


def _distinct(cards: Iterable[dict[str, Any]], similarity: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for card in cards:
        text = " ".join(card["sentences"])
        if all(overlap(text, " ".join(k["sentences"])) < similarity for k in kept):
            kept.append(card)
    return kept


def _capped(cards: Iterable[dict[str, Any]], per_user_month: int) -> list[dict[str, Any]]:
    seen: Counter[tuple[str, str]] = Counter()
    out = []
    for card in cards:
        key = (card["user"], card["date"][:7])
        if seen[key] < per_user_month:
            seen[key] += 1
            out.append(card)
    return out


def _round_robin(cards: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """One card of each primary feature group in turn, so no group fills the list first. A card's
    primary group is the RAREST of its groups in this pool (ties by name), so a card that touches
    a rare group is not filed under a common one."""
    pool = Counter(g for card in cards for g in card["groups"])
    buckets: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        primary = min(card["groups"], key=lambda g: (pool[g], g))
        buckets.setdefault(primary, []).append(card)
    out: list[dict[str, Any]] = []
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                out.append(bucket.pop(0))
    return out


def candidate_cards(
    rows: Iterable[Mapping[str, Any]],
    user: str | None = None,
    per_user_month: int = DEFAULT_PER_USER_MONTH,
    limit: int = DEFAULT_LIMIT,
    similarity: float = NEAR_DUPLICATE,
    truncated: bool = False,
) -> list[dict[str, Any]]:
    """The cards of ``rows`` (viewer-filtered drafting events) worth curating: finalised chains
    with a sentence and readable final criteria, of ``user`` when given, newest first, then
    de-duplicated, capped per user and month, stratified by feature group, at most ``limit``.
    ``truncated``: the rows hit a read cap (``chains.golden_candidates``)."""
    cases = [
        c for c in golden_candidates(rows, truncated) if _usable(c) and user in (None, c["user"])
    ]
    cards = sorted(
        (_card(c) for c in cases), key=lambda c: (c["when"], c["chain_id"]), reverse=True
    )
    return _round_robin(_capped(_distinct(cards, similarity), per_user_month))[: max(0, limit)]


def coverage(cards: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """How many cards touch each feature group and each operator (intent)."""
    groups: Counter[str] = Counter()
    intents: Counter[str] = Counter()
    for card in cards:
        groups.update(card["groups"])
        intents.update(card["intents"])
    return {"groups": dict(sorted(groups.items())), "intents": dict(sorted(intents.items()))}


def render(
    cards: Sequence[Mapping[str, Any]], summary: Mapping[str, Mapping[str, int]]
) -> list[str]:
    """The cards as terminal lines (real sentences: the owner's terminal only)."""
    lines = [f"{len(cards)} candidate(s); real sentences below: do not copy them into the repo"]
    for card in cards:
        lines += [
            "",
            f"chain {card['chain_id']}  user {card['user']}  {card['date']}  "
            f"{len(card['sentences'])} sentence(s)",
        ]
        for n, (sentence, force) in enumerate(
            zip(card["sentences"], card["criteria_in_force"], strict=True), 1
        ):
            lines += [f"  {n}. {sentence}", f"     in force: {brief(force)}"]
        lines.append(f"  final criteria: {brief(card['final_criteria'])}")
        if card["holding_flags"]:
            lines.append(f"  WARNING looks like holdings: {', '.join(card['holding_flags'])}")
    lines += ["", "coverage by feature group: " + _counts(summary["groups"])]
    lines.append("coverage by intent (operator): " + _counts(summary["intents"]))
    return lines


def _counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "-"


def brief(snapshot: Any) -> str:
    """A criteria snapshot as ``field op value`` lines joined by ``;`` (``-`` when none)."""
    return (
        "; ".join(
            f"{c.get('field')} {c.get('op')} {c.get('value')}"
            for c in criteria_table(snapshot).values()
            if isinstance(c, Mapping)
        )
        or "-"
    )
