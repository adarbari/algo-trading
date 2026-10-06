"""The ``FeatureGroup`` declaration: features computed and stored together, what they read,
their parameters and the pure ``compute``.

A group is ``<name>@v<N>``, stored as ``rollups/instrument/<name>@v<N>`` with one row per
instrument per session (today's groups are the rollups), or, with ``entity = "market"``, as
``rollups/market/<name>@v<N>`` with one ``MKT:US`` row per session (ADR 0047; the runner
checks it). It declares its features
(``framework.feature.Feature``: one typed, documented column each) and everything else is
derived from the declaration: the selection catalogue (``rollup.<name>@v<N>.<column>``), the
stored column types (``framework.columns``), the ``rollups.toml`` section (``params``), the
inputs the runner loads (through ``data.feature_inputs``) and the feature catalogue.

``compute(inputs, session, params)`` is pure: ``inputs`` maps each declared input table to
its frame for the session (rows on or before the session only, ``None`` when an optional
input has nothing), and it returns ``instrument_id`` plus the declared feature columns (a
market group: one row, ``instrument_id = market_id("US")``).

A group is re-versioned only when its stored columns change (a new column, a changed
definition or window); each feature records its own version, equal to the group's for now.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, is_dataclass, replace
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.fields import group_of_table, rollup_table
from algotrade.features.framework.feature import AppliesTo, Entity, Feature, feature_problems

type Inputs = Mapping[str, pd.DataFrame | None]
type Compute = Callable[[Inputs, date, Any], pd.DataFrame]
type Lookback = int | Callable[[Any], int]

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED = frozenset({"instrument_id", "session_date", "knowledge_ts", "source", "run_id"})


@dataclass(frozen=True)
class Input:
    """One input table. ``lookback``: earlier exchange sessions also needed (an int, or a
    function of the params). ``required``: without data for the session the group has
    nothing to compute (the runner reports NO_INPUT instead of calling ``compute``).
    ``ids``: only these instruments of a table read by id (``macro/series``: the group's
    series, ``MACRO:<KEY>`` / ``IDX:<KEY>``); empty: all of them."""

    table: str
    lookback: Lookback = 0
    required: bool = True
    ids: tuple[str, ...] = ()

    def sessions_back(self, params: Any) -> int:
        n = self.lookback(params) if callable(self.lookback) else self.lookback
        if n < 0:
            raise ValueError(f"{self.table}: lookback must be >= 0, got {n}")
        return n


def column_types(features: tuple[Feature, ...]) -> dict[str, str]:
    """``{column: dtype}`` in declared order (the stored column order)."""
    return {f.name: f.dtype for f in features}


@dataclass(frozen=True)
class FeatureGroup:
    name: str
    version: int
    description: str
    inputs: tuple[Input, ...]
    features: tuple[Feature, ...]
    compute: Compute = field(repr=False)
    # A frozen dataclass of default parameters (scalar fields are rollups.toml keys), or
    # ``None``: the group takes no parameters.
    params: Any = None
    # Which instruments the group's features are defined for (``Feature.applies_to``); a
    # feature's own non-"any" value wins.
    applies_to: AppliesTo = "any"
    # What one row describes (``Feature.entity``), inherited by its features: ``instrument``
    # (``rollups/instrument/``) or ``market`` (``rollups/market/``, ADR 0047).
    entity: Entity = "instrument"

    def __post_init__(self) -> None:
        owned = tuple(
            replace(
                f,
                version=f.version or self.version,
                group=self.key,
                applies_to=f.applies_to if f.applies_to != "any" else self.applies_to,
                entity=f.entity if f.entity != "instrument" else self.entity,
            )
            for f in self.features
        )
        object.__setattr__(self, "features", owned)
        problems = declaration_problems(self)
        if problems:
            raise ValueError(f"feature group {self.key}: {'; '.join(problems)}")

    @property
    def key(self) -> str:
        return f"{self.name}@v{self.version}"

    @property
    def table(self) -> str:
        return rollup_table(self.entity, self.key)

    @property
    def columns(self) -> Mapping[str, str]:
        """Output column -> field type, in declared order."""
        return column_types(self.features)

    def feature(self, column: str) -> Feature:
        return next(f for f in self.features if f.name == column)


@dataclass(frozen=True)
class Superseded:
    """A group version replaced in ADR 0023 step 3. ``by``: the group whose stored sessions
    must cover the old table's before it is retired (and where its columns live, unless an
    expression feature of the same name took one); ``fields``: other moves (old column ->
    new field; ``""``: retired without a replacement)."""

    by: str
    fields: Mapping[str, str] = field(default_factory=dict)


def declaration_problems(group: FeatureGroup) -> list[str]:
    """Why a declaration is invalid (empty: valid)."""
    problems = []
    if not _NAME.match(group.name):
        problems.append(f"name must match {_NAME.pattern}")
    if group.version < 1:
        problems.append("version must be >= 1")
    if not group.inputs:
        problems.append("declare at least one input")
    if len({i.table for i in group.inputs}) != len(group.inputs):
        problems.append("inputs are declared twice")
    if not group.features:
        problems.append("declare at least one feature")
    names = [f.name for f in group.features]
    if len(set(names)) != len(names):
        problems.append("features are declared twice")
    clash = sorted(set(names) & RESERVED)
    if clash:
        problems.append(f"columns {clash} are reserved")
    for f in group.features:
        problems += feature_problems(f)
        if f.null_status and "@" not in f.null_status and f.null_status not in names:
            problems.append(f"{f.name}: null_status {f.null_status!r} is not a column of the group")
        if f.version != group.version:
            problems.append(f"{f.name}: version must be the group's ({group.version}) for now")
        if f.entity != group.entity:
            problems.append(f"{f.name}: entity must be the group's ({group.entity})")
    if group.params is not None and not is_dataclass(group.params):
        problems.append("params must be a dataclass instance (or None)")
    return problems + _entity_problems(group)


def _entity_problems(group: FeatureGroup) -> list[str]:
    """An instrument group never reads a market group (that would broadcast one market value
    to every instrument); a market group's features apply to the market as a whole."""
    problems = []
    read = [(group_of_table(i.table) or ("", ""))[0] for i in group.inputs]
    market = [i.table for i, entity in zip(group.inputs, read, strict=True) if entity == "market"]
    if group.entity == "instrument" and market:
        problems.append(
            f"an instrument group reads market groups {market}: broadcasting market values "
            "to instruments needs its own ADR (ADR 0047)"
        )
    narrowed = sorted({f.applies_to for f in group.features} - {"any"})
    if group.entity == "market" and narrowed:
        problems.append(
            f"a market group applies to the whole market (applies_to 'any'), not {narrowed}"
        )
    return problems
