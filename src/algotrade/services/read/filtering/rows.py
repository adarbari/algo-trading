"""``frame_of``: the frame of a list surface built from its row objects (ADR 0082 decision 3). A
surface whose rows are read objects, not stored feature rows, declares each ``column:`` in its
filter file with a ``source``: a dotted path in the row (``latest_run.status``), or
``len(path)``. This module walks the path, so a list adopts the pass with a row dataclass whose
fields are the paths' roots and no masking code of its own. A path through a tuple yields a tuple
cell (a pick holds when any element does); a value that is not known (``None``, an ``Unknown`` or
``Unavailable``, a per-name cell the viewer's licence hides, whose ``value`` is None) is missing,
never 0 and never passing; an enum is its value; ``len`` of a missing path is missing. Pure."""

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from algotrade.config.filters.definitions import FilterColumn
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.availability.cause import Unavailable
from algotrade.services.read.filtering.definitions import ResolvedFilters
from algotrade.services.read.filtering.masks import Cell, Frame
from algotrade.services.read.values import Unknown


def _plain(value: Any) -> Any:
    """``value`` as a cell value: an enum is its value, a gap is missing."""
    if isinstance(value, Unknown | Unavailable):
        return None
    return value.value if isinstance(value, Enum) else value


def _step(value: Any, name: str) -> Any:
    if value is None or isinstance(value, Unknown | Unavailable):
        return None
    if isinstance(value, tuple):
        return tuple(_step(v, name) for v in value)
    return getattr(value, name)


def cell_of(row: object, column: FilterColumn) -> Cell:
    """The value of ``column`` on ``row``."""
    found: Any = row
    for name in column.path:
        found = _step(found, name)
    if column.count:
        return None if found is None or isinstance(found, Unknown | Unavailable) else len(found)
    if isinstance(found, tuple):
        return tuple(_plain(v) for v in found)
    return _plain(found)  # type: ignore[no-any-return]


def frame_of(
    rows: Sequence[object],
    resolved: ResolvedFilters,
    columns: Sequence[FilterColumn],
    catalogue: Mapping[str, Sequence[Cell]] | None = None,
) -> Frame:
    """The columns every offered filter reads over ``rows``, by the filter's ``field``: the
    surface's own columns from the rows, a catalogue field from ``catalogue`` (the caller reads
    it in one batch under the viewer's licences)."""
    declared = {c.id: c for c in columns}
    frame: dict[str, Sequence[Cell]] = {}
    for f in resolved.offered:
        if f.column_id is None:
            if catalogue is None or f.field not in catalogue:
                raise ConfigurationError(
                    f"filters/{resolved.surface}.toml: no values for {f.field}"
                )
            frame[f.field] = catalogue[f.field]
        elif f.column_id not in declared:
            raise ConfigurationError(f"filters/{resolved.surface}.toml: no column {f.column_id!r}")
        else:
            column = declared[f.column_id]
            frame[f.field] = [cell_of(r, column) for r in rows]
    return frame
