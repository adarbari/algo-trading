"""The rest of the A / B / C contract (ADR 0041, amended 2026-10-11): what the sentence asks that
no stored field answers (``missing``) and the terms it leaves open (``unresolved``).

``missing``: a feature the trader wants that neither a criterion nor a B1 formula can express
(a time window rollup, new data). Its ``key`` is an item of the curated backlog
(``feature_backlog.toml``, by key or alias, in ``key`` or ``new_key_slug``; only an OPEN item
counts, a closed one is dropped with a note); anything else is a
new slug (a key the backlog does not know, or the model's own ``new_key_slug``, slugified when
it is not one), so a request never names an invented key as if it were curated. ``closest``
keeps only names of the catalogue; a ``feasibility`` outside the three words is ``UNCLEAR``.

``unresolved``: an ambiguous term ("liquid") with alternatives, each carrying its own ready
criterion, validated like any criterion of the draft, so the trader's pick swaps in locally.
An alternative that does not validate is dropped (the item needs two left, else it is dropped
whole and said in the notes); ``default_index`` out of range (or its alternative dropped) falls
back to the first. Pure over the catalogue and the backlog; writes nothing."""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.drafting.backlog import FEASIBILITY, SLUG, FeatureBacklogSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.answer_schema import (
    MISSING,
    UNRESOLVED,
    check_criterion,
    check_item,
)
from algotrade.services.drafting.formulas import Normalise
from algotrade.services.drafting.parts.model import part_tag

MAX_SLUG = 64
MAX_MISSING = 5  # per answer, as are the lists below: the rest are cut, with a note
MAX_CLOSEST = 5
MAX_UNRESOLVED = 3
MAX_ALTERNATIVES = 3
MIN_ALTERNATIVES = 2


@dataclass(frozen=True)
class MissingFeature:
    """A feature requested that does not exist: ``key`` a backlog item's key, else ``None``
    with ``new_key_slug`` for a new one."""

    key: str | None
    new_key_slug: str | None
    span: str
    description: str
    why_needed: str
    closest: tuple[str, ...]
    feasibility: str
    part: str | None = None  # the part id the model tagged it with (explained parts)


@dataclass(frozen=True)
class Alternative:
    text: str  # the model's ``label``
    criterion: dict[str, Any]


@dataclass(frozen=True)
class Unresolved:
    """An ambiguous ``term`` of the sentence (``span``) with its readings; the draft carries
    the one at ``default_index``."""

    term: str
    span: str
    default_index: int
    alternatives: tuple[Alternative, ...]
    part: str | None = None  # the part id the model tagged it with (explained parts)


def missing_of(
    proposal: Mapping[str, Any],
    backlog: FeatureBacklogSettings,
    catalogue: Collection[str],
) -> tuple[tuple[MissingFeature, ...], tuple[str, ...]]:
    """The proposed ``missing`` items resolved against ``backlog`` and ``catalogue``, and the
    notes for the ones that could not be kept."""
    raw = proposal.get("missing")
    listed = raw if isinstance(raw, list) else []
    canonical = {i.key: i for i in backlog.items} | {a: i for i in backlog.items for a in i.aliases}
    out: list[MissingFeature] = []
    notes: list[str] = _cut("missing features", len(listed), MAX_MISSING)
    for n, item in enumerate(listed[:MAX_MISSING], 1):
        if (shape := check_item(item, MISSING, "missing")) is not None:
            notes.append(f"a missing-feature request was not kept ({shape})")
            continue
        known = canonical.get(_clean(item.get("key"))) or canonical.get(
            _clean(item.get("new_key_slug"))
        )  # a curated key sent as a new slug is still the curated one
        if known is not None and known.status != "OPEN":
            notes.append(f"{known.key} is {known.status} in the backlog; request not kept")
            continue
        slug = None if known else _slug(item.get("key")) or _slug(item.get("new_key_slug"))
        if known is None and not slug:
            slug = _slug(item["description"])  # model-written: never the trader's own words
        if known is None and not slug:
            notes.append(
                f"missing feature {n} has no key, slug or description to name it by; not kept"
            )
            continue
        feasibility = item["feasibility"] if item["feasibility"] in FEASIBILITY else ""
        out.append(
            MissingFeature(
                key=known.key if known else None,
                new_key_slug=slug,
                span=_clean(item["span"]),
                description=_clean(item["description"]) or (known.description if known else ""),
                why_needed=_clean(item["why_needed"]),
                closest=tuple(c for c in item["closest"] if _in_catalogue(c, catalogue))[
                    :MAX_CLOSEST
                ],
                feasibility=feasibility or (known.feasibility if known else "") or "UNCLEAR",
                part=part_tag(item),
            )
        )
    return tuple(out), tuple(notes)


