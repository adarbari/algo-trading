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
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.answer_schema import SUGGESTION, check_item

MAX_SUGGESTIONS = 5
SUGGESTED_MODES = ("soft", "score")

# (proposed item, its field name) -> a criterion the validator accepts, or ``ConfigurationError``
Build = Callable[[Mapping[str, Any], str], dict[str, Any]]


@dataclass(frozen=True)
class Suggestion:
    """A protective check offered, never applied: a soft or score criterion with the reason."""

    criterion: dict[str, Any]
    why: str
    source: str | None


@dataclass(frozen=True)
class DroppedSuggestion:
    """A suggestion the draft does not offer, and why."""

    field: str
    reason: str


def suggestions_of(
    proposal: Mapping[str, Any],
    build: Build,
    held: list[Mapping[str, Any]],
) -> tuple[tuple[Suggestion, ...], tuple[DroppedSuggestion, ...]]:
    """The proposed ``suggestions`` checked, and the ones dropped with a reason. ``build``
    validates one as a criterion (``screens._alternative``); ``held`` are the criteria of the
    draft (a suggestion repeating one is dropped quietly)."""
    raw = proposal.get("suggestions")
    items = raw if isinstance(raw, list) else []
    kept: list[Suggestion] = []
    dropped: list[DroppedSuggestion] = []
    seen = {_reading(c) for c in held}
    for item in items:
        mapping = item if isinstance(item, Mapping) else {}
        name = mapping.get("field")
        field_name = name if isinstance(name, str) else ""
        if mapping and _raw_reading(mapping) in seen:  # a repeat is dropped before it is checked
            continue
        try:
            suggestion = _one(item, field_name, build)
        except ConfigurationError as exc:
            dropped.append(DroppedSuggestion(field_name, str(exc)))
            continue
        reading = _reading(suggestion.criterion)
        if reading in seen:
            continue
        if len(kept) >= MAX_SUGGESTIONS:
            dropped.append(DroppedSuggestion(field_name, f"over the {MAX_SUGGESTIONS} allowed"))
            continue
        seen.add(reading)
        kept.append(suggestion)
    return tuple(kept), tuple(dropped)


def _one(item: Any, field_name: str, build: Build) -> Suggestion:
    if (shape := check_item(item, SUGGESTION, "suggestion")) is not None:
        raise ConfigurationError(f"not the suggestion shape ({shape})")
    mode = item.get("mode")
    if mode not in SUGGESTED_MODES:
        raise ConfigurationError(
            f"a suggestion is soft or score, never hard (got {mode if mode else 'no mode'!s})"
        )
    criterion = build(item, field_name)
    why = " ".join(str(item.get("why") or "").split())
    if not why:
        raise ConfigurationError("a suggestion needs a short reason (why)")
    source = item.get("source")
    return Suggestion(criterion, why, source if isinstance(source, str) and source else None)


def _raw_reading(item: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = item.get("value")
    return item.get("field"), item.get("op"), tuple(value) if isinstance(value, list) else value


def _reading(criterion: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    value = criterion.get("value")
    return criterion["field"], criterion["op"], tuple(value) if isinstance(value, list) else value
