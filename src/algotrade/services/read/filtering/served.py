"""``load_served_filters``: a surface's filters as the viewer is served them (``filterSet``, ADR
0082 decision 2). The definitions are resolved against the SITE catalogue (a viewer's own
expression cannot take a site name) and the viewer's data licences; a filter the viewer may not
use is not dropped from the answer but listed as ``Unavailable`` (``LICENCE``, or ``NOT_STORED``
when the catalogue does not resolve its field) so a screen can say why it is missing, and it is
refused if sent (``ResolvedFilters.check``). Session-free: a definition does not depend on the
session."""

import importlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.config.filters.definitions import (
    FilterColumn,
    FilterDefinition,
    FilterSet,
    load_filter_set,
)
from algotrade.config.site.settings import load_phrasebook, load_users
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.licences import held_by, licence_of
from algotrade.services.read.availability.cause import (
    Unavailable,
    UnavailableKind,
    feature_cause,
)
from algotrade.services.read.context import NotFoundError, ReadContext, Stores
from algotrade.services.read.filtering.definitions import ResolvedFilters, resolve_definitions
from algotrade.services.read.filtering.feature_filters import (
    FilterableFeature,
    feature_filter_id,
    filterable_features,
    picked_feature_filters,
    requested_fields,
    takes_features,
)
from algotrade.services.read.filtering.masks import WindowUnit
from algotrade.services.read.filtering.no_data import fields_without_data

NO_DATA_TERM = "term:filter_withheld_no_data"


class FilterGroup(StrEnum):
    """Where a filter sits in the filter bar (the definition's ``group``)."""

    SETUP = "setup"
    CHANGED = "changed"
    TRADEABLE = "tradeable"
    COMING_UP = "coming_up"
    MORE = "more"


class FilterKind(StrEnum):
    """The control a filter is (the definition's ``kind``)."""

    PICK = "pick"
    SELECT = "select"
    TOGGLE = "toggle"
    RANGE = "range"
    WINDOW = "window"
    PERCENTILE = "percentile"


class ValueUnit(StrEnum):
    """How a range shows its stored value (the definition's ``unit``)."""

    PERCENT = "percent"


@dataclass(frozen=True)
class ServedOption:
    """One value a pick or select offers."""

    value: str
    label: str


@dataclass(frozen=True)
class ServedFilter:
    """An offered filter. ``options``: the definition's static values or the members of its
    ``enum`` (empty for ``values``: the stored ones, counted in each result's facets); ``bins``:
    a range's histogram edges; ``window_unit``: what a window counts; ``unit``: how a range shows
    its value (``percent``: shown as 0..100, sent as 0..1)."""

    id: str
    label: str
    group: FilterGroup
    kind: FilterKind
    guide: str
    options: tuple[ServedOption, ...]
    bins: tuple[float, ...]
    window_unit: WindowUnit | None
    unit: ValueUnit | None = None


@dataclass(frozen=True)
class WithheldFilter:
    """A filter of the surface the viewer is not offered, and why in public words."""

    id: str
    label: str
    group: FilterGroup
    unavailable: Unavailable
    guide: str | None = None  # the entry that says why, when the kind's own term is too generic


@dataclass(frozen=True)
class ServedFilters:
    """``filters``: what the viewer may use (``resolved``: the same, as the pass takes them);
    ``withheld``: the rest, in file order; ``columns``: the surface's declared columns (the
    sources a list builds its frame from, ``filtering/rows.py``)."""

    surface: str
    label: str
    resolved: ResolvedFilters
    filters: tuple[ServedFilter, ...]
    withheld: tuple[WithheldFilter, ...]
    columns: tuple[FilterColumn, ...] = ()
    searchable: bool = False


def site_catalogue(ctx: Stores) -> FeatureSet:
    """The site's catalogue, computed once per context (a viewer's own names never join it)."""
    site: FeatureSet = ctx.cache.get_or_compute(("site_catalogue",), lambda: catalogue(ctx.configs))
    return site


def _options(definition: FilterDefinition) -> tuple[ServedOption, ...]:
    """The options of a filter: its ``static`` list, or the values of ``module:Name``."""
    if definition.enum is None:
        return tuple(ServedOption(o.value, o.label) for o in definition.static)
    module, _, name = definition.enum.partition(":")
    members = importlib.import_module(module).__dict__[name]
    return tuple(ServedOption(str(m.value), str(m.value)) for m in members)


def _served(f: FilterDefinition) -> ServedFilter:
    unit = WindowUnit(f.window_unit) if f.window_unit else None
    return ServedFilter(
        f.id,
        f.label,
        FilterGroup(f.group),
        FilterKind(f.kind),
        f.guide,
        _options(f),
        f.bins,
        unit,
        ValueUnit(f.unit) if f.unit else None,
    )


def _without_data(
    ctx: Stores, filters: Iterable[FilterDefinition], offered: Iterable[str]
) -> frozenset[str]:
    """The ids of the offered catalogue-field filters no instrument has a known value for in the
    read session (a context with no session has nothing to look at). They are only left out of
    what ``filterSet`` serves as controls: an input naming one is still read by the lists (never
    refused, so a shared link opens), and as UNKNOWN never passes it matches nothing and the gap
    is disclosed as before; a screen echoes it switched off (``active`` false: in no mask)."""
    if not isinstance(ctx, ReadContext):
        return frozenset()
    live = set(offered)
    wanted = [f for f in filters if f.column_id is None and f.id in live]
    empty = fields_without_data(ctx, [f.field for f in wanted])
    return frozenset(f.id for f in wanted if f.field in empty)