def unresolved_of(
    proposal: Mapping[str, Any], catalogue: Collection[str], normalise: Normalise
) -> tuple[tuple[Unresolved, ...], tuple[str, ...]]:
    """The proposed ``unresolved`` terms with their validated alternatives, and the notes for
    what was dropped."""
    raw = proposal.get("unresolved")
    listed = raw if isinstance(raw, list) else []
    out: list[Unresolved] = []
    notes: list[str] = _cut("ambiguous terms", len(listed), MAX_UNRESOLVED)
    for n, item in enumerate(listed[:MAX_UNRESOLVED], 1):
        if (shape := check_item(item, UNRESOLVED, "unresolved")) is not None:
            notes.append(f"an ambiguous term was not kept ({shape})")
            continue
        term = _clean(item["term"]) or f"term {n}"
        alternatives: list[Alternative] = []
        default: Alternative | None = None
        notes += _cut(f"{term} alternatives", len(item["alternatives"]), MAX_ALTERNATIVES)
        for k, alt in enumerate(item["alternatives"][:MAX_ALTERNATIVES]):
            try:
                made = Alternative(_clean(alt["label"]), _alternative(alt["criterion"], normalise))
            except ConfigurationError as exc:
                notes.append(f"{term}: alternative {_clean(alt['label']) or k + 1} dropped ({exc})")
                continue
            alternatives.append(made)
            if k == item["default_index"]:
                default = made
        if len(alternatives) < MIN_ALTERNATIVES:
            notes.append(f"{term}: fewer than {MIN_ALTERNATIVES} usable alternatives; not offered")
            continue
        if default is None:
            why = (
                "was dropped"
                if 0 <= item["default_index"] < len(item["alternatives"])
                else "is out of range"
            )
            notes.append(f"{term}: the default alternative {why}; first used")
        out.append(
            Unresolved(
                term,
                _clean(item["span"]),
                alternatives.index(default) if default else 0,
                tuple(alternatives),
                part_tag(item),
            )
        )
    return tuple(out), tuple(notes)


def _cut(what: str, count: int, cap: int) -> list[str]:
    """The note that ``count - cap`` of the proposed ``what`` were cut, when any were."""
    return [f"{count - cap} {what} beyond the first {cap} were cut"] if count > cap else []


def _alternative(criterion: Mapping[str, Any], normalise: Normalise) -> dict[str, Any]:
    if (shape := check_criterion(criterion)) is not None:
        raise ConfigurationError(f"not the criterion shape ({shape})")
    field = criterion.get("field")
    return normalise(criterion, field if isinstance(field, str) else "")


def _clean(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _slug(value: Any) -> str:
    """``value`` as a backlog slug (``a-z0-9_``), or empty when nothing is left of it."""
    text = _clean(value)
    if SLUG.match(text):
        return text[:MAX_SLUG]
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:MAX_SLUG]


def _in_catalogue(name: str, catalogue: Collection[str]) -> bool:
    """A catalogue field, or a feature's bare name (as the backlog's ``closest`` writes it)."""
    return name in catalogue or f"feature.{name}" in catalogue
