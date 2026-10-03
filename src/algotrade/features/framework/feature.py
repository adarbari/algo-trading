"""The ``Feature`` declaration: one named, typed, documented column of a feature group.

A feature is what a selection, a screener or a report reads: ``<group>.<column>@v<N>``
(selectable as ``rollup.<group>@v<N>.<column>``), or a site expression feature
``<name>@v<N>`` with no group (``config/site/features/*.toml``; selectable as
``feature.<name>``, computed on read unless materialised: ``features.expressions``). Its
metadata is declared next to the compute that produces it (``features/rollups/<group>.py``)
and drives the generated feature catalogue (``docs/data/features.md``), the stored column
type and, later, UI and email labels (ADR 0023).

- ``entity``      what one row describes: ``instrument`` today (``market``, ``contract``,
                  ``sector`` are reserved for when a feature needs that grain)
- ``kind``        how it is computed: ``window`` (one entity's history up to the session:
                  bars, events, filings, earlier sessions), ``chain`` (one session's option
                  chain), ``expression`` (arithmetic / logic over other features of the same
                  row), ``cross_section`` (across entities on one session), ``label`` (a
                  status, tier or class from a fixed rule)
- ``dtype``       the stored type (``core.model.fields.FIELD_TYPES``)
- ``unit``        ``UNITS``: ``decimal`` is a fraction (0.25 = 25%), ``pct_points`` is 25 =
                  25%, ``ratio`` a plain quotient, ``sessions`` exchange sessions, ``days``
                  calendar days
- ``null_meaning``  why the value can be null (null is UNKNOWN, never zero)
- ``valid_range`` plausible ``(min, max)`` (``None``: open); values outside are kept, not
                  clipped: a range is a sanity bound for checks, not a filter
- ``categories``  the closed set of values of a label (empty: open, e.g. a free-text status)
- ``inputs``      what it is computed from: other features (``<group>.<column>@v<N>``, an
                  expression feature ``<name>@v<N>``) or raw fields (``<table>.<column>``,
                  e.g. ``bars/1d.close``)
- ``version``     the feature's definition version: a group feature's is its group's (a
                  group is re-versioned only when its stored columns change); an expression
                  feature's is its own
"""

import re
from dataclasses import dataclass
from typing import Literal

from algotrade.core.model.fields import FIELD_TYPES, NUMERIC_TYPES

type Entity = Literal["instrument"]
type Kind = Literal["window", "chain", "expression", "cross_section", "label"]
type Range = tuple[float | None, float | None]

ENTITIES = frozenset({"instrument"})
KINDS = frozenset({"window", "chain", "expression", "cross_section", "label"})
UNITS = frozenset(
    {
        "decimal",  # a fraction: 0.25 is 25% (returns, vols, yields, rates, relative spreads)
        "pct_points",  # a percentage as quoted: 25 is 25%
        "ratio",  # a plain quotient (iv / hv), or a dimensionless sensitivity (delta)
        "usd",  # US dollars (dollar volume, market cap)
        "usd_per_share",  # a price per share or per option contract unit
        "shares",  # a share count
        "count",  # how many of something (contracts, ex-dates, quotes)
        "sessions",  # exchange sessions (core.time.calendar)
        "days",  # calendar days
        "date",  # a calendar date
        "flag",  # true / false
        "category",  # one value of a set (a status, tier or class)
        "text",  # an identifier or free text
    }
)
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FEATURE_REF = re.compile(r"^([a-z][a-z0-9_]*\.)?[a-z][a-z0-9_]*@v[1-9][0-9]*$")
_RAW_REF = re.compile(r"^[a-z0-9_/]+\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Feature:
    name: str  # the stored column
    dtype: str
    unit: str
    description: str
    null_meaning: str
    kind: Kind = "window"
    valid_range: Range | None = None
    categories: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    entity: Entity = "instrument"
    version: int = 0  # 0: the group's version (set when the group is declared)
    group: str = ""  # the owning group's key (set when declared); "": an expression feature

    @property
    def key(self) -> str:
        """``<group>.<column>@v<N>`` (columns repeat across groups, so the name is
        qualified), or ``<name>@v<N>`` for an expression feature (names are unique)."""
        if not self.group:
            return f"{self.name}@v{self.version}"
        return f"{self.group.partition('@')[0]}.{self.name}@v{self.version}"

    @property
    def field(self) -> str:
        """The selection field: ``rollup.<group>@v<N>.<column>`` or ``feature.<name>``."""
        return f"rollup.{self.group}.{self.name}" if self.group else f"feature.{self.name}"


def is_feature_ref(ref: str) -> bool:
    """``<group>.<column>@v<N>`` or ``<name>@v<N>`` (otherwise a raw field
    ``<table>.<column>``)."""
    return bool(_FEATURE_REF.match(ref))


def feature_problems(feature: Feature) -> list[str]:
    """Why a feature declaration is invalid (empty: valid)."""
    f = feature
    problems = []
    if not _NAME.match(f.name):
        problems.append(f"{f.name}: name must match {_NAME.pattern}")
    if f.dtype not in FIELD_TYPES:
        problems.append(f"{f.name}: dtype must be one of {sorted(FIELD_TYPES)}")
    if f.unit not in UNITS:
        problems.append(f"{f.name}: unit {f.unit!r} must be one of {sorted(UNITS)}")
    if f.kind not in KINDS:
        problems.append(f"{f.name}: kind {f.kind!r} must be one of {sorted(KINDS)}")
    if f.entity not in ENTITIES:
        problems.append(f"{f.name}: entity {f.entity!r} must be one of {sorted(ENTITIES)}")
    if not f.description.strip() or not f.null_meaning.strip():
        problems.append(f"{f.name}: describe it and say when it is null")
    if f.valid_range is not None:
        lo, hi = f.valid_range
        if f.dtype not in NUMERIC_TYPES:
            problems.append(f"{f.name}: a valid_range needs a numeric dtype")
        elif lo is not None and hi is not None and lo > hi:
            problems.append(f"{f.name}: valid_range min > max")
    if f.categories and f.dtype != "str":
        problems.append(f"{f.name}: categories need dtype str")
    bad = [r for r in f.inputs if not (is_feature_ref(r) or _RAW_REF.match(r))]
    if bad:
        problems.append(f"{f.name}: inputs {bad} are neither <group>.<column>@vN nor table.column")
    return problems


def in_range(feature: Feature, value: float) -> bool:
    """Whether a non-null ``value`` is inside the feature's ``valid_range`` (open: True)."""
    if feature.valid_range is None:
        return True
    lo, hi = feature.valid_range
    return (lo is None or value >= lo) and (hi is None or value <= hi)
