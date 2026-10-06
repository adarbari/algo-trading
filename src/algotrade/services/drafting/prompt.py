"""The prompt a screener draft is asked with (ADR 0040): the task, the rule-screen grammar
(``docs/screeners/rules.md``), the caller's field catalogue in catalogue order (name, type, unit,
description, the values of a category) and the sentence. Rendered from the catalogue with no
timestamps or ids, so the same catalogue gives the same bytes (a provider's prompt cache hits
and a recorded test stays valid). The prompt carries no market data, results or credentials."""

import json
from collections.abc import Iterable, Mapping
from typing import Any

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

Answer shape:
{"criteria": [ ... ], "tie_break": {"field": "...", "descending": true} or null,
 "notes": ["anything you could not map, or assumed"]}
"""

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


def system_prompt(catalogue: Iterable[FeatureInfo]) -> str:
    """The task and the catalogue (in the order given: the caller's catalogue order)."""
    lines = "\n".join(catalogue_line(info) for info in catalogue)
    return f"{TASK}\nCatalogue (name | type | unit | description | values):\n{lines}\n"


def user_prompt(screener_id: str, text: str, current: Mapping[str, Any] | None) -> str:
    """The sentence, with the current draft's criteria (if any) for the model to keep."""
    criteria = (current or {}).get("criteria") or {}
    shown = json.dumps(criteria, sort_keys=True) if criteria else "none"
    return f"Screener id: {screener_id}\nCurrent criteria: {shown}\nSentence: {text.strip()}\n"
