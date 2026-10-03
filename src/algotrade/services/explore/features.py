"""The feature catalogue (every field a selection or a page can show) and one feature's
cross-sectional distribution on a session.

Fields are ``instrument.<column>`` (reference facts, company details),
``rollup.<name>@v<N>.<column>`` (registered rollups, ``features.registry``) and
``feature.<name>`` (expression features, computed on read). Unit and range come from each
feature's declaration (ADR 0023). The catalogue is the store user's: the site's fields plus
their own expression features (``scope = "user"``, ``owner``; ADR 0023 step 4).
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.fields import (
    COMPANY_TABLE,
    FEATURE_FIELD_PREFIX,
    NUMERIC_TYPES,
    REFERENCE_TABLE,
    ROLLUP_TABLE_PREFIX,
    field_source,
    is_feature_field,
)
from algotrade.data.reference import instrument_view
from algotrade.data.rollups import rollup_rows
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import GROUPS, feature
from algotrade.services.configs import catalog_of
from algotrade.services.explore.store import (
    NotFoundError,
    ReadStore,
    partition_for,
    store_features,
)
from algotrade.services.features import read_expressions
from algotrade.services.views import to_value

NULL_MEANING = (
    "UNKNOWN: not computable on the session (missing input or history); never passes a selection"
)
QUANTILES = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
BINS = 20
TOP_CATEGORIES = 25
NUMERIC = NUMERIC_TYPES


@dataclass(frozen=True)
class FeatureInfo:
    name: str  # the selection field (rollup.<group>@v<N>.<column>, feature.<name>, instrument.*)
    kind: str  # instrument (reference / company fact), or the feature's kind (window, chain, ...)
    source: str  # the table it is read from ("expression": computed on read)
    dtype: str  # str | float | int | bool | date
    description: str
    null_meaning: str
    version: int | None = None
    group: str | None = None  # the feature group <name>@v<N>
    key: str | None = None  # the feature key <group>.<column>@v<N>
    inputs: list[str] = field(default_factory=list)
    unit: str | None = None
    range: list[float | None] | None = None  # plausible (min, max); values outside are kept
    categories: list[str] = field(default_factory=list)
    scope: str = "site"  # site, or user: one of the caller's own expression features
    owner: str | None = None  # the user who declared it (scope user)
    # open, or personal: derived from a personal-use market-data licence (IBKR); the API will
    # hide personal features from users other than the owner once there are any (ADR 0028)
    licence: str = "open"


def _group_info(name: str, dtype: str) -> FeatureInfo:
    table, _ = field_source(name)
    found = feature(name)
    if found is None:  # pragma: no cover - every catalogue field of a group is declared
        raise NotFoundError(f"no feature metadata for {name!r}")
    return FeatureInfo(
        name=name,
        kind=found.kind,
        source=table,
        dtype=dtype,
        description=found.description,
        null_meaning=found.null_meaning,
        version=found.version,
        group=found.group,
        key=found.key,
        inputs=list(found.inputs) or [i.table for i in GROUPS[found.group].inputs],
        unit=found.unit or None,
        range=list(found.valid_range) if found.valid_range else None,
        categories=list(found.categories),
        licence=found.licence,
    )


def _expression_info(fs: FeatureSet, name: str, dtype: str) -> FeatureInfo:
    expression = fs.expressions[name.removeprefix(FEATURE_FIELD_PREFIX)]
    f = expression.feature
    return FeatureInfo(
        name=name,
        kind=f.kind,
        source=fs.table(f.name) if expression.materialise else "expression",
        dtype=dtype,
        description=f.description,
        null_meaning=f.null_meaning,
        version=f.version,
        key=f.key,
        inputs=list(f.inputs),
        unit=f.unit or None,
        range=list(f.valid_range) if f.valid_range else None,
        categories=list(f.categories),
        scope=expression.scope,
        owner=expression.definition.owner,
        licence=f.licence,
    )


def feature_catalogue(store: ReadStore) -> list[FeatureInfo]:
    """Every field ``store.user`` may select, instrument facts first, then feature groups in
    registry order (metadata from ``features.registry.feature``), then expression features
    (the site's, then the user's own)."""
    fs = store_features(store)
    out = []
    for name, dtype in catalog_of(fs).fields.items():
        if name.startswith("rollup."):
            out.append(_group_info(name, dtype))
            continue
        if is_feature_field(name):
            out.append(_expression_info(fs, name, dtype))
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


def _expression_values(store: ReadStore, name: str, on: date | None) -> tuple[pd.Series, date]:
    """An expression feature on the latest session on or before ``on`` that any table it
    reads has (tables without that session make it null: UNKNOWN)."""
    expression = name.removeprefix(FEATURE_FIELD_PREFIX)
    fs = store_features(store)
    tables = fs.stored_columns([expression])
    stored = [d for t in tables for d in store.reader.dates(t) if on is None or d <= on]
    if not stored:
        raise NotFoundError(f"{name}: no values stored on or before {on}")
    session = max(stored)
    frame = read_expressions(store.reader, [expression], session, features=fs).frame
    return frame[expression], session


def _values(store: ReadStore, name: str, on: date | None) -> tuple[pd.Series, date]:
    if is_feature_field(name):
        return _expression_values(store, name, on)
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
    dtype = catalog_of(store_features(store)).fields.get(name)
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
