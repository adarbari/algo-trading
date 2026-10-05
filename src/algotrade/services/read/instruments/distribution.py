"""One catalogue feature across instruments for the session (``FeatureDistribution``): how
many have a value, how many a stored null, and the shape of the values (quantiles and a
histogram for a number, the most frequent values otherwise).

The values are the read model's feature values (``features.load_feature_values``, every
instrument of the session's reference snapshot), so a distribution and a page agree on what is
stored for the session (ADR 0036): an instrument with no row (``NO_ROW``) is not counted, a
stored null (``NULL``) is counted as a null, and a table with no partition for the session
makes the whole distribution UNKNOWN (``unknown``: ``NO_PARTITION``, nothing counted), never an
older partition's values."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from algotrade.core.model.fields import NUMERIC_TYPES, REFERENCE_TABLE
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

QUANTILES = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
BINS = 20
TOP_CATEGORIES = 25


@dataclass(frozen=True)
class Quantile:
    q: float  # 0.5: the median
    value: float


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
class FeatureDistribution:
    """``name`` across instruments on ``session``. ``count``: instruments with a row (a value
    or a stored null); ``nulls``: the stored nulls; ``quantiles`` and ``histogram`` (20
    equal-width bins) for a numeric feature, ``categories`` (the most frequent values) for any
    other; ``unknown``: why nothing is counted (no partition for the session)."""

    name: str
    session: date
    info: FeatureInfo
    count: int
    nulls: int
    quantiles: tuple[Quantile, ...]
    histogram: tuple[Bin, ...]
    categories: tuple[Category, ...]
    unknown: Unknown | None = None


def _numeric(values: Sequence[object]) -> tuple[tuple[Quantile, ...], tuple[Bin, ...]]:
    numbers = np.array([v for v in values if isinstance(v, int | float)], dtype=float)
    finite = numbers[np.isfinite(numbers)]
    if not len(finite):
        return (), ()
    quantiles = np.quantile(finite, QUANTILES)
    counts, edges = np.histogram(finite, bins=BINS)
    bins = tuple(Bin(float(edges[i]), float(edges[i + 1]), int(c)) for i, c in enumerate(counts))
    return tuple(Quantile(q, float(v)) for q, v in zip(QUANTILES, quantiles, strict=True)), bins


def _categories(values: Sequence[object]) -> tuple[Category, ...]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:TOP_CATEGORIES]
    return tuple(Category(v, c) for v, c in ranked)


def _absent(found: list[FeatureValue]) -> Unknown | None:
    """The ``NO_PARTITION`` reason when the feature is not stored for the session at all."""
    first = found[0].unknown if found else None
    if first is not None and first.code is UnknownCode.NO_PARTITION:
        return first
    return None


def load_distribution(ctx: ReadContext, name: str) -> FeatureDistribution:
    """``name`` (a catalogue field) across every instrument for ``ctx.session``.
    ``UnknownFeatureError`` when the caller's catalogue has no such field."""
    info = feature_infos(ctx.features, [name])[name]
    found = [values[0] for values in load_feature_values(ctx, None, [name]).values()]
    absent = _absent(found)
    if absent is not None or not found:
        nothing = f"{REFERENCE_TABLE} has no snapshot on or before {ctx.session.date.isoformat()}"
        detail = absent or Unknown(UnknownCode.NO_PARTITION, nothing)
        return FeatureDistribution(name, ctx.session.date, info, 0, 0, (), (), (), detail)
    rows = [v for v in found if v.unknown is None or v.unknown.code is UnknownCode.NULL]
    present = [v.value for v in rows if v.unknown is None]
    quantiles: tuple[Quantile, ...] = ()
    bins: tuple[Bin, ...] = ()
    categories: tuple[Category, ...] = ()
    if info.dtype in NUMERIC_TYPES:
        quantiles, bins = _numeric(present)
    else:
        categories = _categories(present)
    nulls = len(rows) - len(present)
    return FeatureDistribution(
        name, ctx.session.date, info, len(rows), nulls, quantiles, bins, categories
    )
