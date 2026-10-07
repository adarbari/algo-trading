"""``vol_stats@v1``: the ATR and realised-vol windows beside the catalogue's 14 / 20 / 30, the
realised-vol and volume percentiles against the name's own year, and the 60-session volume
average, from daily bars (``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (272)
earlier sessions. One row per instrument with a bar on the session.

    atr_5, atr_20         Wilder ATR over 5 / 20 (momentum@v1 has 14): the ratio of the two is
                          the volatility expansion (feature.atr_ratio_5_20)
    hv10, hv60            close-to-close realised vol over 10 / 60 log returns, annualised
    hv20_pctile_252d      share of the 252 sessions before the session whose hv20 was strictly
                          below the session's (the realised-vol percentile)
    adv_shares_60d        mean share volume over the last 60 sessions
    volume_pctile_252d    share of the 252 sessions before the session whose volume was
                          strictly below the session's
    pocket_pivot          an up close whose volume exceeds the volume of every down close of
                          the 10 sessions before it (Morales and Kacher's buy point inside a
                          base); false when no down day precedes it

The percentiles need ``MIN_PCTILE`` (240) known sessions of the 252, as the 52-week range
does; the other windows are null on any gap inside them.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.momentum import run_start, wilder
from algotrade.features.rollups.price.price_stats import Matrix, Panel, bars_rows
from algotrade.quant import realized_vol
from algotrade.quant.rolling import trailing_percentile

NAME = "vol_stats"
VERSION = 1
BARS = "bars/1d"
ATR_WINDOWS = (5, 20)
ATR_WARMUP = 150  # sessions the Wilder recursion runs over (at most), as momentum@v1
HV_WINDOWS = (10, 60)
PCTILE_BASE = 20  # the realised vol whose percentile is stored: hv20
PCTILE_WINDOW = 252
MIN_PCTILE = 240
ADV_WINDOW = 60
PIVOT_LOOKBACK = (
    10  # the pocket pivot compares today's volume with the down days of this many sessions before
)
PERIODS_PER_YEAR = 252
LOOKBACK = PCTILE_WINDOW + PCTILE_BASE  # 252 earlier hv20 values of 21 closes each
CLOSE, HIGH, LOW, VOLUME = (f"{BARS}.{c}" for c in ("close", "high", "low", "volume"))


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


def _pctile(what: str) -> str:
    return (
        f"the session's {what} is unknown, or fewer than {MIN_PCTILE} of the {PCTILE_WINDOW} "
        "sessions before it have one"
    )


FEATURES = (
    *(
        Feature(
            f"atr_{n}", "float32", "usd_per_share",
            f"Wilder average true range ({n}): seeded with the mean of the first {n} true "
            f"ranges, then ({n - 1} x ATR + TR) / {n}, over the consecutive bars ending on the "
            f"session (at most the last {ATR_WARMUP} sessions)",
            f"fewer than {n + 1} consecutive bars ending on the session (a gap among the last "
            f"{n + 1} sessions, or a shorter history)",
            valid_range=(0, None), inputs=(HIGH, LOW, CLOSE),
        )
        for n in ATR_WINDOWS
    ),
    *(
        Feature(
            f"hv{n}", "float32", "decimal",
            f"Close-to-close realised volatility: sample stdev of the last {n} log returns x "
            f"sqrt({PERIODS_PER_YEAR})",
            _gap(n + 1), valid_range=(0, 5), inputs=(CLOSE,),
        )
        for n in HV_WINDOWS
    ),
    Feature(
        f"hv{PCTILE_BASE}_pctile_{PCTILE_WINDOW}d", "float32", "decimal",
        f"Share of the {PCTILE_WINDOW} sessions before the session whose {PCTILE_BASE}-session "
        "realised volatility was strictly below the session's: 0.10 means realised vol is in "
        "the calmest tenth of the name's year, 0.90 in the wildest",
        _pctile(f"hv{PCTILE_BASE}"), valid_range=(0, 1), inputs=(CLOSE,),
    ),
    Feature(
        f"adv_shares_{ADV_WINDOW}d", "float32", "shares",
        f"Mean share volume over the last {ADV_WINDOW} sessions, the session included",
        _gap(ADV_WINDOW), valid_range=(0, None), inputs=(VOLUME,),
    ),
    Feature(
        f"volume_pctile_{PCTILE_WINDOW}d", "float32", "decimal",
        f"Share of the {PCTILE_WINDOW} sessions before the session whose share volume was "
        "strictly below the session's: 0.98 means only 2% of the year's sessions traded more",
        _pctile("volume"), valid_range=(0, 1), inputs=(VOLUME,),
    ),
    Feature(
        "pocket_pivot", "bool", "flag",
        "The pocket pivot: the close is above the previous close and the session's volume is "
        f"above the volume of every down-close session among the {PIVOT_LOOKBACK} sessions "
        "before it (Morales and Kacher); false on a down day, or when the last "
        f"{PIVOT_LOOKBACK} sessions had no down close to beat",
        f"{_gap(PIVOT_LOOKBACK + 2)}", inputs=(CLOSE, VOLUME),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def true_range(px: Panel) -> Matrix:
    """Per row: max(high - low, |high - previous close|, |low - previous close|)."""
    prev = np.vstack([np.full((1, px.close.shape[1]), np.nan), px.close[:-1]])
    gap = np.fmax(np.abs(px.high - prev), np.abs(px.low - prev))
    return np.asarray(np.fmax(px.high - px.low, gap))


def atr(px: Panel, period: int) -> Matrix:
    """Wilder ATR for the last row over each column's consecutive run of bars (at most the
    last ``ATR_WARMUP`` rows)."""
    recent = Panel(
        px.ids, *(m[-ATR_WARMUP:] for m in (px.open, px.high, px.low, px.close, px.volume))
    )
    first = run_start(recent.close) + 1  # a true range needs the previous close
    return wilder(true_range(recent), first, period)


def pocket_pivot(px: Panel) -> Matrix:
    """For the last row: 1.0 when the close rose and the volume beats every down day's
    volume of the ``PIVOT_LOOKBACK`` sessions before, 0.0 otherwise, NaN on a gap."""
    close, volume = px.close[-PIVOT_LOOKBACK - 2 :], px.volume[-PIVOT_LOOKBACK - 2 :]
    change = np.diff(close, axis=0)  # PIVOT_LOOKBACK + 1 changes: the window, then today
    down = change[:-1] < 0
    down_volume = np.where(down, volume[1:-1], 0.0).max(axis=0)
    up_today = change[-1] > 0
    flag = up_today & down.any(axis=0) & (volume[-1] > down_volume)
    complete = ~np.isnan(close).any(axis=0)
    return np.where(complete, flag.astype(float), np.nan)


def stats(px: Panel) -> dict[str, Matrix]:
    out: dict[str, Matrix] = {f"atr_{n}": atr(px, n) for n in ATR_WINDOWS}
    for n in HV_WINDOWS:
        out[f"hv{n}"] = realized_vol.close_to_close(px.close[-n - 1 :], n, PERIODS_PER_YEAR)[-1]
    hv_path = realized_vol.close_to_close(px.close, PCTILE_BASE, PERIODS_PER_YEAR)
    pct = f"_pctile_{PCTILE_WINDOW}d"
    out[f"hv{PCTILE_BASE}{pct}"] = trailing_percentile(hv_path, PCTILE_WINDOW, MIN_PCTILE)
    out[f"adv_shares_{ADV_WINDOW}d"] = px.volume[-ADV_WINDOW:].mean(axis=0)
    out[f"volume{pct}"] = trailing_percentile(px.volume, PCTILE_WINDOW, MIN_PCTILE)
    out["pocket_pivot"] = pocket_pivot(px)
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    return bars_rows(inputs, session, LOOKBACK, stats, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Wilder ATR over {ATR_WINDOWS[0]} / {ATR_WINDOWS[1]}, realised vol over {HV_WINDOWS[0]} / "
    f"{HV_WINDOWS[1]}, the hv{PCTILE_BASE} and volume percentiles over {PCTILE_WINDOW} "
    f"sessions, the {ADV_WINDOW}-session volume average and the pocket pivot",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
