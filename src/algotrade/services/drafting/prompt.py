"""The prompt a screener draft is asked with (ADR 0041): the task, the rule-screen grammar
(``docs/screeners/rules.md``), two worked examples, the caller's field catalogue in catalogue
order (name, type, unit, description, the values of a category), the site phrasebook (trader
vocabulary -> fields, ``config/site/phrasebook.toml``; a phrase keeps only the fields this
catalogue has), the site field guide (``config/site/field_guide/<group>/*.toml``: how to read a
field, the usual criterion per intent, the caveats, and the situations that fool several thresholds;
only entries over this catalogue's fields, sources left out) and the sentence. Rendered with no
timestamps or ids, so the same catalogue, phrasebook and guide give the same bytes (a provider's
prompt cache hits and a recorded test stays valid). The prompt carries no market data, results
or credentials.

The draft sends ``sliced_system_prompt`` (``PROMPT_VERSION`` 10: the A / B / C answer contract,
the explained parts, the open backlog keys most relevant to the sentence, the index grouped by
prefix): the task, the
examples and an index of every field (grouped under one heading per prefix: type, unit) as a prefix
no sentence changes, then in detail only the fields ``retrieval.select_slice`` picks for the
sentence, capped by a token budget (``PROMPT_BUDGET_TOKENS``: text added to the prompt shrinks the
slice, never the margin to the 15k cap; was ~110k for the whole catalogue, phrasebook and guide),
then the caller's own features."""

import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from algotrade.config.site.drafting.backlog import PROMPT_LIMIT
from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.parts.connectors import NEGATIONS, exclusion_text, join_text
from algotrade.services.drafting.retrieval import FIELD_REF, Slice, select_slice
from algotrade.services.read.instruments.catalogue import FeatureInfo

# Bump with any change to the prompt: the usage log records it (ADR 0058). 2: index + slice;
# 3: formulas, missing and unresolved in the answer, and the open backlog keys; 4: a phrasebook
# entry shows its structured thresholds; 5: the index grouped by prefix and the slice capped by a
# token budget; 6: the phrasebook's last column is headed "exact default"; 7: protective checks
# are ``suggestions``, never criteria, and no threshold is invented for a vague word; 8: explained
# parts (``parts`` and a ``part`` tag on every item, ``services/drafting/parts``); 9: the scoped ask
# of a part's re-draft (``redraft/prompt.py``). One version serves both prompts (the usage log
# records it for ``screener-draft`` and ``screener-draft-part``): bump it on any change to ``TASK``
# or to the scoped ``ASK`` (``redraft/test_prompt.py`` in the tests pins their hashes).
# 10: connectors are rendered from ``parts/connectors.py`` (only the and-type ones are left out of
# words; a negation or an or stays in the condition); one condition one contiguous part.
# 11: "all but" / "anything but" / "everything but" are except joins.
# 12: an "or" and an exclusion are left out of the words between two parts and the server groups
# the parts (ADR 0071); only maths over fields stays one boolean formula.
# 13: a side of an "or" that needs maths makes the whole "or" ONE part with ONE boolean formula.
# 14: missing data never passes, an exclusion included.
PROMPT_VERSION = "14"
PROMPT_BUDGET_TOKENS = 13_000  # chars / 4; the hard cap is 15k, the rest is margin for new text
SECTION_TOKENS = 120  # headers between the sections, counted before the slice is planned

log = logging.getLogger(__name__)

