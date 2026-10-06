"""The prompt a screener draft is asked with (ADR 0041): the task, the rule-screen grammar
(``docs/screeners/rules.md``), two worked examples, the caller's field catalogue in catalogue
order (name, type, unit, description, the values of a category), the site phrasebook (trader
vocabulary -> fields, ``config/site/phrasebook.toml``; a phrase keeps only the fields this
catalogue has), the site field guide (``config/site/field_guide/*.toml``: how to read a field,
the usual criterion per intent, the caveats, and the situations that fool several thresholds;
only entries over this catalogue's fields, sources left out) and the sentence. Rendered with no
timestamps or ids, so the same catalogue, phrasebook and guide give the same bytes (a provider's
prompt cache hits and a recorded test stays valid). The prompt carries no market data, results
or credentials."""

import json
from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.config.site.field_guide import (
    FieldGuideEntry,
    FieldGuideSettings,
    GuideUse,
    Situation,
)
from algotrade.config.site.llm import Phrase
from algotrade.services.read.instruments.catalogue import FeatureInfo

TASK = """\
You turn a trader's sentence into the criteria of a rule screen over a catalogue of stored
fields. Answer with ONE JSON object and nothing else (no prose, no code fence).

A rule screen is a list of criteria; an instrument is picked when every criterion holds.
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

Rules:
- Use only catalogue fields. Never invent a field: when the sentence asks for something the
  catalogue does not have, leave it out and say so in "notes".
- Percentages become fractions for a field whose unit is a fraction (50% -> 0.5); a field
  whose unit is percent takes 50. Dollar amounts are plain numbers (50M -> 50000000).
- "stocks" means instrument.security_type in ["COMMON_STOCK", "ADR"]; "ETFs" means ["ETF"];
  "optionable" means instrument.optionable eq true. Always include instrument.status eq
  "ACTIVE" (id "active") unless the sentence says otherwise.
- Gates (price, liquidity, kind of instrument) are hard. A threshold where a near miss is
  worth seeing is soft with a sensible tolerance. "prefer" / "ideally" is score.
- "rank by X" / "sort by X" sets "tie_break" (descending unless the sentence says lowest
  first); otherwise "tie_break" is null.
- When current criteria are given, keep every one the sentence does not change and answer
  with the complete new list.
- The phrasebook after the catalogue says which fields a trader's words mean and how to
  use them (the gate, a confirmation, a score; typical thresholds). Follow it; prefer its
  thresholds to your own; say in "notes" when you had to choose one.
- The field guide after the phrasebook says how to read a field, the usual criterion for
  each intent (op, value, mode, tolerance) and when the reading lies. Take thresholds from
  it, never from memory. When a caveat or a situation names a field to check, add that
  criterion (soft or score, so it lists rather than rejects) and say why in "notes".

Answer shape:
{"criteria": [ ... ], "tie_break": {"field": "...", "descending": true} or null,
 "notes": ["anything you could not map, or assumed"]}
"""

