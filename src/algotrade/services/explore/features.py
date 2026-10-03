"""The feature catalogue (every field a selection or a page can show) and one feature's
cross-sectional distribution on a session.

Fields are ``instrument.<column>`` (reference facts, company details) and
``rollup.<name>@v<N>.<column>`` (registered rollups, ``features.registry``). Unit and range
are not declared by rollups yet: they stay null until the feature catalogue declares them.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.fields import (
    COMPANY_TABLE,
    REFERENCE_TABLE,
    ROLLUP_TABLE_PREFIX,
    field_source,
)
from algotrade.data.reference import instrument_view
from algotrade.data.rollups import rollup_rows
from algotrade.features.registry import ROLLUPS
from algotrade.services.configs import field_catalog
from algotrade.services.explore.store import NotFoundError, ReadStore, partition_for
from algotrade.services.views import to_value

NULL_MEANING = (
    "UNKNOWN: not computable on the session (missing input or history); never passes a selection"
)
QUANTILES = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
BINS = 20
TOP_CATEGORIES = 25
NUMERIC = frozenset({"float", "int"})


@dataclass(frozen=True)
class FeatureInfo:
    name: str
    kind: str  # "instrument" (reference / company fact) or "rollup"
    source: str  # the table it is read from
    dtype: str  # str | float | int | bool | date
    description: str
    null_meaning: str
    version: int | None = None
    rollup: str | None = None  # <name>@v<N>
    inputs: list[str] = field(default_factory=list)
    unit: str | None = None
    range: list[float] | None = None


def _rollup_info(name: str, dtype: str) -> FeatureInfo:
    table, _ = field_source(name)
    rollup = ROLLUPS[table.removeprefix(ROLLUP_TABLE_PREFIX)]
    return FeatureInfo(
        name=name,
        kind="rollup",
        source=table,
        dtype=dtype,
        description=rollup.description,
        null_meaning=NULL_MEANING,
        version=rollup.version,
        rollup=rollup.key,
        inputs=[i.table for i in rollup.inputs],
    )


def feature_catalogue() -> list[FeatureInfo]:
    """Every selectable field, instrument facts first, then rollups in registry order."""
    out = []
    for name, dtype in field_catalog().fields.items():
        if name.startswith("rollup."):
            out.append(_rollup_info(name, dtype))
            continue
        table, _ = field_source(name)
        kind = "company detail (SEC EDGAR)" if table == COMPANY_TABLE else "reference fact"
        meaning = "not known for this instrument (UNKNOWN)"
        out.append(FeatureInfo(name, "instrument", table, dtype, kind, meaning))
    return out


@dataclass(frozen=True)
class Bin:
    lo: float
    hi: float
    count: int


@dataclass(frozen=True)
class Category:
    value: str
    count: int


@dataclass(frozen=True)
class Distribution:
    name: str
    dtype: str
    session: date
    count: int  # instruments with a row (non-null + null)
    nulls: int
    quantiles: dict[str, float]  # "0.5" -> median (numeric features)
    histogram: list[Bin]  # numeric features
    categories: list[Category]  # other features: the most frequent values


def _values(store: ReadStore, name: str, on: date | None) -> tuple[pd.Series, date]:
    table, column = field_source(name)
    if table.startswith(ROLLUP_TABLE_PREFIX):
        session = partition_for(store.reader, table, on)
        frame = rollup_rows(store.reader, table, session, session)
        if frame is None or column not in frame.columns:
            raise NotFoundError(f"{name}: no values stored for {session}")
        return frame[column], session
    session = partition_for(store.reader, REFERENCE_TABLE, on)
    view = instrument_view(store.reader, session, [name])
    if name not in view.frame.columns:
        raise NotFoundError(f"{name}: no values stored for {session}")
    return view.frame[name], session


def _numeric(values: pd.Series) -> tuple[dict[str, float], list[Bin]]:
    numbers = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    finite = numbers[np.isfinite(numbers)]
    if not len(finite):
        return {}, []
    quantiles = np.quantile(finite, QUANTILES)
    counts, edges = np.histogram(finite, bins=BINS)
    bins = [Bin(float(edges[i]), float(edges[i + 1]), int(c)) for i, c in enumerate(counts)]
    return {str(q): float(v) for q, v in zip(QUANTILES, quantiles, strict=True)}, bins


def feature_distribution(store: ReadStore, name: str, on: date | None = None) -> Distribution:
    """``name`` across instruments on the latest session on or before ``on``."""
    dtype = field_catalog().fields.get(name)
    if dtype is None:
        raise NotFoundError(f"no feature {name!r} (GET /features lists them)")
    values, session = _values(store, name, on)
    present = values.dropna()
    quantiles: dict[str, float] = {}
    bins: list[Bin] = []
    categories: list[Category] = []
    if dtype in NUMERIC:
        quantiles, bins = _numeric(present)
    else:
        counts = present.map(lambda v: str(to_value(v))).value_counts().head(TOP_CATEGORIES)
        categories = [Category(str(v), int(c)) for v, c in counts.items()]
    return Distribution(
        name, dtype, session, len(values), int(values.isna().sum()), quantiles, bins, categories
    )
