"""An instrument's daily bars over an explicit window (ADR 0037 ``PriceSeries``), adjusted for the
corporate actions in it (``data.prices.adjusted_bars``: splits by default, none, or total
return).

Range grain (docs/api/read-model.md "Session resolution"): the caller names ``start``; ``end``
is the session's date unless named (never after it), never "the latest stored". No bars in the
window is an empty series, not an error. A bar's ``close`` is a point of a price series; the
session's close as a fact is the catalogue feature ``rollup.price_stats@v2.close``."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import pandas as pd

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.data.prices import adjusted_bars
from algotrade.services.read.context import ReadContext
from algotrade.services.read.values import to_scalar


class Adjustment(StrEnum):
    """How bars are adjusted for the corporate actions in the window."""

    SPLITS = "splits"
    NONE = "none"
    TOTAL_RETURN = "total_return"


@dataclass(frozen=True)
class PriceBar:
    """One session's daily bar, adjusted (``vwap``: None when not stored)."""

    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None


@dataclass(frozen=True)
class PriceSeries:
    """The bars of ``start..end`` (inclusive), oldest first."""

    instrument_id: str
    adjustment: Adjustment
    start: date
    end: date
    bars: tuple[PriceBar, ...]


def _vwap(value: object) -> float | None:
    found = to_scalar(value)
    return float(found) if isinstance(found, int | float) else None


def load_prices(
    ctx: ReadContext,
    instrument_ids: Sequence[str],
    start: date,
    end: date | None = None,
    adjustment: Adjustment = Adjustment.SPLITS,
) -> dict[str, PriceSeries]:
    """Each instrument's bars for ``start..end`` (``end``: the session's date): one read for
    them all."""
    last = end if end is not None else ctx.session.date
    if last > ctx.session.date:  # a window past the session would show what it did not know
        raise ConfigurationError(f"end {last} is after the session {ctx.session.date}")
    ids = list(dict.fromkeys(instrument_ids))
    found: dict[str, list[PriceBar]] = {iid: [] for iid in ids}
    try:
        frame, _ = adjusted_bars(ctx.reader, "1d", start, last, ids, adjustment=adjustment.value)
    except MissingDataError:  # no bars stored in the window
        frame = None
    for row in [] if frame is None else frame.to_dict("records"):
        found[str(row["instrument_id"])].append(
            PriceBar(
                session=pd.Timestamp(row["session_date"]).date(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                vwap=_vwap(row.get("vwap")),
            )
        )
    return {
        iid: PriceSeries(iid, adjustment, start, last, tuple(sorted(bars, key=lambda b: b.session)))
        for iid, bars in found.items()
    }