TASK = """\
You turn a trader's sentence into the criteria of a rule screen over a catalogue of stored
fields. Answer with ONE JSON object and nothing else (no prose, no code fence).

A rule screen is a list of criteria; an instrument is picked when every criterion holds. "Or" and
"except" are not criteria: each side is its own criterion in its own part and the server groups
them (see "parts").
Each criterion is an object with:
- "id": a short unique slug (a-z, 0-9, _), e.g. "price", "iv_rank"
- "field": exactly one field name from the catalogue below, spelled exactly
- "op": one of eq, ne, in, not_in, gt, gte, lt, lte, between, is_null, not_null
- "value": a number, a string, true/false, a list of values for in / not_in, a list of two
  numbers for between; omitted for is_null / not_null. A category field takes one of its
  listed values.
- "mode": "hard" (a miss rejects), "soft" (a near miss within "tolerance" is kept as a
  WATCH), or "score" (never rejects; a miss only lowers the rank)
- "tolerance": for soft and score only: a number in the field's unit, or {"relative": 0.2}
  for 20% of the threshold; omit for hard
- "on_miss": for soft only: "WATCH" (default), "LIQUIDITY_RISK" or "EVENT_RISK"
- "why": the words of the sentence this criterion comes from
- "part": the id of its part (see "parts"); null only when kept from the current criteria

Rules:
- Use only catalogue fields. Never invent a field: when the sentence asks for something the
  catalogue does not have, leave it out and say so in "notes". The field index lists every
  field you may use; some are then described in detail. A field with no detail is still valid:
  pick it by its name when it is what the sentence asks for.
- Percentages become fractions for a field whose unit is a fraction (50% -> 0.5); a field
  whose unit is percent takes 50. Dollar amounts are plain numbers (50M -> 50000000).
- "stocks" means instrument.security_type in ["COMMON_STOCK", "ADR"]; "ETFs" means ["ETF"];
  "optionable" means instrument.optionable eq true. Always include instrument.status eq
  "ACTIVE" (id "active") unless the sentence says otherwise.
- Gates (price, liquidity, kind of instrument) are hard. A threshold where a near miss is
  worth seeing is soft with a tolerance. "prefer" / "ideally" is score.
- "rank by X" / "sort by X" sets "tie_break" (descending unless the sentence says lowest
  first); otherwise "tie_break" is null.
- When current criteria are given, keep every one the sentence does not change and answer
  with the complete new list.
- The phrasebook and field guide (when given) say which fields a trader's words mean, how to
  read a field, the usual criterion per intent (op, value, mode, tolerance) and when the reading
  lies. Take thresholds from them, never from memory (say in "notes" when you had to choose one).
  A phrasebook entry's last column, "exact default" (`field op value`), is the meaning to use as
  given unless the sentence gives its own value;
  for a word with several readings it lists them and the first is the default.
- Missing data never passes: a name with no value for a field fails a hard criterion, an
  exclusion ("except ...") included, so it is left out. Write no note about names with no value.
- "criteria" holds ONLY what the sentence asks for; a caveat's check goes in "suggestions" (soft
  or score). A vague word ("heavy") with no phrasebook or guide threshold stays out of "criteria":
  offer "unresolved" readings when fields fit, else a note.

Answer shape:
{"criteria": [ ... ], "tie_break": {"field": "...", "descending": true, "part": "p3"} or null,
 "notes": ["anything you could not map, or assumed"],
 "formulas": [ ... ] or null, "missing": [ ... ] or null, "unresolved": [ ... ] or null,
 "suggestions": [ ... ] or null, "parts": [ ... ]}

"parts": the sentence split in order, 1 to 12 parts, one per thing the trader asks for:
{"id": "p1", "words": their own words, copied exactly, "reading": one short line (160 characters at
most), what we read this as, with only numbers its criteria hold (10% is 0.1)}. No overlaps. A part
is one condition and its words are contiguous: when the instrument word sits inside a condition
("cheap stocks on P/E"), the whole phrase is one part. Leave out of the words only the
connector that joins a part to the previous one (@@JOINS@@: the server reads it), an "or" between
two parts (@@ORS@@) and an exclusion between two parts (@@EXCLUDES@@), and filler such as "show
me" or "I'm looking for". Each side of an "or" is its own part with its own criterion, never one
boolean formula: "RSI under 30 or near the 52-week low" is p1 "RSI under 30" and p2 "near the
52-week low", the "or" left out. An excluded condition is its own part, drafted as it reads (never
negated): "except penny stocks" is the criterion for a penny stock in a part whose words leave
"except" out, and the server turns it into "none of". Words of preference ("ideally",
"preferably") stay in the words of their part, whose criterion is score. A negation that belongs
to one condition (@@NEGATIONS@@: "not overbought", "no earnings this week") stays in its words, with
its criterion negated. A formula cannot be one side of an "or" (the server cannot group it): when
maths over fields is needed on ANY side, the whole "or" is ONE part, its words covering both sides
("the 20 day return beats the 60 day return or RSI14 under 30"), with ONE boolean formula holding
both sides ("a > b or rsi < 30") and no other criterion for them. Words you cannot map
are still a part, with no item. Every criterion, formula, missing, unresolved, suggestion and the
tie_break carries "part"; scaffolding (status ACTIVE) goes with the part naming the kind of
instrument.

Each part of the sentence goes in one place. A: a criterion on a catalogue field (preferred). B: a
formula, only when maths over fields says it and no field does. C: missing, when neither can. Never
guess a field to fill a gap. Never add a criterion the sentence does not ask for to define a vague
word; offer unresolved readings.

"formulas": [{"name": "draft_<slug>", "expr", "dtype": "float|bool|str|date", "unit", "description",
"null_meaning", "inputs": [the names expr reads], "criterion": {"op", "value", "mode",
"tolerance"} or null, "part"}]. A formula is maths on one session's values:
"rollup.<group>@vN.<column>" is written <group>.<column>, "feature.<name>" is written <name> (no
instrument.* fields); + - * /
comparisons and or not; if(c, a, b) abs min max log sqrt ncdf clip(x, lo, hi) coalesce is_null
one_of(x, a, ...) exists(group). No lag, window, rolling or history: anything over time is
"missing" with ROLLUP_FROM_STORED. A formula equal to a catalogue field is dropped: use the field.

"missing": [{"key": an open key from "Open requests" below, else null, "new_key_slug" (a-z0-9_) when
key is null, "span", "description", "why_needed", "closest": [catalogue fields], "feasibility":
"ROLLUP_FROM_STORED" (a window over stored data) | "NEEDS_SOURCE" (new data) | "UNCLEAR", "part"}].

"suggestions": [{"field", "op", "value", "mode": "soft"|"score", "tolerance" (soft needs it),
"on_miss", "why": the caveat, "source": field or null, "part": the part whose words raised it}], at
most 5, shown to the trader to accept.

"unresolved": [{"term", "span", "default_index", "part", "alternatives": [{"label", "criterion": a
complete criterion}, 2 or 3]}] for a term with several readings ("liquid"); the server adds the
default to the criteria, so do not list it there. Not for a term the phrasebook or field guide
settles.
"""

