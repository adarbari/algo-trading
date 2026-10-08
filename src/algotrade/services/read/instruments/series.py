"""Catalogue features of an instrument per session over an explicit window (ADR 0037
``FeatureSeries``): the history behind a sparkline or a feature chart.

Range grain (docs/api/read-model.md "Session resolution"): the caller names ``start``; ``end``
is the session's date unless named (never after it), never "the latest stored". Rollup columns
are read for the sessions stored in the window (``data.rollups.rollup_rows``) and expression
features computed for them (``services.features.read_expressions``, the evaluation a selection
uses). A session with no value for a name has ``None`` there. ``instrument.*`` facts are
snapshot facts with no history: asking for one is a request error, and so is a name outside the
caller's catalogue (``UnknownFeatureError``). The rows of a stored table are shared through
``ctx.cache`` (market entity only: keyed on the table, ids, the session and the published
state and the window's start; the read is the window up to the session), so a chart that
asks again for it reads the store once."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import FEATURE_FIELD_PREFIX, field_source, is_feature_field
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.data.rollups import rollup_rows
from algotrade.services.features import read_expressions
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.services.read.values import to_scalar

EXPRESSIONS = ""  # the group of expression features (computed, not one table)


@dataclass(frozen=True)
class SeriesPoint:
    """One session's values, in the order of ``FeatureSeries.names`` (None: no value)."""

    session: date
    values: tuple[Scalar, ...]


@dataclass(frozen=True)
class FeatureSeries:
    """``names`` for each stored session of ``start..end``, oldest first."""

    instrument_id: str
    names: tuple[str, ...]
    start: date
    end: date
    points: tuple[SeriesPoint, ...]


def _groups(
    ctx: ReadContext, names: Sequence[str], entity: str
) -> dict[str, list[tuple[str, str]]]:
    """Rollup table (or ``EXPRESSIONS``) -> [(catalogue name, column)]."""
    infos = feature_infos(ctx.features, names, entity)  # UnknownFeatureError for a name not there
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, info in infos.items():
        if is_feature_field(name):
            groups.setdefault(EXPRESSIONS, []).append(
                (name, name.removeprefix(FEATURE_FIELD_PREFIX))
            )
        elif info.kind == "instrument":
            raise ConfigurationError(f"{name}: an instrument fact has no history (no series)")
        else:
            groups.setdefault(field_source(name)[0], []).append((name, field_source(name)[1]))
    return groups


def _frame(
    ctx: ReadContext,
    table: str,
    columns: list[str],
    ids: list[str],
    start: date,
    end: date,
    entity: str,
) -> pd.DataFrame | None:
    if table == EXPRESSIONS:  # computed from the caller's formulas: never shared
        return read_expressions(
            ctx.reader, columns, start, end, instruments=ids, features=ctx.features
        ).frame
    if entity != "market" or ctx.reader.own_run is not None:
        # Instrument reads come in batches (dataloaders) and would evict the session's and
        # the screens' entries; a run's pending writes do not move visible_seq.
        return rollup_rows(ctx.reader, table, start, end, instruments=ids)
    # A market table's rows do not depend on the caller, so every request shares them. The
    # read is the window up to the session (a day is a partition: a read from the first stored
    # day, 14 000 of them since 1971, took 10 s for a one-year chart), and the published state
    # is in the key (read before the rows, ADR 0022), so a publish makes it unreachable. A
    # chart that asks again for the window reads the store once. The frame is only read, never
    # changed, by its callers.
    key = ("series-frame", table, tuple(ids), start, ctx.session.date, ctx.reader.visible_seq())
    cached: tuple[pd.DataFrame | None] | None = ctx.cache.get(key)
    if cached is None:
        cached = (rollup_rows(ctx.reader, table, start, ctx.session.date, instruments=ids),)
        ctx.cache.put(key, cached)
    frame = cached[0]
    if frame is None:
        return None
    days = frame["session_date"]
    window = frame[(days >= start) & (days <= end)]
    return None if window.empty else window


def load_series(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    names: Sequence[str],
    start: date,
    end: date | None = None,
    entity: str = "instrument",
) -> dict[str, FeatureSeries]:
    """``names`` (catalogue fields, in the order asked; repeats dropped) of each instrument
    for every stored session of ``start..end`` (``end``: the session's date): one read per
    table for them all. ``entity``: whose catalogue and ids (``market``: ``market_id("US")``,
    ADR 0047)."""
    wanted = tuple(dict.fromkeys(names))
    last = end if end is not None else ctx.session.date
    if last > ctx.session.date:  # a window past the session would show what it did not know
        raise ConfigurationError(f"end {last} is after the session {ctx.session.date}")
    ids = list(dict.fromkeys(instrument_ids))
    by_day: dict[tuple[str, date], dict[str, Any]] = {}
    for table, fields in _groups(ctx, wanted, entity).items():
        frame = _frame(ctx, table, [c for _, c in fields], ids, start, last, entity)
        if frame is None or frame.empty:
            continue
        for row in frame.to_dict("records"):
            day = pd.Timestamp(row["session_date"]).date()
            values = by_day.setdefault((str(row["instrument_id"]), day), {})
            values.update({name: to_scalar(row.get(column)) for name, column in fields})
    out = {}
    for iid in ids:
        days = sorted(d for i, d in by_day if i == iid)
        points = tuple(SeriesPoint(d, tuple(by_day[(iid, d)].get(n) for n in wanted)) for d in days)
        out[iid] = FeatureSeries(iid, wanted, start, last, points)
    return out
