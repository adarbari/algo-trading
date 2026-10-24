"""``FilterSet`` (``Query.filterSet(surface)``): a surface's filter definitions as the viewer is
served them (ADR 0082 decision 1): what each filter is, and the filters the viewer may not use
as ``Unavailable`` (a licence), never dropped silently."""

from typing import Self

import strawberry

from algotrade.services.read.filtering import served
from algotrade.services.read.filtering.masks import WindowUnit
from algotrade_api.graphql.types.availability import Unavailable

strawberry.enum(served.FilterGroup, description="Where a filter sits in the filter bar")
strawberry.enum(served.ValueUnit, description="How a range shows its stored value")
strawberry.enum(served.FilterKind, description="The control a filter is: how its input is read")


@strawberry.type(description="One value a pick or select offers")
class FilterChoice:
    value: str
    label: str

    @classmethod
    def of(cls, d: served.ServedOption) -> Self:
        return cls(value=d.value, label=d.label)


@strawberry.type(
    description="One filter of a surface: `guide` is its Guide entry reference (`term:<id>`); "
    "`options` the values of a static or enum pick / select (empty: the stored ones, counted in "
    "the result's facets); `bins` a range's histogram edges; `windowUnit` what a window counts; "
    "`unit` PERCENT: a range's stored 0..1 value is shown and entered as 0..100, "
    "its limits are sent as 0..1"
)
class FilterDefinition:
    id: str
    label: str
    group: served.FilterGroup
    kind: served.FilterKind
    guide: str
    options: list[FilterChoice]
    bins: list[float]
    window_unit: WindowUnit | None
    unit: served.ValueUnit | None

    @classmethod
    def of(cls, d: served.ServedFilter) -> Self:
        return cls(
            id=d.id,
            label=d.label,
            group=d.group,
            kind=d.kind,
            guide=d.guide,
            options=[FilterChoice.of(o) for o in d.options],
            bins=list(d.bins),
            window_unit=d.window_unit,
            unit=d.unit,
        )


@strawberry.type(
    description="A filter the viewer is not offered (a field under a data licence they do not "
    "hold, `unavailable.kind` LICENCE) and is refused if they send it"
)
class WithheldFilter:
    id: str
    label: str
    group: served.FilterGroup
    unavailable: Unavailable

    @classmethod
    def of(cls, d: served.WithheldFilter) -> Self:
        return cls(id=d.id, label=d.label, group=d.group, unavailable=Unavailable.of(d.unavailable))


@strawberry.type(
    description="The filters of a surface for the viewer: `filters` they may use, in the order "
    "a group lists them, and `withheld` the ones they may not"
)
class FilterSet:
    surface: str
    label: str
    filters: list[FilterDefinition]
    withheld: list[WithheldFilter]

    @classmethod
    def of(cls, d: served.ServedFilters) -> Self:
        return cls(
            surface=d.surface,
            label=d.label,
            filters=[FilterDefinition.of(f) for f in d.filters],
            withheld=[WithheldFilter.of(w) for w in d.withheld],
        )
