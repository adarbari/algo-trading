"""The ``Rollup`` declaration: what a rollup reads, its parameters, its typed output columns
and its pure ``compute``.

A rollup is ``<name>@v<N>``, stored as ``rollups/instrument/<name>@v<N>`` with one row per
instrument per session. Everything else is derived from the declaration: the selection
catalogue (``rollup.<name>@v<N>.<column>``), the stored column types (``framework.columns``),
the ``rollups.toml`` section (``params``) and the inputs the runner loads.

``compute(inputs, session, params)`` is pure: ``inputs`` maps each declared input table to
its frame for the session (rows on or before the session only, ``None`` when an optional
input has nothing), and it returns ``instrument_id`` plus the declared columns.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, is_dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.fields import FIELD_TYPES, ROLLUP_TABLE_PREFIX

type Inputs = Mapping[str, pd.DataFrame | None]
type Compute = Callable[[Inputs, date, Any], pd.DataFrame]
type Lookback = int | Callable[[Any], int]

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED = frozenset({"instrument_id", "session_date", "knowledge_ts", "source", "run_id"})


@dataclass(frozen=True)
class Input:
    """One input table. ``lookback``: earlier exchange sessions also needed (an int, or a
    function of the params). ``required``: without data for the session the rollup has
    nothing to compute (the runner reports NO_INPUT instead of calling ``compute``)."""

    table: str
    lookback: Lookback = 0
    required: bool = True

    def sessions_back(self, params: Any) -> int:
        n = self.lookback(params) if callable(self.lookback) else self.lookback
        if n < 0:
            raise ValueError(f"{self.table}: lookback must be >= 0, got {n}")
        return n


@dataclass(frozen=True)
class Rollup:
    name: str
    version: int
    description: str
    inputs: tuple[Input, ...]
    columns: Mapping[str, str]  # output column -> field type ("str" | "float" | ...)
    compute: Compute = field(repr=False)
    # A frozen dataclass of default parameters (scalar fields are rollups.toml keys), or
    # ``None``: the rollup takes no parameters.
    params: Any = None

    def __post_init__(self) -> None:
        problems = declaration_problems(self)
        if problems:
            raise ValueError(f"rollup {self.name}@v{self.version}: {'; '.join(problems)}")

    @property
    def key(self) -> str:
        return f"{self.name}@v{self.version}"

    @property
    def table(self) -> str:
        return f"{ROLLUP_TABLE_PREFIX}{self.key}"


def declaration_problems(rollup: Rollup) -> list[str]:
    """Why a declaration is invalid (empty: valid)."""
    problems = []
    if not _NAME.match(rollup.name):
        problems.append(f"name must match {_NAME.pattern}")
    if rollup.version < 1:
        problems.append("version must be >= 1")
    if not rollup.inputs:
        problems.append("declare at least one input")
    if len({i.table for i in rollup.inputs}) != len(rollup.inputs):
        problems.append("inputs are declared twice")
    if not rollup.columns:
        problems.append("declare at least one output column")
    bad = sorted(c for c, t in rollup.columns.items() if t not in FIELD_TYPES)
    if bad:
        problems.append(f"columns {bad}: types must be one of {sorted(FIELD_TYPES)}")
    clash = sorted(set(rollup.columns) & RESERVED)
    if clash:
        problems.append(f"columns {clash} are reserved")
    if rollup.params is not None and not is_dataclass(rollup.params):
        problems.append("params must be a dataclass instance (or None)")
    return problems