TASK = (
    TASK.replace("@@JOINS@@", join_text())
    .replace("@@ORS@@", join_text("or"))
    .replace("@@EXCLUDES@@", exclusion_text())
    .replace("@@NEGATIONS@@", ", ".join(NEGATIONS))
)

# Two worked examples (sentence -> answer), rendered into the task so a smaller model sees the
# shape and the judgement expected. Their fields exist in the site catalogue (a test checks).
EXAMPLES: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "stocks with upward momentum that are close to their 52-week low",
        {
            "criteria": [
                {
                    "id": "active",
                    "part": "p1",
                    "field": "instrument.status",
                    "op": "eq",
                    "value": "ACTIVE",
                    "why": "listed",
                },
                {
                    "id": "stocks",
                    "part": "p1",
                    "field": "instrument.security_type",
                    "op": "in",
                    "value": ["COMMON_STOCK", "ADR"],
                    "why": "stocks",
                },
                {
                    "id": "near_low",
                    "part": "p3",
                    "field": "feature.pct_from_low_52w",
                    "op": "lte",
                    "value": 0.10,
                    "mode": "soft",
                    "tolerance": 0.05,
                    "why": "close to their 52-week low",
                },
                {
                    "id": "momentum",
                    "part": "p2",
                    "field": "rollup.price_stats@v2.ret_20d",
                    "op": "gt",
                    "value": 0,
                    "why": "upward momentum",
                },
                {
                    "id": "rsi",
                    "part": "p2",
                    "field": "rollup.momentum@v1.rsi_14",
                    "op": "gte",
                    "value": 50,
                    "mode": "score",
                    "tolerance": 20,
                    "why": "upward momentum",
                },
            ],
            "tie_break": {
                "field": "rollup.price_stats@v2.ret_20d",
                "descending": True,
                "part": "p2",
            },
            "notes": ["momentum read as a positive 20-day return; RSI only scores"],
            "parts": [
                {"id": "p1", "words": "stocks", "reading": "Active stocks and ADRs"},
                {
                    "id": "p2",
                    "words": "upward momentum",
                    "reading": "A positive 20-day return; RSI 14 at 50 or more only scores",
                },
                {
                    "id": "p3",
                    "words": "close to their 52-week low",
                    "reading": "Within 10% of the 52-week low, a near miss of 5% still shown",
                },
            ],
        },
    ),
    (
        "liquid stocks with IV rank above 50% and no earnings in the next 10 sessions, "
        "rank by IV rank",
        {
            "criteria": [
                {
                    "id": "active",
                    "part": "p1",
                    "field": "instrument.status",
                    "op": "eq",
                    "value": "ACTIVE",
                },
                {
                    "id": "stocks",
                    "part": "p1",
                    "field": "instrument.security_type",
                    "op": "in",
                    "value": ["COMMON_STOCK", "ADR"],
                },
                {
                    "id": "liquid",
                    "part": "p1",
                    "field": "rollup.price_stats@v2.adv_usd_20d",
                    "op": "gte",
                    "value": 50000000,
                    "mode": "soft",
                    "tolerance": {"relative": 0.2},
                    "on_miss": "LIQUIDITY_RISK",
                    "why": "liquid",
                },
                {
                    "id": "iv_rank",
                    "part": "p2",
                    "field": "feature.iv_rank",
                    "op": "gte",
                    "value": 0.5,
                    "mode": "soft",
                    "tolerance": 0.1,
                },
                {
                    "id": "no_earnings",
                    "part": "p3",
                    "field": "rollup.earnings@v1.days_to_earnings",
                    "op": "gt",
                    "value": 10,
                    "mode": "soft",
                    "tolerance": 2,
                    "on_miss": "EVENT_RISK",
                },
            ],
            "tie_break": {"field": "feature.iv_rank", "descending": True, "part": "p4"},
            "notes": ["liquid read as $50M a day traded (no amount given)"],
            "parts": [
                {
                    "id": "p1",
                    "words": "liquid stocks",
                    "reading": "Active stocks and ADRs at about $50M a day; 20% under still shown",
                },
                {
                    "id": "p2",
                    "words": "IV rank above 50%",
                    "reading": "IV rank of 50% or more; 0.1 less is still shown",
                },
                {
                    "id": "p3",
                    "words": "no earnings in the next 10 sessions",
                    "reading": "More than 10 days to the next earnings, 2 days of slack",
                },
                {"id": "p4", "words": "rank by IV rank", "reading": "Highest IV rank first"},
            ],
        },
    ),
)


