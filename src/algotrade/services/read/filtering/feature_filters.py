"""Filters on any catalogue feature, made on the fly (ADR 0082, "More filters"): the id
``feature:<field>`` (a catalogue field: ``rollup.<group>@v<N>.<column>`` or ``feature.<name>``)
names a filter the surface's file does not declare. Its kind comes from the field's dtype (a
number is a range, a flag a toggle, a label a pick; a date is not offered), its group is
``more``, its Guide entry the field's own (``field:<name>``); a range's bin edges are chosen from
the values by ``nice_edges`` (``facets.py``) because no file fixed them, and a fraction (unit
``decimal``) is shown as a percent. The licence gate is the same as for a declared filter
(``hidden_fields``): a field the viewer's licences do not cover is not offered, not searchable and
refused if sent. Only a surface whose rows are instruments takes them (``takes_features``: it
declares at least one catalogue-field filter, so its loader reads a catalogue batch). Pure."""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from algotrade.config.filters.definitions import (
    FilterDefinition,
    FilterOption,
    FilterSet,
)
from algotrade.config.site.llm import Phrase
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.configs import catalog_of
from algotrade.services.licences import hidden_fields

FEATURE_PREFIX = "feature:"
GROUP = "more"
_NUMERIC = frozenset({"float", "float32", "int"})
_KIND = {"bool": "toggle", "str": "pick", **dict.fromkeys(_NUMERIC, "range")}


@dataclass(frozen=True)
class FilterableFeature:
    """A catalogue field the viewer may filter on: its ``kind`` and ``label``, the Guide entry
    that explains it and the words a trader uses for it (the phrasebook's ``say`` of every phrase
    naming the field)."""

    name: str
    label: str
    kind: str
    guide: str
    synonyms: tuple[str, ...]


def feature_filter_id(field: str) -> str:
    return f"{FEATURE_PREFIX}{field}"


def takes_features(filter_set: FilterSet) -> bool:
    """Whether the surface's rows are instruments with a catalogue batch read: it declares a
    filter on a catalogue field (not only on columns of its own read objects)."""
    return any(f.column_id is None for f in filter_set.filters)


def _label(field: str) -> str:
    return field.rpartition(".")[2].replace("_", " ")


def feature_definition(
    features: FeatureSet, field: str, dtypes: Mapping[str, str] | None = None
) -> FilterDefinition | None:
    """The filter ``feature:<field>`` makes, None for a field the catalogue does not have or
    whose type no control fits (``dtypes``: the catalogue's field types, when the caller has
    them). The licence is the caller's (``hidden_fields``)."""
    feature = features.feature(field)
    kind = _KIND.get((dtypes if dtypes is not None else catalog_of(features).fields).get(field, ""))
    if feature is None or kind is None:
        return None
    categories = tuple(FilterOption(c, c) for c in feature.categories)
    return FilterDefinition(
        id=feature_filter_id(field),
        label=_label(field),
        group=GROUP,
        kind=kind,
        field=field,
        guide=f"field:{field}",
        options=("static" if categories else "values") if kind == "pick" else None,
        static=categories if kind == "pick" else (),
        unit="percent" if kind == "range" and feature.unit == "decimal" else None,
    )


def requested_fields(ids: Iterable[str]) -> tuple[str, ...]:
    """The catalogue fields the ids ``feature:<field>`` name, in order, once each."""
    return tuple(
        dict.fromkeys(i.removeprefix(FEATURE_PREFIX) for i in ids if i.startswith(FEATURE_PREFIX))
    )


def picked_feature_filters(
    features: FeatureSet, held: Collection[str], fields: Iterable[str]
) -> tuple[tuple[FilterDefinition, ...], tuple[FilterDefinition, ...]]:
    """``(offered, withheld)`` for the requested ``fields``: a field with no control or not in
    the catalogue is in neither (its input is refused as not offered); one the viewer's licences
    do not cover is withheld."""
    wanted = tuple(dict.fromkeys(fields))
    hidden = hidden_fields(features, wanted, held)
    dtypes = catalog_of(features).fields if wanted else {}
    made = [(f, feature_definition(features, f, dtypes)) for f in wanted]
    return (
        tuple(d for f, d in made if d is not None and f not in hidden),
        tuple(d for f, d in made if d is not None and f in hidden),
    )


def filterable_features(
    features: FeatureSet, held: Collection[str], phrases: Sequence[Phrase] = ()
) -> tuple[FilterableFeature, ...]:
    """Every catalogue field the viewer may filter on, in catalogue order (a hidden field never
    appears), with the phrasebook's wording for it."""
    said: dict[str, list[str]] = {}
    for phrase in phrases:
        for field in phrase.fields:
            said.setdefault(field, []).extend(phrase.say)
    dtypes = catalog_of(features).fields
    names = tuple(dtypes)
    hidden = hidden_fields(features, names, held)
    out: list[FilterableFeature] = []
    for name in names:
        if name in hidden:
            continue
        definition = feature_definition(features, name, dtypes)
        if definition is not None:
            out.append(
                FilterableFeature(
                    name,
                    definition.label,
                    definition.kind,
                    definition.guide,
                    tuple(dict.fromkeys(said.get(name, ()))),
                )
            )
    return tuple(out)
