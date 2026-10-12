"""Suggested checks (ADR 0041, amended 2026-10-11, owner decision 2026-10-11): the protective
checks a caveat or situation of the field guide raises that the sentence did not ask for (a
trend or earnings check on a yield screen). The model proposes them in ``suggestions``; the
server never puts one in the document: a trader accepts or skips each in the review panel, as
with a pending formula or a missing feature (nothing the model proposes is applied silently).

A suggestion is ``{field, op, value, mode, tolerance, on_miss, why, source}`` with the criterion
rules of ``screens._criterion`` (a catalogue field, a known op, a value of the right shape, a
tolerance) and one more: ``mode`` is ``soft`` or ``score``, never ``hard`` (a missing mode is
refused too, since a criterion without one is hard). One that does not validate, repeats a
criterion of the draft (same field, op and value) or another suggestion, or is over the cap
(``MAX_SUGGESTIONS``) is dropped; a refused one is listed with its reason in ``dropped`` (a
duplicate is dropped quietly: there is nothing to report). ``why`` is the short reason shown
beside it and ``source`` the field guide entry or field that raised it. Pure; writes nothing."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.contract.answer_schema import SUGGESTION, check_item
from algotrade.services.drafting.parts.model import part_tag

MAX_SUGGESTIONS = 5
SUGGESTED_MODES = ("soft", "score")

# (proposed item, its field name) -> a criterion the validator accepts, or ``ConfigurationError``
Build = Callable[[Mapping[str, Any], str], dict[str, Any]]


class SuggestionError(ConfigurationError):
    """A suggestion that does not hold: ``kind`` says which check refused it."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Suggestion:
    """A protective check offered, never applied: a soft or score criterion with the reason.
    ``id`` (``s1``, ``s2``...) is the server's, so a part can point at it; ``part`` is the part
    id the model tagged it with (explained parts)."""

    criterion: dict[str, Any]
    why: str
    source: str | None
    id: str = ""
    part: str | None = None


@dataclass(frozen=True)
class DroppedSuggestion:
    """A suggestion the draft does not offer, and why. ``reason`` is what the Builder shows;
    ``kind`` (the check that refused it, as ``DroppedCriterion.kind``, plus ``over_cap``) and
    ``detail`` (that check and the JSON path only, e.g. ``bad_value: suggestions[0].value``: no
    quoted value, never the model's ``why``) carry no model prose, so a report can use them."""

    field: str
    reason: str
    kind: str = "other"
    detail: str = ""


def suggestions_of(
    proposal: Mapping[str, Any],
    build: Build,
    held: list[Mapping[str, Any]],
    offered: list[Mapping[str, Any]] | None = None,
) -> tuple[tuple[Suggestion, ...], tuple[DroppedSuggestion, ...]]:
    """The proposed ``suggestions`` checked, and the ones dropped with a reason. ``build``
    validates one as a criterion (``screens._alternative``); ``held`` are the criteria of the
    draft (a suggestion repeating one, or on the same field in the same direction (``gt`` /
    ``gte`` above, ``lt`` / ``lte`` below), is dropped quietly: it would rewrite what the sentence
    asked; the opposite direction is kept); ``offered`` are criteria shown elsewhere (the
    alternatives of an unresolved term): a suggestion repeating one is dropped quietly too."""
    raw = proposal.get("suggestions")
    items = raw if isinstance(raw, list) else []
    kept: list[Suggestion] = []
    dropped: list[DroppedSuggestion] = []
    seen = {_reading(c) for c in [*held, *(offered or [])]}
    asked = {(c["field"], _direction(c["op"])) for c in held}  # a threshold the sentence set
    for n, item in enumerate(items):
        mapping = item if isinstance(item, Mapping) else {}
        name = mapping.get("field")
        field_name = name if isinstance(name, str) else ""
        try:
            suggestion = _one(item, field_name, build)
        except ConfigurationError as exc:
            kind = getattr(exc, "kind", "validator")  # ``screens.CriterionError`` has one
            dropped.append(
                DroppedSuggestion(field_name, str(exc), kind, _detail(kind, n, str(exc)))
            )
            continue
        reading = _reading(suggestion.criterion)
        if (
            reading in seen or (reading[0], _direction(reading[1])) in asked
        ):  # a repeat, or a rewrite of an asked threshold
            continue
        if len(kept) >= MAX_SUGGESTIONS:
            dropped.append(
                DroppedSuggestion(
                    field_name,
                    f"over the {MAX_SUGGESTIONS} allowed",
                    "over_cap",
                    _detail("over_cap", n, ""),
                )
            )
            continue
        seen.add(reading)
        kept.append(replace(suggestion, id=f"s{len(kept) + 1}"))
    return tuple(kept), tuple(dropped)


def _one(item: Any, field_name: str, build: Build) -> Suggestion:
    if (shape := check_item(item, SUGGESTION, "suggestion")) is not None:
        raise SuggestionError("bad_shape", f"not the suggestion shape ({shape})")
    mode = item.get("mode")
    if mode not in SUGGESTED_MODES:
        raise SuggestionError(
            "bad_mode",
            f"a suggestion is soft or score, never hard (got {mode if mode else 'no mode'!s})",
        )
    criterion = build(item, field_name)
    why = " ".join(str(item.get("why") or "").split())
    if not why:
        raise SuggestionError("missing_why", "a suggestion needs a short reason (why)")
    source = item.get("source")
    return Suggestion(
        criterion, why, source if isinstance(source, str) and source else None, part=part_tag(item)
    )


_PATH = {
    "not_in_catalogue": ".field", "bad_op": ".op", "bad_mode": ".mode", "bad_value": ".value",
    "missing_why": ".why", "validator": ".criterion",
}  # fmt: skip


def _detail(kind: str, n: int, message: str) -> str:
    """``kind`` and the JSON path of the part that failed: built from the check, never from the
    model's words or values."""
    part = ".tolerance" if kind == "bad_value" and message.startswith("tolerance") else None
    return f"{kind}: suggestions[{n}]{part or _PATH.get(kind, '')}"


def _direction(op: str) -> str:
    """``above`` for gt / gte, ``below`` for lt / lte, else the op itself."""
    return {"gt": "above", "gte": "above", "lt": "below", "lte": "below"}.get(op, op)


def _reading(criterion: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = criterion.get("value")
    return criterion["field"], criterion["op"], tuple(value) if isinstance(value, list) else value
