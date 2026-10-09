"""A market's stored fields over a window, shaped for a chart (ADR 0047, ADR 0038): for the
exchange sessions of ``start..min(end, ctx.session)``, each name's value read from that
session's own partition (``load_series(entity="market")``: a session with no stored row is a
gap, never carried forward from an earlier one; range grain, docs/api/read-model.md "Session
resolution"). A number is bucketed server-side into at most ``points`` points that keep each
bucket's extremes (``buckets.py``); a flag or a label is merged into ``segments`` (``ON`` /
``OFF`` / ``UNKNOWN``, or the label text), so the browser only draws.

Only stored ``market.`` fields have a history: a ``feature.*`` expression would be computed for
every session of the window on read (thousands), so it is a request error; the numbers it
needs are stored by their group."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import GROUP_FIELD_HEADS, field_source
from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_between
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.services.read.instruments.series import load_series, market_frame
from algotrade.services.read.market.buckets import (
    UNKNOWN,
    Point,
    Segment,
    bucket_numbers,
    merge_segments,
)
from algotrade.services.read.market.features import US

HEAD = GROUP_FIELD_HEADS["market"] + "."
NUMBERS = ("float", "float32", "int")
MAX_POINTS = 5_000


@dataclass(frozen=True)
class SeriesHistory:
    """One field's history. A number: ``points`` (oldest first; a ``None`` value is a gap)
    from buckets of ``bucket_sessions`` sessions, ``segments`` empty. A flag or a label:
    ``segments`` (``bucket_sessions`` 1: every session counted), ``points`` empty."""

    name: str
    bucket_sessions: int
    points: tuple[Point, ...]
    segments: tuple[Segment, ...]


def _state(value: Scalar, dtype: str) -> str:
    if value is None:
        return UNKNOWN
    if dtype == "bool":
        return "ON" if value else "OFF"
    return str(value)


def _history(
    name: str, dtype: str, sessions: list[date], values: list[Scalar], n: int
) -> SeriesHistory:
    if dtype in NUMBERS:
        numbers = [None if v is None else float(v) for v in values]
        size, points = bucket_numbers(sessions, numbers, n)
        return SeriesHistory(name, size, points, ())
    segments = merge_segments(sessions, [_state(v, dtype) for v in values])
    return SeriesHistory(name, 1, (), segments)


def _checked(ctx: ReadContext, names: Sequence[str]) -> dict[str, str]:
    """The dtype of each name, once every name is a stored market field."""
    for name in names:
        if not name.startswith(HEAD):
            raise ConfigurationError(
                f"{name}: only stored market fields ({HEAD}<group>@v<N>.<column>) have a "
                "history; a feature.* expression would be computed for every session of the "
                "window on read"
            )
    infos = feature_infos(ctx.features, names, "market")  # UnknownFeatureError for a stranger
    for name, info in infos.items():
        if info.dtype not in (*NUMBERS, "bool", "str"):
            raise ConfigurationError(f"{name}: a {info.dtype} field has no chart history")
    return {name: info.dtype for name, info in infos.items()}


def load_market_history(
    ctx: ReadContext,
    names: Sequence[str],
    start: date,
    end: date,
    points: int = 600,
    market: str = US,
) -> tuple[SeriesHistory, ...]:
    """``names`` (stored market fields; repeats dropped) of ``market`` over ``start..end``
    (``end`` is cut to the session's date: a window past it would show what it did not know),
    in the order asked. ``ConfigurationError`` for a ``feature.*`` or non-market name, an
    unsupported type, a window that ends before it starts, or ``points`` outside
    ``2..MAX_POINTS``; ``UnknownFeatureError`` for a name not in the market catalogue."""
    if not 2 <= points <= MAX_POINTS:
        raise ConfigurationError(f"points {points} is outside 2..{MAX_POINTS}")
    if end < start:
        raise ConfigurationError(f"end {end} is before start {start}")
    wanted = tuple(dict.fromkeys(names))
    dtypes = _checked(ctx, wanted)
    last = min(end, ctx.session.date)
    sessions = sessions_between(start, last) if start <= last else []
    mid = market_id(market)
    found = load_series(ctx, [mid], wanted, start, last, entity="market")[mid] if sessions else None
    stored = {p.session: p.values for p in found.points} if found else {}
    return tuple(
        _history(
            name,
            dtypes[name],
            sessions,
            [stored[d][i] if d in stored else None for d in sessions],
            points,
        )
        for i, name in enumerate(wanted)
    )


def warm_market_frames(ctx: ReadContext, market: str = US) -> tuple[str, ...]:
    """Read every stored table of the market catalogue into ``ctx.cache`` (``market_frame``)
    for ``ctx``'s session and published state, so the first chart after a publish or a start
    does not read thousands of partitions on a request; the tables read, in name order."""
    tables = sorted(
        {
            field_source(name)[0]
            for name in ctx.features.field_types("market")
            if name.startswith(HEAD)
        }
    )
    for table in tables:
        market_frame(ctx, table, [market_id(market)])
    return tuple(tables)
