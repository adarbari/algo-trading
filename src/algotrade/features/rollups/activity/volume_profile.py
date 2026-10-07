"""``volume_profile@v1``: volume at price from daily bars over the last year: the point of
control, the value area, and the nearest high- and low-volume nodes above and below the close
(``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``WINDOW - 1`` (251)
earlier sessions, and ``momentum@v1`` for the session (``atr_14``, for the share of volume
near the close). One row per instrument with a bar on the session.

This is a DAILY-BAR approximation of a volume profile: each bar's volume is spread evenly
over the price bins its high-low range covers (``bins`` equal bins between the window's lowest
low and highest high); an intraday profile would place it where it traded. Read the nodes as
zones a few bins wide, not exact prices.

    profile_status           OK, FEW_BARS (fewer than min_bars bars in the window), NO_RANGE
                             (every bar at one price)
    poc_252d                 the centre of the bin with the most volume (ties: nearest the close)
    value_area_high / _low   the edges of the smallest run of bins around the point of control
                             holding value_area (70%) of the volume
    hvn_above / hvn_below    the centre of the nearest bin above / below the close's bin whose
                             volume is at least hvn_factor (1.5) x the mean bin volume
    lvn_above / lvn_below    ... at most lvn_factor (0.5) x the mean bin volume
    volume_near_close_share  share of the window's volume in bins whose centre is within one
                             atr_14 of the close

Parameters: ``VolumeProfileParams`` (``config/site/rollups.toml ["volume_profile@v1"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, panel, traded_rows

type Mask = npt.NDArray[np.bool_]

NAME = "volume_profile"
VERSION = 1
BARS = "bars/1d"
MOMENTUM = "rollups/instrument/momentum@v1"
WINDOW = 252
STATUSES = ("OK", "FEW_BARS", "NO_RANGE")
HIGH, LOW, CLOSE, VOLUME = (f"{BARS}.{c}" for c in ("high", "low", "close", "volume"))
_INPUTS = (HIGH, LOW, CLOSE, VOLUME)
_NOT_OK = "profile_status is not OK (fewer than min_bars bars in the window, or no price range)"


def _node(kind: str, side: str, factor: str) -> Feature:
    return Feature(
        f"{kind}_{side}", "float32", "usd_per_share",
        f"The centre of the nearest price bin {side} the close's bin whose volume over the last "
        f"{WINDOW} sessions is {factor} the mean bin volume: the nearest "
        f"{'high' if kind == 'hvn' else 'low'}-volume node {side} the price",
        f"no such bin {side} the close in the window's range, or {_NOT_OK}",
        valid_range=(0, None), inputs=_INPUTS,
    )  # fmt: skip


FEATURES = (
    Feature(
        "profile_status", "str", "category",
        "OK: the profile is computed; FEW_BARS: fewer than min_bars (240) bars among the last "
        f"{WINDOW} sessions; NO_RANGE: every bar in the window at one price",
        "never", kind="label", categories=STATUSES, inputs=_INPUTS,
    ),
    Feature(
        f"poc_{WINDOW}d", "float32", "usd_per_share",
        f"Point of control: the centre of the price bin with the most volume over the last "
        f"{WINDOW} sessions (each bar's volume spread evenly over the bins its range covers; "
        "ties: the bin nearest the close)",
        _NOT_OK, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "value_area_high", "float32", "usd_per_share",
        "The top edge of the value area: the smallest run of bins around the point of control "
        "holding value_area (70%) of the window's volume, grown one bin at a time towards the "
        "neighbour with more volume",
        _NOT_OK, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "value_area_low", "float32", "usd_per_share",
        "The bottom edge of the value area", _NOT_OK, valid_range=(0, None), inputs=_INPUTS,
    ),
    _node("hvn", "above", "at least hvn_factor (1.5) x"),
    _node("hvn", "below", "at least hvn_factor (1.5) x"),
    _node("lvn", "above", "at most lvn_factor (0.5) x"),
    _node("lvn", "below", "at most lvn_factor (0.5) x"),
    Feature(
        "volume_near_close_share", "float32", "decimal",
        f"Share of the last {WINDOW} sessions' volume in bins whose centre is within one "
        "atr_14 of the close: 0.30 means the name has traded nearly a third of its year within "
        "a day's range of here (a heavily traded level)",
        f"atr_14 is null (no momentum row, or fewer than 15 consecutive bars), or {_NOT_OK}",
        valid_range=(0, 1), inputs=(*_INPUTS, "momentum.atr_14@v1"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class VolumeProfileParams:
    bins: int = 50  # price bins between the window's lowest low and highest high
    value_area: float = 0.70  # share of the volume the value area holds
    hvn_factor: float = 1.5  # a bin at or above this x the mean bin volume is a high-volume node
    lvn_factor: float = 0.5  # ... at or below this x the mean is a low-volume node
    min_bars: int = 240  # bars needed in the window

    def __post_init__(self) -> None:
        if self.bins < 5:
            raise ValueError(f"bins must be >= 5, got {self.bins}")
        if not 0 < self.value_area < 1:
            raise ValueError(f"value_area must be in (0, 1), got {self.value_area}")
        if not 0 < self.lvn_factor < 1 <= self.hvn_factor:
            raise ValueError("need 0 < lvn_factor < 1 <= hvn_factor")
        if not 1 <= self.min_bars <= WINDOW:
            raise ValueError(f"min_bars must be 1..{WINDOW}, got {self.min_bars}")


def histogram(px: Panel, p: VolumeProfileParams) -> tuple[Matrix, Matrix, Matrix]:
    """``(volume_by_bin, lower_edge, width)``: instruments x bins volume, with each bar's
    volume spread evenly over the bins its [low, high] overlaps (a bar with no range goes to
    its bin); the lower edge and bin width per instrument (NaN width: no range)."""
    lo = np.nanmin(px.low, axis=0)
    hi = np.nanmax(px.high, axis=0)
    span = hi - lo
    width = np.where(span > 0, span / p.bins, np.nan)
    edges = lo[:, None] + width[:, None] * np.arange(p.bins + 1)[None, :]  # N x (bins + 1)
    out = np.zeros((len(px.ids), p.bins))
    for row in range(len(px.close)):
        bar_lo, bar_hi, vol = px.low[row], px.high[row], px.volume[row]
        has = ~np.isnan(bar_lo) & ~np.isnan(vol) & (vol > 0) & (span > 0)
        if not has.any():
            continue
        overlap = np.minimum(edges[:, 1:], bar_hi[:, None]) - np.maximum(
            edges[:, :-1], bar_lo[:, None]
        )
        overlap = np.clip(overlap, 0, None)
        length = overlap.sum(axis=1)
        point = (bar_hi - bar_lo) <= 0  # a bar at one price: all of it in that bin
        with np.errstate(invalid="ignore"):
            offset = np.where(has, (bar_lo - lo) / width, 0.0)
        idx = np.clip(np.nan_to_num(offset).astype(np.int64), 0, p.bins - 1)
        weights = np.where(
            length[:, None] > 0, overlap / np.where(length > 0, length, 1)[:, None], 0.0
        )
        weights[point & has] = 0.0
        weights[np.arange(len(lo))[point & has], idx[point & has]] = 1.0
        out += np.where(has[:, None], weights * np.nan_to_num(vol)[:, None], 0.0)
    return out, lo, width


def value_area(
    volume: Matrix, poc: npt.NDArray[np.int64], share: float
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """Per instrument: the lowest and highest bin index of the run around ``poc`` holding
    ``share`` of the volume, grown one bin at a time towards the larger neighbour."""
    n, bins = volume.shape
    lo = poc.copy()
    hi = poc.copy()
    rows = np.arange(n)
    total = volume.sum(axis=1)
    held = volume[rows, poc].copy()
    for _ in range(bins):
        need = held < share * total
        below = np.where(lo > 0, volume[rows, np.maximum(lo - 1, 0)], -1.0)
        above = np.where(hi < bins - 1, volume[rows, np.minimum(hi + 1, bins - 1)], -1.0)
        can = need & ((below >= 0) | (above >= 0))
        take_above = can & (above >= below)
        take_below = can & ~take_above
        held = np.where(take_above, held + above, np.where(take_below, held + below, held))
        hi = np.where(take_above, hi + 1, hi)
        lo = np.where(take_below, lo - 1, lo)
    return lo, hi


def nearest(volume: Matrix, at: npt.NDArray[np.int64], above: bool, mask: Mask) -> Matrix:
    """Per instrument: the index of the nearest bin strictly above / below ``at`` where
    ``mask`` is true (NaN: none)."""
    bins = volume.shape[1]
    idx = np.arange(bins)[None, :]
    side = idx > at[:, None] if above else idx < at[:, None]
    hit = mask & side  # both boolean
    distance = np.where(hit, np.abs(idx - at[:, None]), bins + 1)
    best = distance.argmin(axis=1)
    return np.where(hit.any(axis=1), best, np.nan)


def profile(px: Panel, atr: Matrix, p: VolumeProfileParams) -> dict[str, object]:
    volume, lo, width = histogram(px, p)
    n, bins = volume.shape
    rows = np.arange(n)
    bars = (~np.isnan(px.close)).sum(axis=0)
    ok = (bars >= p.min_bars) & ~np.isnan(width)
    status = np.where(bars < p.min_bars, "FEW_BARS", np.where(np.isnan(width), "NO_RANGE", "OK"))
    safe_width = np.where(ok, width, 1.0)
    with np.errstate(invalid="ignore"):
        close_bin = np.clip(
            np.nan_to_num((px.close[-1] - lo) / safe_width).astype(np.int64), 0, bins - 1
        )
    centre = lo[:, None] + safe_width[:, None] * (np.arange(bins)[None, :] + 0.5)
    # the point of control: the fullest bin, ties to the one nearest the close
    peak = volume.max(axis=1)
    is_peak = volume >= peak[:, None]
    distance = np.where(is_peak, np.abs(np.arange(bins)[None, :] - close_bin[:, None]), bins + 1)
    poc = distance.argmin(axis=1)
    va_lo, va_hi = value_area(volume, poc, p.value_area)
    mean = volume.mean(axis=1)[:, None]
    hvn = volume >= p.hvn_factor * mean
    lvn = volume <= p.lvn_factor * mean

    def at(index: Matrix) -> Matrix:
        has = ~np.isnan(index) & ok
        picked = centre[rows, np.where(has, index, 0).astype(np.int64)]
        return np.where(has, picked, np.nan)

    near = np.abs(centre - px.close[-1][:, None]) <= atr[:, None]
    total = volume.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        near_share = np.where(
            ok & (total > 0) & ~np.isnan(atr), (volume * near).sum(axis=1) / total, np.nan
        )
    return {
        "profile_status": status,
        f"poc_{WINDOW}d": np.where(ok, centre[rows, poc], np.nan),
        "value_area_high": np.where(ok, lo + safe_width * (va_hi + 1), np.nan),
        "value_area_low": np.where(ok, lo + safe_width * va_lo, np.nan),
        "hvn_above": at(nearest(volume, close_bin, True, hvn)),
        "hvn_below": at(nearest(volume, close_bin, False, hvn)),
        "lvn_above": at(nearest(volume, close_bin, True, lvn)),
        "lvn_below": at(nearest(volume, close_bin, False, lvn)),
        "volume_near_close_share": near_share,
    }


def compute(inputs: Inputs, session: date, p: VolumeProfileParams) -> pd.DataFrame:
    bars, momentum = inputs[BARS], inputs[MOMENTUM]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW))
    atr = np.full(len(px.ids), np.nan)
    if momentum is not None and not momentum.empty:
        known = momentum.set_index(momentum["instrument_id"].astype(str))["atr_14"]
        atr = known.reindex(px.ids).to_numpy(dtype=float)
    return traded_rows(px, profile(px, atr, p), COLUMNS)  # type: ignore[arg-type]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Volume at price over the last {WINDOW} sessions from daily bars: point of control, value "
    "area, the nearest high- and low-volume nodes above and below the close, and the share of "
    "volume within an ATR of the close",
    (Input(BARS, lookback=WINDOW - 1), Input(MOMENTUM, required=False)),
    FEATURES,
    compute,
    params=VolumeProfileParams(),
)
