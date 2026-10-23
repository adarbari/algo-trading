"""``FilterSet``: the filters of one surface (a table, list or feed) from
``config/site/filters/<surface>.toml`` (ADR 0082 decision 1), typed and shape-checked. Site only,
fail closed: an unknown key, a wrong type or a kind's missing part names the file. A filter's
``field`` is a catalogue name (``rollup.<group>@v<N>.<name>`` or ``feature.<name>``) or
``column:<id>``, a column the file declares for the surface (``[[column]]``: ``id``, ``dtype``,
``source``, where in the read object the value comes from). That the names exist in the
catalogue, the kind fits the dtype and the Guide entry is written are fitness tests over the
shipped files (they need the catalogue); a licence is never declared here: it is derived per
viewer (ADR 0069)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Protocol

from algotrade.config.site.fields import Table, unique
from algotrade.core.model.errors import ConfigurationError

KIND = "filters"
GROUPS = ("setup", "changed", "tradeable", "coming_up", "more")
KINDS = ("pick", "select", "toggle", "range", "window", "percentile")
OPTIONS = ("static", "values", "enum")
WINDOW_UNITS = ("days", "sessions")
DTYPES = ("str", "int", "float", "bool", "date")
COLUMN = "column:"  # a ``field`` that names a column of the surface, not a catalogue feature
GUIDE_KINDS = ("term", "field", "situation", "start")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")  # also a key of the URL parameter ``f``
_ENUM = re.compile(r"^[a-z_][a-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")  # module:Name
_REF = re.compile(r"^[a-z_]+:[a-z0-9_]+$")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class FilterOption:
    """One offered value of a ``static`` pick / select."""

    value: str
    label: str


@dataclass(frozen=True)
class FilterColumn:
    """A column of the surface a filter may name as ``column:<id>``; ``source`` is the dotted
    path in the surface's read object (``best.decision``)."""

    id: str
    dtype: str
    source: str


@dataclass(frozen=True)
class FilterDefinition:
    """One filter. ``options``: how a pick / select gets its values (``static`` lists them,
    ``values`` are the ones stored for the session, ``enum`` names ``module:Name``); ``bins``:
    a range's fixed histogram edges; ``window_unit``: what a window counts; ``guide``: the
    entry that explains it (``<kind>:<id>``)."""

    id: str
    label: str
    group: str
    kind: str
    field: str
    guide: str
    options: str | None = None
    static: tuple[FilterOption, ...] = ()
    enum: str | None = None
    bins: tuple[float, ...] = ()
    window_unit: str | None = None

    @property
    def column_id(self) -> str | None:
        """The surface column the filter reads, None for a catalogue field."""
        return self.field.removeprefix(COLUMN) if self.field.startswith(COLUMN) else None


@dataclass(frozen=True)
class FilterSet:
    """A surface's filters in file order (the order a group lists them) and its columns."""

    surface: str
    label: str
    columns: tuple[FilterColumn, ...]
    filters: tuple[FilterDefinition, ...]

    def get(self, filter_id: str) -> FilterDefinition | None:
        return next((f for f in self.filters if f.id == filter_id), None)

    def in_group(self, group: str) -> tuple[FilterDefinition, ...]:
        return tuple(f for f in self.filters if f.group == group)


def _column(t: Table) -> FilterColumn:
    t.only(("id", "dtype", "source"))
    return FilterColumn(_id(t), t.choice("dtype", "", DTYPES), t.line("source"))


def _id(t: Table) -> str:
    value = t.line("id")
    if not _ID.match(value):
        raise ConfigurationError(f"{t.where} id: expected snake_case (a-z, 0-9, _), got {value!r}")
    return value


def _bins(t: Table) -> tuple[float, ...]:
    raw = t.raw("bins")
    if raw is None:
        return ()
    ok = isinstance(raw, list) and all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in raw
    )
    if not ok or len(raw) < 2 or any(a >= b for a, b in pairwise(raw)):
        raise ConfigurationError(f"{t.where} bins: expected two or more numbers, ascending")
    return tuple(float(v) for v in raw)


def _filter(t: Table) -> FilterDefinition:
    t.only(("id", "label", "group", "kind", "field", "guide", "options", "enum", "bins",
            "window_unit", "option"))  # fmt: skip
    kind = t.choice("kind", "", KINDS)
    options = t.choice("options", "", OPTIONS) if t.raw("options") is not None else None
    static = tuple(_option(o) for o in t.tables("option"))
    enum = t.line("enum") if t.raw("enum") is not None else None
    bins = _bins(t)
    unit = t.choice("window_unit", "", WINDOW_UNITS) if t.raw("window_unit") is not None else None
    guide = t.line("guide")
    if not _REF.match(guide) or guide.split(":")[0] not in GUIDE_KINDS:
        raise ConfigurationError(f"{t.where} guide: expected <kind>:<id> of {GUIDE_KINDS}")
    field = t.line("field")
    if field.startswith(COLUMN) and not _ID.match(field[len(COLUMN) :]):
        raise ConfigurationError(f"{t.where} field: a column id is snake_case, got {field!r}")
    _check_kind(t, kind, options, static, enum, bins, unit)
    return FilterDefinition(
        _id(t), t.line("label"), t.choice("group", "", GROUPS), kind, field, guide,
        options, static, enum, bins, unit,
    )  # fmt: skip


def _option(t: Table) -> FilterOption:
    t.only(("value", "label"))
    return FilterOption(t.line("value"), t.line("label"))


def _check_kind(
    t: Table,
    kind: str,
    options: str | None,
    static: tuple[FilterOption, ...],
    enum: str | None,
    bins: tuple[float, ...],
    unit: str | None,
) -> None:
    """Each kind has its own parts: a pick / select its options, a range its bins, a window its
    unit; nothing carries a part of another kind."""
    listed = kind in ("pick", "select")
    if listed != (options is not None):
        raise ConfigurationError(
            f"{t.where} options: required on pick and select and on no other kind (got {kind})"
        )
    if bool(static) != (options == "static"):
        raise ConfigurationError(f'{t.where} option: [[option]] only with options = "static"')
    if options == "static":
        unique(t.where, "option values", (o.value for o in static))
    if (enum is not None) != (options == "enum") or (enum and not _ENUM.match(enum)):
        raise ConfigurationError(f'{t.where} enum: module:Name, only with options = "enum"')
    if bool(bins) != (kind == "range"):
        raise ConfigurationError(f"{t.where} bins: required on a range and on no other kind")
    if (unit is not None) != (kind == "window"):
        raise ConfigurationError(
            f"{t.where} window_unit: required on a window and on no other kind"
        )


def parse_filter_set(surface: str, doc: Mapping[str, Any] | None) -> FilterSet:
    """The document, typed; a missing file is a surface with no filters."""
    where = f"filters/{surface}.toml"
    t = Table(doc, where)
    t.only(("label", "column", "filter"))
    columns = tuple(_column(c) for c in t.tables("column"))
    filters = tuple(_filter(f) for f in t.tables("filter"))
    unique(where, "column ids", (c.id for c in columns))
    unique(where, "filter ids", (f.id for f in filters))
    declared = {c.id for c in columns}
    for f in filters:
        if f.column_id is not None and f.column_id not in declared:
            raise ConfigurationError(f"{where} filter {f.id} field: no [[column]] {f.column_id!r}")
    return FilterSet(surface, t.line("label") if doc else surface, columns, filters)


def load_filter_set(configs: Documents, surface: str) -> FilterSet:
    """A surface's filters (``config/site/filters/<surface>.toml``)."""
    return parse_filter_set(surface, configs.load("site", KIND, surface))