# Two worked examples (sentence -> answer), rendered into the task so a smaller model sees the
# shape and the judgement expected. Their fields exist in the site catalogue (a test checks).
EXAMPLES: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "stocks with upward momentum that are close to their 52-week low",
        {
            "criteria": [
                {
                    "id": "active",
                    "field": "instrument.status",
                    "op": "eq",
                    "value": "ACTIVE",
                    "mode": "hard",
                    "why": "stocks (listed)",
                },
                {
                    "id": "stocks",
                    "field": "instrument.security_type",
                    "op": "in",
                    "value": ["COMMON_STOCK", "ADR"],
                    "mode": "hard",
                    "why": "stocks",
                },
                {
                    "id": "near_low",
                    "field": "feature.pct_from_low_52w",
                    "op": "lte",
                    "value": 0.10,
                    "mode": "soft",
                    "tolerance": 0.05,
                    "why": "close to their 52-week low",
                },
                {
                    "id": "momentum",
                    "field": "rollup.price_stats@v2.ret_20d",
                    "op": "gt",
                    "value": 0,
                    "mode": "hard",
                    "why": "upward momentum",
                },
                {
                    "id": "above_sma20",
                    "field": "feature.pct_vs_sma_20",
                    "op": "gt",
                    "value": 0,
                    "mode": "soft",
                    "tolerance": 0.02,
                    "why": "upward momentum (confirmation)",
                },
                {
                    "id": "rsi",
                    "field": "rollup.momentum@v1.rsi_14",
                    "op": "gte",
                    "value": 50,
                    "mode": "score",
                    "tolerance": 20,
                    "why": "upward momentum (strength)",
                },
            ],
            "tie_break": {"field": "rollup.price_stats@v2.ret_20d", "descending": True},
            "notes": [
                "momentum read as a positive 20-day return, confirmed above the 20-day average; "
                "RSI only scores",
                "near the low read as within 10% of the 52-week low (5% near-miss band)",
            ],
        },
    ),
    (
        "liquid optionable stocks over $10 with IV rank above 50% and no earnings in the next "
        "10 sessions, rank by IV rank",
        {
            "criteria": [
                {
                    "id": "active",
                    "field": "instrument.status",
                    "op": "eq",
                    "value": "ACTIVE",
                    "mode": "hard",
                    "why": "stocks (listed)",
                },
                {
                    "id": "stocks",
                    "field": "instrument.security_type",
                    "op": "in",
                    "value": ["COMMON_STOCK", "ADR"],
                    "mode": "hard",
                    "why": "stocks",
                },
                {
                    "id": "optionable",
                    "field": "instrument.optionable",
                    "op": "eq",
                    "value": True,
                    "mode": "hard",
                    "why": "optionable",
                },
                {
                    "id": "price",
                    "field": "rollup.price_stats@v2.close",
                    "op": "gt",
                    "value": 10,
                    "mode": "hard",
                    "why": "over $10",
                },
                {
                    "id": "liquid",
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
                    "field": "feature.iv_rank",
                    "op": "gte",
                    "value": 0.5,
                    "mode": "soft",
                    "tolerance": 0.1,
                    "why": "IV rank above 50%",
                },
                {
                    "id": "no_earnings",
                    "field": "rollup.earnings@v1.days_to_earnings",
                    "op": "gt",
                    "value": 10,
                    "mode": "soft",
                    "tolerance": 2,
                    "on_miss": "EVENT_RISK",
                    "why": "no earnings in the next 10 sessions",
                },
            ],
            "tie_break": {"field": "feature.iv_rank", "descending": True},
            "notes": ["liquid read as $50M a day traded (no amount given)"],
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
    return f"{' / '.join(phrase.say)} | {', '.join(fields)} | {hint or '-'}"


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


def guide_line(entry: FieldGuideEntry, catalogue: set[str]) -> str | None:
    """One field guide entry: ``name | reads | use: ...; ... | caveats: ... ``; None when the
    field is not in this catalogue. Sources stay out of the prompt."""
    if entry.name not in catalogue:
        return None
    parts = [entry.name, entry.reads]
    parts.append("use: " + "; ".join(use_text(u) for u in entry.uses) if entry.uses else "use: -")
    parts.append("caveats: " + " ".join(entry.caveats) if entry.caveats else "caveats: -")
    return " | ".join(parts)


def situation_line(situation: Situation, catalogue: set[str]) -> str | None:
    """One situation with the affected fields this catalogue has (None: it has none)."""
    affects = [f for f in situation.affects if f in catalogue]
    if not affects:
        return None
    return f"{situation.name} | {situation.signs} | affects: {', '.join(affects)} | {situation.do}"


def system_prompt(
    catalogue: Iterable[FeatureInfo],
    phrasebook: Iterable[Phrase] = (),
    guide: FieldGuideSettings | None = None,
) -> str:
    """The task with its examples, the catalogue (in the order given: the caller's catalogue
    order), the phrasebook (file order; entries with none of this catalogue's fields left
    out) and the field guide (file order; entries and situations over this catalogue's fields
    only)."""
    infos = list(catalogue)
    names = {info.name for info in infos}
    lines = "\n".join(catalogue_line(info) for info in infos)
    phrases = [line for p in phrasebook if (line := phrase_line(p, names)) is not None]
    out = (
        f"{TASK}\n{examples_text()}\n"
        f"Catalogue (name | type | unit | description | values):\n{lines}\n"
    )
    if phrases:
        out += "\nPhrasebook (what the trader says | fields | how to use them):\n"
        out += "\n".join(phrases) + "\n"
    if guide is not None:
        entries = [line for e in guide.fields if (line := guide_line(e, names)) is not None]
        if entries:
            out += "\nField guide (field | how to read it | the criterion per intent | caveats):\n"
            out += "\n".join(entries) + "\n"
        situations = [
            line for s in guide.situations if (line := situation_line(s, names)) is not None
        ]
        if situations:
            out += (
                "\nSituations that fool a threshold (situation | signs | affects | what to do):\n"
            )
            out += "\n".join(situations) + "\n"
    return out


def user_prompt(screener_id: str, text: str, current: Mapping[str, Any] | None) -> str:
    """The sentence, with the current draft's criteria (if any) for the model to keep."""
    criteria = (current or {}).get("criteria") or {}
    shown = json.dumps(criteria, sort_keys=True) if criteria else "none"
    return f"Screener id: {screener_id}\nCurrent criteria: {shown}\nSentence: {text.strip()}\n"
