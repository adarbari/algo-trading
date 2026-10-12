"""The draft of a sentence the phrasebook resolves without the model (ADR 0041; plan lever 3).
``shortcut`` turns a ``Resolution`` into an answer in the model's own shape (``answer_schema``:
criteria, each tagged with the part of the sentence it comes from, and the parts, quoting the
trader's own words), so ``draft_screen`` runs it through the same parsing, validation and
attribution as a model's answer; ``served`` then marks the parts' readings as the server's own
(built from the entries' criteria here, never a model's words) and drops the gaps that hold only
filler. Every doubt returns ``None`` and the model answers instead: the Builder's ``current``
criteria are kept and added to, never reinterpreted (a phrase on a field ``current`` already
has, an id the Builder would not keep, a shape that is not a criteria table); a phrase two
entries or two places of the sentence say; criteria two entries share; more parts than the
cap; words nothing explains. The ``instrument.status`` = ``ACTIVE`` scaffolding the prompt
always asks of the model is added when no entry says it (an ``unplaced`` row, as for the model).
Pure; no model, no storage."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from algotrade.core.model.predicates import NO_VALUE_OPS
from algotrade.services.drafting.answer_schema import check_criterion
from algotrade.services.drafting.parts.model import MAX_PARTS, MAX_READING, Part
from algotrade.services.drafting.parts.spans import CONNECTORS
from algotrade.services.drafting.phrasebook.resolve import FILLER, Resolution
from algotrade.services.drafting.retrieval import stem

STATUS = "instrument.status"
ACTIVE = {"id": "active", "field": STATUS, "op": "eq", "value": "ACTIVE", "mode": "hard"}
KEPT_KEYS = ("field", "op", "value", "mode", "tolerance", "on_miss")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WORD = re.compile(r"[a-z0-9]+")
_OPS = {
    "eq": "is", "ne": "is not", "gt": "above", "gte": "at least", "lt": "below",
    "lte": "at most", "in": "is one of", "not_in": "is not one of", "between": "is between",
    "is_null": "is missing", "not_null": "is present",
}  # fmt: skip


@dataclass(frozen=True)
class Shortcut:
    """``answer``: the draft in the model's answer shape; ``readings``: part id -> the line the
    server reads that part as."""

    answer: dict[str, Any]
    readings: dict[str, str]


def shortcut(
    resolution: Resolution, sentence: str, current: Mapping[str, Any] | None
) -> Shortcut | None:
    """The answer for ``resolution`` over ``sentence`` and the Builder's ``current`` document, or
    ``None`` when the model should answer (see the module docstring)."""
    if len(resolution.claims) > MAX_PARTS:
        return None
    kept = _kept(current)
    if kept is None:
        return None
    held_fields = {c["field"] for c in kept if isinstance(c.get("field"), str)}
    owner: dict[tuple[str, str], int] = {}
    criteria: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    readings: dict[str, str] = {}
    for n, claim in enumerate(resolution.claims, 1):
        mine = [c.as_answer() for c in claim.phrase.criteria]
        if not mine or any(c["field"] in held_fields for c in mine):  # current: the model decides
            return None
        for c in mine:
            key = (c["field"], c["op"])
            if key in owner:  # two places, or two entries, say one criterion
                return None
            owner[key] = n
        words = sentence[claim.start : claim.end]
        parts.append({"id": f"p{n}", "words": words, "reading": None})
        readings[f"p{n}"] = _reading(mine)
    for c in resolution.criteria:  # file order, as the resolution gives them
        criteria.append({**c, "part": f"p{owner[(c['field'], c['op'])]}"})
    if STATUS not in held_fields | {c["field"] for c in criteria}:
        criteria.append(dict(ACTIVE))
    return Shortcut(
        {"criteria": [*kept, *criteria], "tie_break": None, "notes": [], "parts": parts}, readings
    )


def _kept(current: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    """The Builder's criteria as items of the answer (no part: they come from no words), ``[]``
    when it has none, ``None`` for a shape or an id the draft would not carry over as it is."""
    held = current.get("criteria") if isinstance(current, Mapping) else None
    if not held:
        return []
    if not isinstance(held, Mapping):
        return None
    out: list[dict[str, Any]] = []
    for cid, criterion in held.items():
        if not isinstance(cid, str) or not _ID.match(cid) or not isinstance(criterion, Mapping):
            return None
        item = {"id": cid, **{k: criterion[k] for k in KEPT_KEYS if k in criterion}}
        if check_criterion({**item, "part": None}) is not None:  # not the answer's criterion shape
            return None
        out.append(item)
    return out


def _reading(criteria: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(_say(c) for c in criteria)[:MAX_READING].rstrip()


def _say(c: Mapping[str, Any]) -> str:
    column = str(c["field"]).rsplit(".", 1)[-1]
    op = c["op"]
    text = f"{column} {_OPS.get(op, op)}"
    if op not in NO_VALUE_OPS:
        value = c.get("value")
        shown = " and ".join(map(_value, value or ())) if op == "between" else _value(value)
        text += f" {shown}"
    if c.get("mode", "hard") != "hard" and c.get("tolerance") is not None:
        text += f" (a near miss within {_value(c['tolerance'])} is kept as {c['mode']})"
    return text


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, Mapping):
        return " or ".join(f"{k} {_value(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(map(_value, value))
    return str(value)


def served(parts: Sequence[Part], shortcut_: Shortcut) -> tuple[Part, ...] | None:
    """``parts`` (as ``build_parts`` made them from the shortcut's answer) with the server's
    readings, without the gaps that hold only filler words; ``None`` when a part is not
    understood or a gap holds anything else."""
    out: list[Part] = []
    for part in parts:
        if part.origin == "gap":
            words = [stem(w) for w in _WORD.findall(part.words.lower())]
            if all(w in FILLER or w in CONNECTORS for w in words):
                continue
            return None
        if part.kind == "not_understood":
            return None
        reading = shortcut_.readings.get(part.id)
        out.append(replace(part, reading=reading, reading_source="server") if reading else part)
    return tuple(out)
