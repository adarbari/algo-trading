"""``price_history@v1``: whether the instrument traded on the session, and its range over the
history it has (ADR 0046).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``), the last
``year_sessions`` sessions plus ``listing_quiet`` sessions before them. One row per instrument
with a bar among the last ``year_sessions`` sessions (the session included), so a stock that
did not trade on the session still has a row saying so: the read shows "No trade" for its
close, never an older close (ADR 0036). Only bars on or before the session are read.

    bar_status       TRADED (a bar on the session) or NO_TRADE (none; an earlier bar in the
                     window). The ``null_status`` of ``price_stats.close``
    last_bar_session the session of the latest bar on or before the session
    range_sessions   sessions from the first bar in the window to the session, both included
    range_status     how much history the range covers (the first that holds):
                     FULL           at least ``full_bars`` bars in the window (as
                                    ``price_stats``' 52-week high and low)
                     SINCE_LISTING  no bar in the ``listing_quiet`` sessions before the first
                                    bar of the window (a listing, or a return after a long
                                    halt), and at least ``min_listing_sessions`` sessions since
                     NEW_LISTING    a listing with fewer sessions than that
                     FEW_BARS       otherwise: an older listing that trades too rarely to fill
                                    the window
    high_avail       highest daily high over the window's bars when FULL or SINCE_LISTING
    low_avail        lowest daily low, likewise

``high_avail`` / ``low_avail`` give a "high since listing" where the 52-week high is null for
a young listing; NEW_LISTING and FEW_BARS read EXPLAINED ("New listing", "Too few trades").
``config/site/rollups.toml ["price_history@v1"]`` sets the window and the thresholds.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, NullReason
from algotrade.features.rollups.price.price_stats import BARS, CLOSE, HIGH, LOW, panel

type Matrix = npt.NDArray[np.float64]

NAME = "price_history"
VERSION = 1
TRADED, NO_TRADE = "TRADED", NullReason.NO_TRADE.value
FULL, SINCE_LISTING = "FULL", "SINCE_LISTING"
NEW_LISTING, FEW_BARS = NullReason.NEW_LISTING.value, NullReason.FEW_BARS.value
SHORT = (FEW_BARS, NEW_LISTING)  # the range statuses with no range: EXPLAINED (ADR 0046)
_SHORT_MEANING = (
    "range_status is NEW_LISTING (fewer than min_listing_sessions sessions since listing) or "
    "FEW_BARS (an older listing with fewer than full_bars bars in the window)"
)

FEATURES = (
    Feature(
        "bar_status", "str", "category",
        "TRADED: a bar on the session; NO_TRADE: none, though the instrument has a bar among "
        "the last year_sessions (252) sessions",
        "never", "label", categories=(TRADED, NO_TRADE), inputs=(CLOSE,),
    ),
    Feature(
        "last_bar_session", "date", "date",
        "The session of the latest bar on or before the session", "never", inputs=(CLOSE,),
    ),
    Feature(
        "range_sessions", "int", "sessions",
        "Sessions the range covers: from the first bar among the last year_sessions (252) "
        "sessions to the session, both included",
        "never", valid_range=(1, None), inputs=(CLOSE,),
    ),
    Feature(
        "range_status", "str", "category",
        "How much history the range covers: FULL (at least full_bars, 240, bars in the "
        "window), SINCE_LISTING (listed inside the window, at least min_listing_sessions, 20, "
        "sessions ago), NEW_LISTING (listed more recently), FEW_BARS (an older listing that "
        "trades too rarely)",
        "never", "label", categories=(FULL, SINCE_LISTING, NEW_LISTING, FEW_BARS),
        inputs=(CLOSE,),
    ),
    Feature(
        "high_avail", "float32", "usd_per_share",
        "Highest daily high over the history available: the last year_sessions (252) "
        "sessions, or since listing; split-adjusted (not dividend-adjusted)",
        _SHORT_MEANING, valid_range=(0, None), inputs=(HIGH,),
        null_status="range_status", explained_statuses=SHORT,
    ),
    Feature(
        "low_avail", "float32", "usd_per_share",
        "Lowest daily low over the history available: the last year_sessions (252) sessions, "
        "or since listing; split-adjusted (not dividend-adjusted)",
        _SHORT_MEANING, valid_range=(0, None), inputs=(LOW,),
        null_status="range_status", explained_statuses=SHORT,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class PriceHistoryParams:
    year_sessions: int = 252  # the window, in sessions (price_stats' 52 weeks)
    full_bars: int = 240  # bars in the window for FULL (price_stats' min_year_sessions)
    listing_quiet: int = 60  # sessions with no bar before the first one that make it a listing
    min_listing_sessions: int = 20  # sessions since listing for SINCE_LISTING (else NEW_LISTING)

    def __post_init__(self) -> None:
        if self.year_sessions < 2:
            raise ValueError(f"year_sessions must be >= 2, got {self.year_sessions}")
        if not 1 <= self.full_bars <= self.year_sessions:
            raise ValueError("full_bars must be between 1 and year_sessions")
        if self.listing_quiet < 1:
            raise ValueError("listing_quiet must be >= 1")
        if not 1 <= self.min_listing_sessions <= self.year_sessions:
            raise ValueError("min_listing_sessions must be between 1 and year_sessions")


def lookback(p: PriceHistoryParams) -> int:
    """Earlier sessions needed: the window and the quiet sessions before it."""
    return p.year_sessions + p.listing_quiet - 1


def history(
    high: Matrix, low: Matrix, close: Matrix, p: PriceHistoryParams
) -> dict[str, npt.NDArray[np.generic]]:
    """Every column but ``last_bar_session`` (as the index of the last bar in the panel) for
    the LAST session of the panel (``listing_quiet + year_sessions`` sessions x instruments,
    NaN: no bar), one value per instrument, for the instruments with a bar in the window."""
    quiet, year = p.listing_quiet, p.year_sessions
    traded = ~np.isnan(close)
    window = traded[-year:]
    present = window.any(axis=0)
    first = np.argmax(window, axis=0)  # index in the window of the first bar (0 if none)
    bars = window.sum(axis=0)
    since = year - first  # sessions from the first bar to the session, both included
    rows = np.arange(len(close))[:, None]
    start = len(close) - year + first  # the first bar's row in the panel
    before = (rows >= start - quiet) & (rows < start)
    listing = ~(traded & before).any(axis=0)
    status = np.select(
        [bars >= p.full_bars, listing & (since >= p.min_listing_sessions), listing],
        [FULL, SINCE_LISTING, NEW_LISTING],
        FEW_BARS,
    )
    ranged = (status == FULL) | (status == SINCE_LISTING)
    with np.errstate(invalid="ignore"):
        high_avail = np.where(ranged, np.fmax.reduce(high[-year:], axis=0), np.nan)
        low_avail = np.where(ranged, np.fmin.reduce(low[-year:], axis=0), np.nan)
    last = len(close) - 1 - np.argmax(traded[::-1], axis=0)
    return {
        "present": present,
        "bar_status": np.where(traded[-1], TRADED, NO_TRADE),
        "last_bar": last,
        "range_sessions": since,
        "range_status": status,
        "high_avail": high_avail,
        "low_avail": low_avail,
    }


def compute(inputs: Inputs, session: date, p: PriceHistoryParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, lookback(p) + 1)
    px = panel(bars, days)
    values = history(px.high, px.low, px.close, p)
    keep = values["present"]
    frame = pd.DataFrame({"instrument_id": px.ids[keep]})
    for column in ("bar_status", "range_status", "high_avail", "low_avail"):
        frame[column] = values[column][keep]
    frame["last_bar_session"] = [days[i] for i in values["last_bar"][keep]]
    frame["range_sessions"] = values["range_sessions"][keep].astype(np.int64)
    return frame[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Whether the instrument traded on the session, and its high / low over the history it has",
    (Input(BARS, lookback=lookback),),
    FEATURES,
    compute,
    PriceHistoryParams(),
)