def examples_text() -> str:
    """The worked examples as the task shows them."""
    parts = []
    for n, (sentence, answer) in enumerate(EXAMPLES, 1):
        parts.append(f"Example {n}\nSentence: {sentence}\nAnswer: {json.dumps(answer)}")
    return "\n\n".join(parts) + "\n"


DESCRIPTION_CHARS = 160


def catalogue_line(info: FeatureInfo) -> str:
    """One catalogue field: ``name | type | unit | description | values: ...``."""
    text = " ".join(info.description.split())
    if len(text) > DESCRIPTION_CHARS:
        text = text[: DESCRIPTION_CHARS - 1].rstrip() + "…"
    parts = [info.name, info.dtype, info.unit or "-", text or "-"]
    if info.categories:
        parts.append("values: " + ", ".join(info.categories))
    return " | ".join(parts)


def phrase_line(phrase: Phrase, catalogue: set[str]) -> str | None:
    """One phrasebook entry with the fields this catalogue has (None: it has none of them)."""
    fields = [f for f in phrase.fields if f in catalogue]
    if not fields:
        return None
    hint = " ".join(phrase.hint.split())
    line = f"{' / '.join(phrase.say[:SAY_SHOWN])} | {', '.join(fields)} | {hint or '-'}"
    exact = _structured_text(phrase, catalogue)
    return f"{line} | = {exact}" if exact else line


def _structured_text(phrase: Phrase, catalogue: set[str]) -> str:
    """The entry's structured meaning, compact: ``field op value`` joined by `` and `` (every
    criterion applies), or the readings of an ambiguous word (``label: criterion``, the default
    first); empty without one or when a field is not in this catalogue."""
    if phrase.criteria:
        if all(c.field in catalogue for c in phrase.criteria):
            return " and ".join(c.short() for c in phrase.criteria)
        return ""
    if not phrase.alternatives or any(
        a.criterion.field not in catalogue for a in phrase.alternatives
    ):
        return ""
    order = [
        phrase.default_index,
        *(i for i in range(len(phrase.alternatives)) if i != phrase.default_index),
    ]
    readings = (phrase.alternatives[i] for i in order)
    return "one of " + "; ".join(f"{a.label}: {a.criterion.short()}" for a in readings)


def _value(value: Any) -> str:
    return json.dumps(value)


