"""``volume@v1``: how much an instrument traded on the session and how that compares with its
recent sessions: the trend of volume (drying up or expanding), the volume surprise in standard
deviations, and whether the volume sat on up or down days (accumulation / distribution).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``: prices
divided and volume multiplied by the splits up to the session, never a later one), the
session plus ``LOOKBACK`` earlier sessions. One row per instrument with a bar on the session.

Windows are exchange sessions (``core.time.calendar``): a window statistic is null (UNKNOWN),
never a shorter window and never zero, unless every session of it has a bar.

    session_volume       the session's share volume
    dollar_volume        close x volume on the session
    adv_shares_20d       mean volume over the last 20 sessions, the session included
    volume_ratio_5d_20d  mean volume of the last 5 sessions / mean volume of the last 20 (both
                         the session included); null when the 20 had no volume at all
    volume_z_20d         (volume - mean) / sample stdev (ddof 1) of the volume of the 20
                         sessions BEFORE the session; null when those 20 are all equal
    up_volume_share_20d  volume on sessions closing above the previous close / total volume
                         over the last 20 sessions (a flat close counts in the total only)
    cmf_20d              Chaikin money flow: sum(mfm x volume) / sum(volume) over the last 20
                         sessions, mfm = ((close - low) - (high - close)) / (high - low), 0 when
                         high == low

The windows named in the columns (5, 20) are part of the definition: changing one is a new
version. Formulas over these columns (``volume_dry_up``, ``volume_climax``, ``volume_bias``)
are expression features (``config/site/features/volume.toml``).
"""

from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Panel, panel, traded_rows

type Matrix = npt.NDArray[np.float64]

NAME = "volume"
VERSION = 1
BARS = "bars/1d"
SHORT = 5  # sessions of the recent volume in the ratio
WINDOW = 20  # sessions of the volume base, the up-volume share and CMF
LOOKBACK = WINDOW  # the session plus 20 earlier: the z-score base and the close before

CLOSE, HIGH, LOW, VOLUME = (f"{BARS}.{c}" for c in ("close", "high", "low", "volume"))
_WINDOW_GAP = f"a session among the last {WINDOW} has no bar (a gap), or the history is shorter"
_BEFORE_GAP = f"a session among the last {WINDOW + 1} has no bar (a gap), or the history is shorter"
_NO_VOLUME = f"or the last {WINDOW} sessions had no volume at all"

FEATURES = (
    Feature(
        "session_volume", "float32", "shares",
        "The session's share volume, split-adjusted as of the session",
        "never null: a row exists only for an instrument with a bar on the session",
        valid_range=(0, None), inputs=(VOLUME,),
    ),
    Feature(
        "dollar_volume", "float32", "usd",
        "Close x share volume on the session: the dollars traded that day",
        "never null: a row exists only for an instrument with a bar on the session",
        valid_range=(0, None), inputs=(CLOSE, VOLUME),
    ),
    Feature(
        f"adv_shares_{WINDOW}d", "float32", "shares",
        f"Mean share volume over the last {WINDOW} sessions, the session included",
        _WINDOW_GAP, valid_range=(0, None), inputs=(VOLUME,),
    ),
    Feature(
        f"volume_ratio_{SHORT}d_{WINDOW}d", "float32", "ratio",
        f"Mean volume of the last {SHORT} sessions / mean volume of the last {WINDOW} (both "
        "the session included): below 1 the last week was quieter than the month, above 1 "
        "busier",
        f"{_WINDOW_GAP}; {_NO_VOLUME}", valid_range=(0, None), inputs=(VOLUME,),
    ),
    Feature(
        f"volume_z_{WINDOW}d", "float32", "ratio",
        f"(The session's volume - the mean volume of the {WINDOW} sessions before it) / the "
        f"sample standard deviation (ddof 1) of those {WINDOW}: the volume surprise in standard "
        "deviations, on the same base as momentum.rel_volume",
        f"{_BEFORE_GAP}; or the {WINDOW} sessions before the session all had the same volume "
        "(zero standard deviation, all zero included)",
        inputs=(VOLUME,),
    ),
    Feature(
        f"up_volume_share_{WINDOW}d", "float32", "decimal",
        f"Volume traded on sessions closing above the previous close / total volume, over the "
        f"last {WINDOW} sessions: 0.5 is balanced, above is accumulation, below distribution; a "
        "session closing unchanged counts in the total only",
        f"{_BEFORE_GAP} (the first session needs the close before it); {_NO_VOLUME}",
        valid_range=(0, 1), inputs=(CLOSE, VOLUME),
    ),
    Feature(
        f"cmf_{WINDOW}d", "float32", "decimal",
        f"Chaikin money flow over the last {WINDOW} sessions: sum(mfm x volume) / sum(volume), "
        "mfm = ((close - low) - (high - close)) / (high - low), 0 when high equals low: above 0 "
        "closes sat in the upper half of the day's range on volume",
        f"{_WINDOW_GAP}; {_NO_VOLUME}",
        valid_range=(-1, 1), inputs=(CLOSE, HIGH, LOW, VOLUME),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _bars_in(px: Panel, n: int) -> npt.NDArray[np.bool_]:
    """Per instrument, whether every one of the last ``n`` sessions has a bar."""
    return ~np.isnan(px.close[-n:]).any(axis=0)


def _quotient(part: Matrix, whole: Matrix, known: npt.NDArray[np.bool_]) -> Matrix:
    """``part / whole`` where ``known`` and ``whole`` is above 0, else NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(known & (whole > 0), part / whole, np.nan)


def volume_stats(px: Panel) -> dict[str, Matrix]:
    """Every column for the LAST session of the panel, one value per instrument."""
    close, high, low, volume = px.close, px.high, px.low, px.volume
    window, full = volume[-WINDOW:], _bars_in(px, WINDOW)
    total = window.sum(axis=0)
    base = volume[-WINDOW - 1 : -1]
    flat = base.max(axis=0) == base.min(axis=0)  # exact: never a tiny float stdev
    up = close[-WINDOW:] > close[-WINDOW - 1 : -1]
    span = high[-WINDOW:] - low[-WINDOW:]
    with np.errstate(divide="ignore", invalid="ignore"):
        mfm = np.where(span > 0, ((close - low)[-WINDOW:] - (high - close)[-WINDOW:]) / span, 0.0)
    adv = np.where(full, window.mean(axis=0), np.nan)
    return {
        "session_volume": volume[-1],
        "dollar_volume": close[-1] * volume[-1],
        f"adv_shares_{WINDOW}d": adv,
        f"volume_ratio_{SHORT}d_{WINDOW}d": _quotient(volume[-SHORT:].mean(axis=0), adv, full),
        f"volume_z_{WINDOW}d": _quotient(
            volume[-1] - base.mean(axis=0),
            base.std(axis=0, ddof=1),
            _bars_in(px, WINDOW + 1) & ~flat,
        ),
        f"up_volume_share_{WINDOW}d": _quotient(
            (window * up).sum(axis=0), total, _bars_in(px, WINDOW + 1)
        ),
        f"cmf_{WINDOW}d": _quotient((mfm * window).sum(axis=0), total, full),
    }


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    return traded_rows(px, volume_stats(px), COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Session volume and dollar volume, {WINDOW}-session average volume, the {SHORT} / {WINDOW} "
    "volume ratio, the volume z-score, the up-volume share and Chaikin money flow",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
