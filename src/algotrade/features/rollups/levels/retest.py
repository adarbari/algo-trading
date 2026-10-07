"""``retest@v1``: the latest 20-session breakout, whether it was retested and held, and how
many breakouts of the last year failed (``docs/data/swing.md``).

Inputs: ``bars/1d`` split-adjusted AS OF the session (the session plus ``LOOKBACK`` (291)
earlier sessions) and the session's stored ``momentum@v1`` rows (``atr_14``, the tolerance's
unit). One row per instrument with a bar on the session.

A **breakout session** b is one whose close is above the highest high of the 20 sessions
before b (``momentum.prior_high_20d`` as of b: its level), every one of them with a bar.

    breakout_date, breakout_level, sessions_since_breakout
                    the most recent breakout session among the last ``search_sessions`` (60,
                    the session included), its level and the sessions since it (0: today)
    retest_state    first match: NONE (no breakout in the window); FAILED (a close after b,
                    through the session, below the level); NO_ATR (``atr_14`` is null, so the
                    tolerance is unknown); RETESTING (the session is after b, its low is at or
                    below ``level + retest_atr x atr_14`` and its close at or above the
                    level); HELD (an earlier session after b had such a low); FRESH (none did)
    failed_breakouts_252d
                    over the last 252 sessions, the first sessions of runs of consecutive
                    breakout sessions whose close fell below their level within the next
                    ``fail_sessions`` (20) sessions; a breakout too recent to have run its 20
                    sessions that has not failed is pending and not counted. Null unless
                    all ``LOOKBACK + 1`` bars exist (a gap among them, or a shorter history)

Parameters: ``RetestParams`` (``config/site/rollups.toml ["retest@v1"]``). The 20-session
prior-high window and the 252-session count are named in the columns: changing them is a new
version.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, panel, traded_rows

NAME = "retest"
VERSION = 1
BARS = "bars/1d"
MOMENTUM = "rollups/instrument/momentum@v1"
PRIOR = 20  # sessions before a breakout whose highest high its close must clear
YEAR = 252  # sessions counted for failed_breakouts_252d
LOOKBACK = 291  # earlier sessions read: 292 bars
STATES = ("FAILED", "NONE", "RETESTING", "HELD", "FRESH", "NO_ATR")

CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("close", "high", "low"))
_NONE = "no breakout session among the last search_sessions (60) sessions (retest_state NONE)"


@dataclass(frozen=True)
class RetestParams:
    search_sessions: int = 60  # sessions searched for the latest breakout, today included
    retest_atr: float = 0.5  # how near the level a low must come to retest it, in ATRs
    fail_sessions: int = 20  # sessions after a breakout in which a close below its level fails it

    def __post_init__(self) -> None:
        if not 1 <= self.search_sessions <= LOOKBACK + 1 - PRIOR:
            raise ValueError(f"search_sessions must be between 1 and {LOOKBACK + 1 - PRIOR}")
        if not self.retest_atr > 0:
            raise ValueError(f"retest_atr must be > 0, got {self.retest_atr}")
        if not 1 <= self.fail_sessions <= YEAR:
            raise ValueError(f"fail_sessions must be between 1 and {YEAR}")


FEATURES = (
    Feature(
        "breakout_date", "date", "date",
        f"The session of the most recent breakout among the last 60: a close above the highest "
        f"high of the {PRIOR} sessions before it",
        _NONE, inputs=(HIGH, CLOSE),
    ),
    Feature(
        "breakout_level", "float32", "usd_per_share",
        f"The highest high of the {PRIOR} sessions before that breakout (what its close cleared)",
        _NONE, valid_range=(0, None), inputs=(HIGH, CLOSE),
    ),
    Feature(
        "sessions_since_breakout", "int", "sessions",
        "Exchange sessions from that breakout to the session (0: the breakout is today)",
        _NONE, valid_range=(0, LOOKBACK), inputs=(HIGH, CLOSE),
    ),
    Feature(
        "retest_state", "str", "category",
        "FAILED (a close after the breakout, through the session, is below its level), NONE "
        "(no breakout in the last 60 sessions), NO_ATR (atr_14 unknown), RETESTING (the "
        "session's low is at or below the level + 0.5 x atr_14 and its close at or above the "
        "level), HELD (an earlier session after the breakout had such a low), FRESH (price "
        "has not come back to the level); the breakout session itself is never a retest",
        "never", "label", categories=STATES,
        inputs=(HIGH, LOW, CLOSE, "momentum.atr_14@v1"),
    ),
    Feature(
        "failed_breakouts_252d", "int", "count",
        f"Breakouts of the last {YEAR} sessions (the first session of each run of consecutive "
        "breakout sessions) whose close fell below their level within the next 20 sessions; "
        "one that has not failed and is under 20 sessions old is pending and not counted",
        f"a session among the last {LOOKBACK + 1} has no bar (a gap), or the history is shorter",
        valid_range=(0, YEAR), inputs=(HIGH, CLOSE),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def breakouts(high: Matrix, close: Matrix) -> tuple[npt.NDArray[np.bool_], Matrix]:
    """Sessions x instruments: whether each session's close is above the highest high of the
    ``PRIOR`` sessions before it, and that level (NaN where there are fewer than ``PRIOR``
    sessions before it, or one has no bar)."""
    n = len(high)
    prior = high[: n - PRIOR].copy()
    for j in range(1, PRIOR):
        prior = np.maximum(prior, high[j : n - PRIOR + j])  # NaN propagates: a gap voids it
    level = np.full(high.shape, np.nan)
    level[PRIOR:] = prior
    with np.errstate(invalid="ignore"):
        return close > level, level


def failed_after(close: Matrix, level: Matrix, sessions: int) -> npt.NDArray[np.bool_]:
    """Sessions x instruments: whether a close within the next ``sessions`` sessions (the
    last ones may have fewer left) is below the row's level (NaN: no level, never)."""
    n = len(close)
    ahead = np.vstack([close, np.full((sessions, close.shape[1]), np.inf)])
    failed = np.zeros(close.shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        for j in range(1, sessions + 1):
            failed |= ahead[j : j + n] < level
    return failed


def failures(
    is_break: npt.NDArray[np.bool_], level: Matrix, close: Matrix, p: RetestParams
) -> Matrix:
    """Per column, the failed breakouts among the last ``YEAR`` sessions (NaN on a gap)."""
    starts = is_break.copy()
    starts[1:] &= ~is_break[:-1]
    count = (starts & failed_after(close, level, p.fail_sessions))[-YEAR:].sum(axis=0)
    return np.where(np.isnan(close).any(axis=0), np.nan, count)


def compute(inputs: Inputs, session: date, p: RetestParams) -> pd.DataFrame:
    bars, momentum = inputs[BARS], inputs[MOMENTUM]
    assert bars is not None and momentum is not None  # required inputs
    days = sessions_ending(session, LOOKBACK + 1)
    px = panel(bars, days)
    n, cols = len(days), np.arange(px.close.shape[1])
    today = momentum[momentum["session_date"] == session]
    atr = pd.Series(today["atr_14"].to_numpy(dtype=np.float64), index=today["instrument_id"])
    tol = p.retest_atr * atr.reindex(px.ids).to_numpy(dtype=np.float64)

    is_break, level = breakouts(px.high, px.close)
    recent = is_break[-p.search_sessions :]
    found = recent.any(axis=0)
    row = n - 1 - np.argmax(recent[::-1], axis=0)  # the latest breakout session
    where = level[row, cols]
    after = np.arange(n)[:, None] > row  # sessions after the breakout, the session included
    before_today = after & (np.arange(n)[:, None] < n - 1)
    with np.errstate(invalid="ignore"):
        failed = ((px.close < where) & after).any(axis=0)
        retesting = (row < n - 1) & (px.low[-1] <= where + tol) & (px.close[-1] >= where)
        held = ((px.low <= where + tol) & before_today).any(axis=0)
    state = np.where(
        ~found, "NONE",
        np.where(failed, "FAILED",
        np.where(np.isnan(tol), "NO_ATR",
        np.where(retesting, "RETESTING", np.where(held, "HELD", "FRESH")))),
    )  # fmt: skip
    values = {
        "breakout_date": np.array(
            [days[r] if ok else None for r, ok in zip(row, found, strict=True)], dtype=object
        ),
        "breakout_level": np.where(found, where, np.nan),
        "sessions_since_breakout": np.where(found, n - 1 - row, np.nan),
        "retest_state": state.astype(object),
        "failed_breakouts_252d": failures(is_break, level, px.close, p),
    }
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The latest 20-session breakout of the last 60 sessions, its level, whether it was "
    "retested (within 0.5 ATR) and held or failed, and the failed breakouts of the last year",
    (Input(BARS, lookback=LOOKBACK), Input(MOMENTUM)),
    FEATURES,
    compute,
    RetestParams(),
)