def use_text(use: GuideUse) -> str:
    """One intent as the model should write it: ``intent: op value mode [tolerance] [on_miss]
    (note)``."""
    parts = [use.op]
    if use.op not in ("is_null", "not_null"):
        parts.append(_value(use.value))
    parts.append(use.mode)
    if use.tolerance is not None:
        parts.append(f"tolerance {_value(use.tolerance)}")
    if use.on_miss:
        parts.append(f"on_miss {use.on_miss}")
    text = f"{use.intent}: {' '.join(parts)}"
    return f"{text} ({use.note})" if use.note else text


def situation_line(situation: Situation, catalogue: set[str]) -> str | None:
    """One situation with the affected fields this catalogue has (None: it has none)."""
    affects = [f for f in situation.affects if f in catalogue]
    if not affects:
        return None
    return f"{situation.name} | {situation.signs} | affects: {', '.join(affects)} | {situation.do}"


INDEX_HEADER = (
    "Field index (every field you may use). A heading ends in .*: a field's name is the heading "
    "without the * followed by the entry's name, e.g. rollup.price_stats@v2.* with close is "
    "rollup.price_stats@v2.close. An entry is name|type|unit. Detail for the fields most likely "
    "to matter follows it; a field with no detail is still valid:"
)


def index_group(name: str) -> tuple[str, str]:
    """``(heading, local name)`` of a field: ``rollup.price_stats@v2.`` + ``close``;
    ``feature.`` + ``iv_rank``; a name with no dot has the empty heading."""
    if "@" in name:  # rollup.<group>@vN.<column>
        head, _, tail = name.rpartition(".")
    elif "." in name:
        head, _, tail = name.partition(".")
    else:
        return "", name
    return f"{head}.", tail


def index_line(info: FeatureInfo) -> str:
    """One field of the index under its heading: ``local name|type|unit``."""
    return f"{index_group(info.name)[1]}|{info.dtype}|{info.unit or '-'}"


