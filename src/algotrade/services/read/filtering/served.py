"""``load_served_filters``: a surface's filters as the viewer is served them (``filterSet``, ADR
0082 decision 2). The definitions are resolved against the SITE catalogue (a viewer's own
expression cannot take a site name) and the viewer's data licences; a filter the viewer may not
use is not dropped from the answer but listed as ``Unavailable`` (``LICENCE``, or ``NOT_STORED``
when the catalogue does not resolve its field) so a screen can say why it is missing, and it is
refused if sent (``ResolvedFilters.check``). Session-free: a definition does not depend on the
session."""

import importlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.config.filters.definitions import FilterDefinition, load_filter_set
from algotrade.config.site.settings import load_users
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.licences import held_by, licence_of
from algotrade.services.read.availability.cause import (
    Unavailable,
    UnavailableKind,
    feature_cause,
)
from algotrade.services.read.context import NotFoundError, Stores
from algotrade.services.read.filtering.definitions import ResolvedFilters, resolve_definitions
from algotrade.services.read.filtering.masks import WindowUnit


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


@dataclass(frozen=True)
class ServedOption:
    """One value a pick or select offers."""

    value: str
    label: str


@dataclass(frozen=True)
class ServedFilter:
    """An offered filter. ``options``: the definition's static values or the members of its
    ``enum`` (empty for ``values``: the stored ones, counted in each result's facets); ``bins``:
    a range's histogram edges; ``window_unit``: what a window counts."""

    id: str
    label: str
    group: FilterGroup
    kind: FilterKind
    guide: str
    options: tuple[ServedOption, ...]
    bins: tuple[float, ...]
    window_unit: WindowUnit | None


@dataclass(frozen=True)
class WithheldFilter:
    """A filter of the surface the viewer is not offered, and why in public words."""

    id: str
    label: str
    group: FilterGroup
    unavailable: Unavailable


@dataclass(frozen=True)
class ServedFilters:
    """``filters``: what the viewer may use (``resolved``: the same, as the pass takes them);
    ``withheld``: the rest, in file order."""

    surface: str
    label: str
    resolved: ResolvedFilters
    filters: tuple[ServedFilter, ...]
    withheld: tuple[WithheldFilter, ...]


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
        f.id, f.label, FilterGroup(f.group), FilterKind(f.kind), f.guide, _options(f), f.bins, unit
    )


def _why(definition: FilterDefinition, site: FeatureSet, day: date | None) -> Unavailable:
    field = definition.field
    if site.feature(field) is None:
        kind, detail = UnavailableKind.NOT_STORED, f"{field} is not in the catalogue"
    else:
        kind = UnavailableKind.LICENCE
        held = licence_of(site, field)
        detail = f"{field} is under the {held} data licence, which the user does not hold"
    return Unavailable(kind, (field,), feature_cause(field, detail, kind.value, day))


def load_served_filters(ctx: Stores, surface: str, day: date | None = None) -> ServedFilters:
    """``surface``'s filters for ``ctx``'s user. ``NotFoundError`` for a surface with no file."""
    filter_set = load_filter_set(ctx.configs, surface)
    if not filter_set.filters and not filter_set.columns:
        raise NotFoundError(f"filters: no surface {surface!r}")
    site = site_catalogue(ctx)
    held = held_by(load_users(ctx.configs), ctx.user.user_id)
    resolved = resolve_definitions(filter_set, site, held)
    withheld = tuple(
        WithheldFilter(f.id, f.label, FilterGroup(f.group), _why(f, site, day))
        for f in filter_set.filters
        if f.id in resolved.withheld
    )
    offered = tuple(_served(f) for f in resolved.offered)
    return ServedFilters(surface, filter_set.label, resolved, offered, withheld)
