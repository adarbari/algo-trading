"""The items of a draft as the attribution sees them (ADR 0041, amended 2026-10-11): one ``Item``
per criterion of the document (and per dropped one), pending formula, missing request, ambiguous
term, suggestion and the rank, carrying the part id the model tagged it with, the words it
quoted, its field, whether the Builder's current document already had it, and the numbers a
reading of its part may cite. Pure."""

from collections.abc import Mapping, Sequence
from typing import Any

from algotrade.services.drafting.contract.formulas import DraftFormula
from algotrade.services.drafting.contract.gaps import MissingFeature, Unresolved
from algotrade.services.drafting.contract.suggestions import Suggestion
from algotrade.services.drafting.parts.consistency import names_numbers, stated, values_of
from algotrade.services.drafting.parts.model import Item


def _frozen(value: Any) -> Any:
    """``value`` as something hashable (the Builder's document is whatever the client sent)."""
    if isinstance(value, list):
        return tuple(_frozen(v) for v in value)
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _frozen(v)) for k, v in value.items()))
    return value


def _reading(criterion: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    return (criterion.get("field"), criterion.get("op"), _frozen(criterion.get("value")))


def _numbers(criterion: Mapping[str, Any]) -> tuple[float, ...]:
    return (
        *values_of(criterion.get("value")),
        *values_of(criterion.get("tolerance")),
        *names_numbers([str(criterion.get("field", ""))]),
    )


def items_of(
    criteria: Mapping[str, Mapping[str, Any]],
    tags: Mapping[str, str | None],
    current: Mapping[str, Any] | None,
    dropped: Sequence[tuple[str, str]],
    formulas: Sequence[DraftFormula],
    unresolved: Sequence[Unresolved],
    missing: Sequence[MissingFeature],
    suggestions: Sequence[Suggestion],
    rank: tuple[str | None, str] | None,
    spans: Mapping[str, str] | None = None,
) -> list[Item]:
    """The items of a draft: ``criteria`` the document's (id -> criterion), ``tags`` the model's
    part of each criterion id, ``current`` the Builder's document, ``dropped`` (id, field) of the
    criteria dropped, ``rank`` the (tag, field) of the document's tie-break, ``spans`` the words
    a criterion stands for when it is the default reading of an ambiguous term."""
    held = current.get("criteria") if isinstance(current, Mapping) else None
    carried = (
        {_reading(c) for c in held.values() if isinstance(c, Mapping)}
        if isinstance(held, Mapping)
        else set()
    )
    out = [
        Item(
            "criteria",
            cid,
            tags.get(cid),
            (spans or {}).get(cid),
            c["field"],
            _reading(c) in carried,
            _numbers(c),
        )
        for cid, c in criteria.items()
    ]
    out += [Item("dropped", cid, tags.get(cid), None, field) for cid, field in dropped]
    for f in formulas:
        c = f.criterion or {}
        numbers = (*values_of(c.get("value")), *values_of(c.get("tolerance")),
                   *stated(f.expr), *names_numbers(f.inputs))  # fmt: skip
        out.append(Item("formulas", f.name, f.part, None, None, False, numbers))
    for u in unresolved:
        options = [a.criterion for a in u.alternatives]
        numbers = tuple(n for c in options for n in _numbers(c))
        out.append(Item("unresolved", u.term, u.part, u.span, options[u.default_index]["field"],
                        False, numbers))  # fmt: skip
    out += [Item("missing", m.key or str(m.new_key_slug), m.part, m.span) for m in missing]
    out += [
        Item("suggestions", s.id, s.part, None, s.criterion["field"], False, _numbers(s.criterion))
        for s in suggestions
    ]
    if rank is not None:
        out.append(Item("rank", "rank", rank[0], None, rank[1]))
    return out
