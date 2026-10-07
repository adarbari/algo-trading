"""Rolling statistics and trailing runs over sessions x instruments arrays (point in time).

Each function takes an array with sessions on axis 0, oldest first (a 2-d array holds one
series per column), and returns an array of the same shape whose row ``i`` describes the
window ENDING at session ``i``: NaN until the window is full, and NaN for every window that
contains a NaN (a missing session; never a shorter window).

    rolling_mean, rolling_var   mean and sample variance (ddof 1) of the last ``window`` rows
    rolling_max, rolling_min    highest and lowest of the last ``window`` rows
    trailing_run                how many consecutive rows, ending at the last one, satisfy a
                                condition (0 when the last does not; stops at an unknown row)
"""

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

type Array = npt.NDArray[np.float64]
type Mask = npt.NDArray[np.bool_]


def _check_window(window: int, minimum: int) -> None:
    if window < minimum:
        raise ValueError(f"window must be >= {minimum}, got {window}")


def _windows(values: Array, window: int, reduce: str, **kwargs: int) -> Array:
    out = np.full(values.shape, np.nan)
    if values.shape[0] >= window:
        views = sliding_window_view(values, window, axis=0)
        out[window - 1 :] = getattr(views, reduce)(axis=-1, **kwargs)
    return out


def rolling_mean(values: Array, window: int) -> Array:
    """Mean of the last ``window`` rows."""
    _check_window(window, 1)
    return _windows(values, window, "mean")


def rolling_var(values: Array, window: int) -> Array:
    """Sample variance (ddof 1) of the last ``window`` rows."""
    _check_window(window, 2)
    return _windows(values, window, "var", ddof=1)


def rolling_max(values: Array, window: int) -> Array:
    """Highest of the last ``window`` rows (NaN when one is missing)."""
    _check_window(window, 1)
    return _windows(values, window, "max")


def rolling_min(values: Array, window: int) -> Array:
    """Lowest of the last ``window`` rows (NaN when one is missing)."""
    _check_window(window, 1)
    return _windows(values, window, "min")


def trailing_run(holds: Mask, known: Mask) -> npt.NDArray[np.float64]:
    """Per column, how many consecutive rows ending at the last one have ``holds`` true, every
    one of them ``known``: 0 when the last row is known and does not hold, NaN when the last
    row is unknown. An unknown row inside the run ends it (the rows before are not counted)."""
    if holds.shape != known.shape:
        raise ValueError("holds and known must have the same shape")
    alive = (holds & known)[::-1].astype(np.int64)
    run = np.cumprod(alive, axis=0).sum(axis=0).astype(np.float64)
    return np.where(known[-1], run, np.nan)
