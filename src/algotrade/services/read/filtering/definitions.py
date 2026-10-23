"""``resolve_definitions``: which of a surface's filters a viewer is offered (ADR 0082 decision 2).
A filter on a catalogue field is offered only when the catalogue resolves the field and the
viewer's licences cover it (``services/licences``: a field the viewer may not see is neither
offered nor accepted, so a count never leaks a withheld value, ADR 0069); a filter on a column
of the surface is offered (the loader that builds the column applies the licence of what it
reads). ``ResolvedFilters.check`` refuses an input that names a filter that is not offered.

Contract for the caller (the loader that adopts this): pass the SITE catalogue (a viewer's own
expression must not take a site name) and, for a surface built from stored runs, a catalogue
whose names have already gone through ``hidden_stored`` (ADR 0069 decision 3); and build each
``column:`` of the frame itself under the licence of what it reads, because a column is offered
here without a licence check and its counts would show whatever the frame holds."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from algotrade.config.filters.definitions import FilterDefinition, FilterSet
from algotrade.core.model.errors import PermissionDeniedError
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.licences import hidden_fields


class FilterRefusedError(PermissionDeniedError):
    """An input names a filter the viewer is not offered (unknown here, or its field is covered
    by a licence they do not hold)."""


@dataclass(frozen=True)
class ResolvedFilters:
    """``offered``: the filters of the surface the viewer may use, in file order; ``withheld``:
    the ids left out because of a licence or a field the catalogue does not resolve."""

    surface: str
    offered: tuple[FilterDefinition, ...]
    withheld: frozenset[str] = frozenset()

    def get(self, filter_id: str) -> FilterDefinition | None:
        return next((f for f in self.offered if f.id == filter_id), None)

    def check(self, ids: Iterable[str]) -> None:
        """Raises ``FilterRefusedError`` for the first id that is not offered."""
        for filter_id in ids:
            if self.get(filter_id) is None:
                raise FilterRefusedError(f"{self.surface}: filter {filter_id!r} is not offered")


def resolve_definitions(
    filter_set: FilterSet, features: FeatureSet, held: Collection[str]
) -> ResolvedFilters:
    """``filter_set`` against the catalogue ``features`` and the licences ``held``."""
    catalogue = [f for f in filter_set.filters if f.column_id is None]
    hidden = hidden_fields(features, (f.field for f in catalogue), held)
    unresolved = {f.field for f in catalogue if features.feature(f.field) is None}
    out = {f.id for f in catalogue if f.field in hidden or f.field in unresolved}
    offered = tuple(f for f in filter_set.filters if f.id not in out)
    return ResolvedFilters(filter_set.surface, offered, frozenset(out))
