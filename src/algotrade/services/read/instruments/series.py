"""Catalogue features of an instrument per session over an explicit window (ADR 0037
``FeatureSeries``): the history behind a sparkline or a feature chart.

Range grain (docs/api/read-model.md "Session resolution"): the caller names ``start``; ``end``
is the session's date unless named (never after it), never "the latest stored". Rollup columns
are read for the sessions stored in the window (``data.rollups.rollup_rows``) and expression
features computed for them (``services.features.read_expressions``, the evaluation a selection
uses). A session with no value for a name has ``None`` there. ``instrument.*`` facts are
snapshot facts with no history: asking for one is a request error, and so is a name outside the
caller's catalogue (``UnknownFeatureError``). The rows of a stored table are shared through
``ctx.cache`` (market entity only, ``market_frame``: keyed on the table, ids, the session and
the published state; the read is the table's whole history up to the session and a window is
a slice of it), so every chart of a published state reads the store once."""

import threading
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
from algotrade.services.read.availability.cause import (
    Cause,
    Unavailable,
    UnavailableKind,
    feature_cause,
)
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
    """``names`` for each stored session of ``start..end``, oldest first. ``unavailable``: the
    names the caller's data licence does not cover (``services.licences``): never read, no value
    at any session, kind ``LICENCE`` (ADR 0028, 0056)."""

    instrument_id: str
    names: tuple[str, ...]
    start: date
    end: date
    points: tuple[SeriesPoint, ...]
    unavailable: tuple[Unavailable, ...] = ()


def _groups(
    ctx: ReadContext, names: Sequence[str], entity: str
) -> dict[str, list[tuple[str, str]]]:
    """Rollup table (or ``EXPRESSIONS``) -> [(catalogue name, column)]."""
    infos = feature_infos(ctx.features, names, entity)  # UnknownFeatureError for a name not there
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, info in infos.items():
        if info.licence not in ctx.licences:  # never read: see ``load_series``
            continue
        if is_feature_field(name):
            groups.setdefault(EXPRESSIONS, []).append(
                (name, name.removeprefix(FEATURE_FIELD_PREFIX))
            )
        elif info.kind == "instrument":
            raise ConfigurationError(f"{name}: an instrument fact has no history (no series)")
        else:
            groups.setdefault(field_source(name)[0], []).append((name, field_source(name)[1]))
    return groups


def _barred_cause(names: Sequence[str], day: date) -> Cause:
    """The admin-only chain of the names a data licence withholds."""
    links = (feature_cause(n, f"{n} is under a data licence the user does not hold", "LICENCE", day)
             for n in names)  # fmt: skip
    return Cause(tuple(link for c in links for link in c.links))


def _frame(
    ctx: ReadContext,
    table: str,
    columns: list[str],
    ids: list[str],
    start: date,
    end: date,
    entity: str,
    span: tuple[date, date] | None = None,
) -> pd.DataFrame | None:
    if table == EXPRESSIONS:  # computed from the caller's formulas: never shared
        return read_expressions(
            ctx.reader,
            columns,
            start,
            end,
            instruments=ids,
            features=ctx.features,
            memo=ctx.cache.get_or_compute,
        ).frame
    if entity != "market" or ctx.reader.own_run is not None:
        # Instrument reads come in batches (dataloaders) and would evict the session's and
        # the screens' entries; a run's pending writes do not move visible_seq.
        return rollup_rows(ctx.reader, table, start, end, instruments=ids)
    held = ctx.cache.get(_frame_key(ctx, table, ids)) if span is not None else None
    if span is not None and held is None:  # the whole history is not already read: just the span
        frame = span_frame(ctx, table, columns, ids, span)
    else:
        frame = held[0] if held is not None else market_frame(ctx, table, ids)
    if frame is None:
        return None
    days = frame["session_date"]
    window = frame[(days >= start) & (days <= end)]
    return None if window.empty else window