def index_text(site: Iterable[FeatureInfo]) -> str:
    """The index of ``site`` fields: one ``<heading>*`` line per prefix, then its entries (names
    sorted, so a heading is not repeated)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for info in sorted(site, key=lambda i: i.name):
        groups[index_group(info.name)[0]].append(index_line(info))
    return "\n".join(f"{head}*\n" + "\n".join(lines) for head, lines in groups.items())


_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_NULL_RULE = re.compile(r"\b(null|unknown)\b", re.IGNORECASE)
# A sentence that says how to use the field (a name may be given without its section prefix).
_HOW_TO = re.compile(
    r"\b(use|never|do not|don't|soft|hard|score|gate|check|pair|rank)\b", re.IGNORECASE
)


def caveat_sentences(entry: FieldGuideEntry, catalogue: set[str]) -> list[str]:
    """The caveat text a slice keeps, in file order: the first sentence of the first caveat,
    then every sentence that names a catalogue field (what to check), states the null rule or
    says how to use the field (use, never, soft, hard, score, gate, check, pair, rank)."""
    keep: list[str] = []
    for n, caveat in enumerate(entry.caveats):
        for k, sentence in enumerate(_SENTENCE.split(" ".join(caveat.split()))):
            named = any(m in catalogue for m in FIELD_REF.findall(sentence))
            wanted = (
                (n == 0 and k == 0)
                or named
                or _NULL_RULE.search(sentence)
                or _HOW_TO.search(sentence)
            )
            if wanted and sentence not in keep:
                keep.append(sentence)
    return keep


def slice_guide_line(
    entry: FieldGuideEntry, catalogue: set[str], caveats: bool = True
) -> str | None:
    """A field guide entry trimmed for the slice: ``name | use: ... | caveat: ...`` where the
    caveat keeps its lead sentence, every sentence naming a field to check, and the null rule
    (no ``reads``: the catalogue line describes the field); ``caveats=False`` leaves them out
    (a brief field). None when the field is not in this
    catalogue."""
    if entry.name not in catalogue:
        return None
    uses = "use: " + "; ".join(use_text(u) for u in entry.uses) if entry.uses else "use: -"
    parts = [entry.name, uses]
    kept = caveat_sentences(entry, catalogue) if caveats else []
    if kept:
        parts.append("caveat: " + " ".join(kept))
    return " | ".join(parts)


SAY_SHOWN = 4  # wordings of an entry the prompt lists (the slice still matches on all of them)
KEY_CHARS = 60  # of an open key's description (PROMPT_LIMIT keys must stay inside the budget)
_WORD = re.compile(r"[a-z0-9]{3,}")
OPEN_HEADER = "Open requests (key | what it is); reuse one as a missing item's key when it fits:"


# Feature groups kept out of the drafting prompt: their columns are not for natural-language drafts
# yet (etf_macro@v1: macro signals on about 30 carrier funds), and 32 more index lines crowd the
# budget. The first edges screen on them since EB E5 batch Y, and the group stays out: removing it
# pushes golden cases' fields out of the slice (open, for the architect). Decision log 2026-10-18.
UNDRAFTED_GROUPS = frozenset({"etf_macro@v1"})
# Expression features of the allocation edges (EB E5 batch Y) that read those columns or are for a
# canary gate: two more index lines tip the slice margin, and neither is a stock screen's field.
UNDRAFTED_FIELDS = frozenset({"feature.credit_spread_vs_ma200", "feature.momentum_13612w"})


def draftable(catalogue: Iterable[FeatureInfo]) -> list[FeatureInfo]:
    """``catalogue`` without the fields of ``UNDRAFTED_GROUPS`` and ``UNDRAFTED_FIELDS``."""
    return [
        i for i in catalogue if i.group not in UNDRAFTED_GROUPS and i.name not in UNDRAFTED_FIELDS
    ]


def prefix_text(catalogue: Iterable[FeatureInfo]) -> str:
    """The part of the sliced prompt that no sentence changes: the task, the examples and the
    index of every SITE field (sorted by name)."""
    site = sorted((i for i in draftable(catalogue) if i.scope == "site"), key=lambda i: i.name)
    return f"{TASK}\n{examples_text()}\n{INDEX_HEADER}\n{index_text(site)}\n"


def relevant_keys(
    sentence: str, open_keys: Iterable[tuple[str, str]], limit: int = PROMPT_LIMIT
) -> list[tuple[str, str]]:
    """At most ``limit`` of the open (key, description) pairs: those whose key or description
    share the most words with the sentence first, then by key (deterministic)."""
    said = set(_WORD.findall(sentence.lower()))

    def score(pair: tuple[str, str]) -> int:
        return len(said & set(_WORD.findall(f"{pair[0].replace('_', ' ')} {pair[1]}".lower())))

    return sorted(open_keys, key=lambda p: (-score(p), p[0]))[:limit]


def _tokens(text: str) -> int:
    return len(text) // 4


def _weigher(
    infos: Sequence[FeatureInfo], guide: FieldGuideSettings | None
) -> Callable[[str, bool], int]:
    """``weigh(name, brief)`` for ``select_slice``: the tokens of the field's detail line and guide
    entry as the prompt renders them (a brief field's entry has no caveats)."""
    names = {i.name for i in infos}
    lines = {i.name: catalogue_line(i) for i in infos if i.scope == "site"}
    entries = {e.name: e for e in guide.fields} if guide is not None else {}

    def weigh(name: str, brief: bool) -> int:
        text = lines.get(name, "")
        entry = entries.get(name)
        if entry is not None and (line := slice_guide_line(entry, names, not brief)) is not None:
            text += "\n" + line
        return _tokens(text) + 1

    return weigh


def slice_for(
    catalogue: Iterable[FeatureInfo],
    sentence: str,
    phrasebook: Iterable[Phrase] = (),
    guide: FieldGuideSettings | None = None,
    open_keys: Iterable[tuple[str, str]] = (),
    slice_tokens: int | None = None,
) -> Slice:
    """The slice ``sliced_system_prompt`` renders for ``sentence``: ``select_slice`` under the
    token budget left once everything else in the prompt (task, examples, index, open keys, the
    matched phrasebook entries, the caller's own features) is counted, and under ``slice_tokens``
    when given (the small slice of one part's re-draft). The plan is checked against
    the rendered prompt and tightened until the whole fits ``PROMPT_BUDGET_TOKENS`` (or only the
    phrasebook and core fields remain)."""
    infos, book, keys = draftable(catalogue), tuple(phrasebook), tuple(open_keys)
    weigh = _weigher(infos, guide)
    matched = select_slice(sentence, infos, book, guide, 0, weigh).phrases
    bare = Slice((), frozenset(), matched)
    room = PROMPT_BUDGET_TOKENS - SECTION_TOKENS
    room -= _tokens(_render(infos, sentence, bare, guide, keys))
    if slice_tokens is not None:
        room = min(room, slice_tokens)
    chosen = select_slice(sentence, infos, book, guide, room, weigh)
    if _tokens(_render(infos, sentence, chosen, guide, keys)) > PROMPT_BUDGET_TOKENS:
        # the weigher counts a field's own lines, not the situations it brings: find by halving
        # the largest room whose whole prompt fits (the fewest fields when none does)
        low, high = 0, room
        chosen = select_slice(sentence, infos, book, guide, 0, weigh)
        while high - low > 8:
            mid = (low + high) // 2
            plan = select_slice(sentence, infos, book, guide, mid, weigh)
            if _tokens(_render(infos, sentence, plan, guide, keys)) <= PROMPT_BUDGET_TOKENS:
                chosen, low = plan, mid
            else:
                high = mid
    total = _tokens(_render(infos, sentence, chosen, guide, keys))
    if total > PROMPT_BUDGET_TOKENS:  # the phrasebook, core fields and own features alone
        log.warning("drafting prompt over budget: %d > %d tokens", total, PROMPT_BUDGET_TOKENS)
    return chosen


def sliced_system_prompt(
    catalogue: Iterable[FeatureInfo],
    sentence: str,
    phrasebook: Iterable[Phrase] = (),
    guide: FieldGuideSettings | None = None,
    open_keys: Iterable[tuple[str, str]] = (),
    slice_tokens: int | None = None,
) -> str:
    """The prompt for one sentence (ADR 0041, plan "Token and latency budget"): ``prefix_text``
    (byte-identical across sentences), then the slice ``slice_for`` picks (catalogue lines,
    trimmed guide entries, the phrasebook entries the sentence says, the situations over the
    slice), then the caller's own features in full (``scope != "site"``, sorted; most users have
    none). The sentence itself is in the user prompt. ``slice_tokens`` caps the slice (a part's
    re-draft sends the same prefix and a small one, ``services/drafting/redraft``)."""
    infos, keys = draftable(catalogue), tuple(open_keys)
    chosen = slice_for(infos, sentence, phrasebook, guide, keys, slice_tokens)
    return _render(infos, sentence, chosen, guide, keys)


def _render(
    infos: Sequence[FeatureInfo],
    sentence: str,
    chosen: Slice,
    guide: FieldGuideSettings | None,
    open_keys: Iterable[tuple[str, str]],
) -> str:
    """The prompt text for a chosen slice."""
    names = {info.name for info in infos}
    picked = set(chosen.fields)
    detail = [i for i in sorted(infos, key=lambda i: i.name) if i.name in picked]
    detail = [i for i in detail if i.scope == "site"]
    own = sorted((i for i in infos if i.scope != "site"), key=lambda i: i.name)
    out = prefix_text(infos)
    keys = [
        f"{key} | {' '.join(description.split())[:KEY_CHARS]}"
        for key, description in relevant_keys(sentence, open_keys)
    ]
    if keys:
        out += f"\n{OPEN_HEADER}\n" + "\n".join(keys) + "\n"
    out += "\nDetail (name | type | unit | description | values):\n"
    out += "\n".join(catalogue_line(i) for i in detail) + "\n"
    phrases = [line for p in chosen.phrases if (line := phrase_line(p, names)) is not None]
    if phrases:
        out += "\nPhrasebook (what the trader says | fields | how to use them | exact default):\n"
        out += "\n".join(phrases) + "\n"
    if guide is not None:
        entries = [
            line
            for e in guide.fields
            if e.name in picked
            and (line := slice_guide_line(e, names, e.name not in chosen.brief)) is not None
        ]
        if entries:
            out += "\nField guide (field | the criterion per intent | main caveat):\n"
            out += "\n".join(entries) + "\n"
        situations = [
            line
            for s in guide.situations
            if picked.intersection(s.affects) and (line := situation_line(s, names)) is not None
        ]
        if situations:
            out += (
                "\nSituations that fool a threshold (situation | signs | affects | what to do):\n"
            )
            out += "\n".join(situations) + "\n"
    if own:
        out += "\nYour own features (name | type | unit | description | values):\n"
        out += "\n".join(catalogue_line(info) for info in own) + "\n"
    return out


def user_prompt(screener_id: str, text: str, current: Mapping[str, Any] | None) -> str:
    """The sentence, with the current draft's criteria (if any) for the model to keep."""
    criteria = (current or {}).get("criteria") or {}
    shown = json.dumps(criteria, sort_keys=True) if criteria else "none"
    return f"Screener id: {screener_id}\nCurrent criteria: {shown}\nSentence: {text.strip()}\n"