def _why(
    definition: FilterDefinition, site: FeatureSet, day: date | None, no_data: bool = False
) -> Unavailable:
    field = definition.field
    if no_data:
        detail = f"no known value for session {day}"
        return Unavailable(
            UnavailableKind.NOT_STORED, (field,), feature_cause(field, detail, "NOT_STORED", day)
        )
    if site.feature(field) is None:
        kind, detail = UnavailableKind.NOT_STORED, f"{field} is not in the catalogue"
    else:
        kind = UnavailableKind.LICENCE
        held = licence_of(site, field)
        detail = f"{field} is under the {held} data licence, which the user does not hold"
    return Unavailable(kind, (field,), feature_cause(field, detail, kind.value, day))


@dataclass(frozen=True)
class ListFilters:
    """What a list reads of a surface's filters: ``resolved`` (the pass's definitions) and
    ``columns`` (the declared columns). No no-data check: only ``filterSet`` offers controls."""

    resolved: ResolvedFilters
    columns: tuple[FilterColumn, ...]


def _resolve(
    ctx: Stores, surface: str, wanted: Iterable[str]
) -> tuple[FilterSet, FeatureSet, ResolvedFilters, tuple[FilterDefinition, ...]]:
    """The surface's file, the site catalogue, the filters resolved for ``ctx``'s user and the
    picked feature filters it may not use (``wanted``: see ``load_served_filters``).
    ``NotFoundError`` for a surface with no file."""
    filter_set = load_filter_set(ctx.configs, surface)
    if not filter_set.filters and not filter_set.columns:
        raise NotFoundError(f"filters: no surface {surface!r}")
    site = site_catalogue(ctx)
    held = held_by(load_users(ctx.configs), ctx.user.user_id)
    resolved = resolve_definitions(filter_set, site, held)
    extra_on, extra_off = (
        picked_feature_filters(site, held, requested_fields(wanted))
        if takes_features(filter_set)
        else ((), ())
    )
    if extra_on or extra_off:
        resolved = ResolvedFilters(
            surface,
            (*resolved.offered, *extra_on),
            resolved.withheld | {f.id for f in extra_off},
        )
    return filter_set, site, resolved, tuple(extra_off)


def load_list_filters(ctx: Stores, surface: str, wanted: Iterable[str] = ()) -> ListFilters:
    """``resolved`` and ``columns`` of ``load_served_filters``, without its no-data check (a
    full read of the surface's fields, whose result only ``filterSet`` uses): every list, table,
    export and trade read takes its filters here."""
    filter_set, _, resolved, _ = _resolve(ctx, surface, wanted)
    return ListFilters(resolved, filter_set.columns)


def load_served_filters(
    ctx: Stores, surface: str, day: date | None = None, wanted: Iterable[str] = ()
) -> ServedFilters:
    """``surface``'s filters for ``ctx``'s user. ``NotFoundError`` for a surface with no file.
    ``wanted``: the filter ids of the request; each ``feature:<field>`` one is offered too when
    the surface takes features and the viewer's licences cover the field (else it is withheld, or
    left for ``check`` to refuse), ``feature_filters.py``. Runs the no-data check: only
    ``filterSet`` calls it (guarded by ``tests/unit/services/read/filtering/test_served.py``);
    lists use ``load_list_filters``."""
    filter_set, site, resolved, extra_off = _resolve(ctx, surface, wanted)
    stale = _without_data(ctx, filter_set.filters, (f.id for f in resolved.offered))
    withheld = tuple(
        WithheldFilter(
            f.id,
            f.label,
            FilterGroup(f.group),
            _why(f, site, day, f.id in stale),
            NO_DATA_TERM if f.id in stale else None,
        )
        for f in (*filter_set.filters, *extra_off)
        if f.id in resolved.withheld or f.id in stale
    )
    offered = tuple(_served(f) for f in resolved.offered if f.id not in stale)
    return ServedFilters(
        surface,
        filter_set.label,
        resolved,
        offered,
        withheld,
        filter_set.columns,
        takes_features(filter_set),
    )


def load_filter_set_with(
    ctx: Stores, surface: str, fields: Iterable[str] | None = None
) -> ServedFilters:
    """``surface``'s filters plus the ones made of the catalogue ``fields`` (``filterSet``'s
    ``withFeatures``), each served when the surface takes features and the licences cover it."""
    day = ctx.session.date if isinstance(ctx, ReadContext) else None
    return load_served_filters(ctx, surface, day, [feature_filter_id(f) for f in fields or ()])


def load_filterable_features(ctx: Stores, surface: str) -> tuple[FilterableFeature, ...]:
    """The catalogue fields the user may filter ``surface`` on by search (``More filters``): none
    for a surface that takes no features; a field their data licences do not cover never appears.
    """
    filter_set = load_filter_set(ctx.configs, surface)
    if not takes_features(filter_set):
        return ()
    held = held_by(load_users(ctx.configs), ctx.user.user_id)
    phrases = load_phrasebook(ctx.configs).phrases
    return filterable_features(site_catalogue(ctx), held, phrases)
