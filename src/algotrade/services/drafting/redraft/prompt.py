"""The scoped prompt of one part's re-draft (ADR 0041, amended 2026-10-12). The system prompt is
the whole draft's, so the provider's prompt cache hits: the same task, examples and field index
(``prompt.prefix_text``, byte for byte), then a slice retrieved for the new words alone and
capped at ``SLICE_TOKENS`` (the whole draft's slice fills the 13,000-token budget), the matched
phrasebook entries and the open request keys. The user prompt says what is asked: the words of
one part, answered in the same JSON with one part, and the criteria of the other parts as compact
fixed rows (``MAX_ROWS`` of at most ``ROW_CHARS``) the model must not repeat, restate or
contradict (the server drops one on the same field and operator). What is not cached is the slice
and the user prompt, under 4,000 tokens (a test measures it). Pure."""

import json
from collections.abc import Iterable, Mapping
from typing import Any

from algotrade.config.site.field_guide import FieldGuideSettings
from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.prompt import sliced_system_prompt
from algotrade.services.read.instruments.catalogue import FeatureInfo

SLICE_TOKENS = 1200  # tokens of detail lines and guide entries for the new words
MAX_ROWS = 24  # fixed criteria shown; the server's merge still holds the rest
ROW_CHARS = 110
ASK = """\
This is a RE-DRAFT of ONE part of a screen the trader already described. Answer with the same JSON
object, for this part only.
- "parts": exactly one part, {"id": "p1", "words": the part's words below, copied exactly,
  "reading": one short line}; every criterion, formula, missing, unresolved, suggestion and the
  tie_break carries "part": "p1".
- "criteria" holds only what these words ask for. The criteria of the other parts are fixed: do not
  repeat, restate or contradict them (a criterion on the same field and operator as one of them is
  discarded). Add no scaffolding (status, kind of instrument): the other parts hold it.
- Keep the answer short: no "notes" unless a word could not be mapped.
"""


def fixed_rows(criteria: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """The criteria of the other parts as ``id | field op value [mode tolerance]``, the first
    ``MAX_ROWS`` (each clipped to ``ROW_CHARS``), then a line saying how many were left out."""
    rows = [_row(cid, c) for cid, c in criteria.items() if isinstance(c, Mapping)]
    shown = rows[:MAX_ROWS]
    if len(rows) > MAX_ROWS:
        shown.append(f"(+{len(rows) - MAX_ROWS} more, not shown)")
    return shown


def _row(cid: str, criterion: Mapping[str, Any]) -> str:
    parts = [f"{criterion.get('field')} {criterion.get('op')}"]
    if "value" in criterion:
        parts.append(json.dumps(criterion["value"], separators=(",", ":")))
    mode = criterion.get("mode")
    if mode and mode != "hard":
        parts.append(str(mode))
        if criterion.get("tolerance") is not None:
            parts.append(json.dumps(criterion["tolerance"], separators=(",", ":")))
    row = f"{cid} | {' '.join(parts)}"
    return row if len(row) <= ROW_CHARS else row[: ROW_CHARS - 1] + "…"


def scoped_prompts(
    infos: Iterable[FeatureInfo],
    screener_id: str,
    words: str,
    others: Mapping[str, Mapping[str, Any]],
    phrasebook: Iterable[Phrase],
    guide: FieldGuideSettings | None,
    open_keys: Iterable[tuple[str, str]],
) -> tuple[str, str]:
    """(system, user) for re-drafting ``words`` while ``others`` (id -> criterion: the criteria
    of the other parts, the trader's hand-added ones too) stay as they are."""
    system = sliced_system_prompt(infos, words, phrasebook, guide, open_keys, SLICE_TOKENS)
    rows = fixed_rows(others)
    fixed = "\n".join(rows) if rows else "none"
    user = (
        f"Screener id: {screener_id}\n{ASK}\n"
        f"Fixed criteria of the other parts (id | field op value mode tolerance):\n{fixed}\n\n"
        f"Part words: {words}\n"
    )
    return system, user