def _frame_key(ctx: ReadContext, table: str, ids: Sequence[str]) -> tuple[object, ...]:
    return ("series-frame", table, tuple(ids), ctx.session.date, ctx.reader.version())


def market_frame(ctx: ReadContext, table: str, ids: Sequence[str]) -> pd.DataFrame | None:
    """Every stored row of market table ``table`` for ``ids`` up to the session, shared by every
    request. A market table's rows do not depend on the caller; the read is the table's whole
    history (a day is a partition, 14 000 of them since 1971: 20 s cold), once per published
    state (in the key, read before the rows, ADR 0022: a publish makes it unreachable), and
    every window is a slice of it: keyed on the window's start, the regime page's sixteen
    episodes and its scores chart each read thousands of partitions again (150 s). The API
    reads it ahead of the first request (``warm_market_frames``). The frame is only read,
    never changed, by its callers."""
    key = _frame_key(ctx, table, ids)
    cached: tuple[pd.DataFrame | None] = ctx.cache.get_or_compute(
        key,
        lambda: (rollup_rows(ctx.reader, table, date.min, ctx.session.date, instruments=ids),),
    )
    return cached[0]


def span_frame(
    ctx: ReadContext, table: str, columns: list[str], ids: Sequence[str], span: tuple[date, date]
) -> pd.DataFrame | None:
    """``columns`` of market table ``table`` for ``ids`` over ``span`` only (never the table's
    whole history), read once per request: kept in ``ctx.memo`` (not ``ctx.cache``: a span per
    caller would evict the shared frames), under a lock because a request's loaders run on
    several threads. The read goes through the history copy (ADR 0060) as one column of the
    years the span touches, as ``market_frame`` does for every column of all of them; the rows
    of a day are the same (``table_range``'s point-in-time resolution, pin and ``session_date``
    bound), so a slice of this frame is the slice of ``market_frame``'s."""
    low, high = span[0], min(span[1], ctx.session.date)
    key = ("series-span", table, tuple(sorted(columns)), tuple(ids), low, high, ctx.session.date)
    with ctx.memo.setdefault(("series-span-lock", key), threading.Lock()):
        if key not in ctx.memo:
            ctx.memo[key] = (rollup_rows(ctx.reader, table, low, high, None, list(ids), columns),)
        return ctx.memo[key][0]  # type: ignore[no-any-return]


def load_series(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    names: Sequence[str],
    start: date,
    end: date | None = None,
    entity: str = "instrument",
    span: tuple[date, date] | None = None,
) -> dict[str, FeatureSeries]:
    """``names`` (catalogue fields, in the order asked; repeats dropped) of each instrument
    for every stored session of ``start..end`` (``end``: the session's date): one read per
    table for them all. ``entity``: whose catalogue and ids (``market``: ``market_id("US")``,
    ADR 0047). ``span`` (market only): read just those columns over ``span`` (a window that
    covers ``start..end``, shared by calls of one request) instead of the table's whole
    history: for a caller that wants one window of a few columns (``span_frame``)."""
    wanted = tuple(dict.fromkeys(names))
    last = end if end is not None else ctx.session.date
    if last > ctx.session.date:  # a window past the session would show what it did not know
        raise ConfigurationError(f"end {last} is after the session {ctx.session.date}")
    ids = list(dict.fromkeys(instrument_ids))
    barred = tuple(
        n for n, i in feature_infos(ctx.features, wanted, entity).items()
        if i.licence not in ctx.licences
    )  # fmt: skip
    unavailable = (
        (Unavailable(UnavailableKind.LICENCE, barred, _barred_cause(barred, last)),)
        if barred
        else ()
    )
    by_day: dict[tuple[str, date], dict[str, Any]] = {}
    for table, fields in _groups(ctx, wanted, entity).items():
        frame = _frame(ctx, table, [c for _, c in fields], ids, start, last, entity, span)
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
        out[iid] = FeatureSeries(iid, wanted, start, last, points, unavailable)
    return out
