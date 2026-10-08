"""``episode_behaviour@v1``: how each instrument behaved against the market, and in the market's
reference crash episodes (docs/market-regime-plan.md 5.7, ADR 0047).

Inputs: ``bars/1d`` split-adjusted as of the session, 252 sessions back (the beta);
``instruments/symbol_ids`` (SPY's id, a lookup only: never built); and ``bars/1d#windows`` (the
closes of each episode's own window: ``Input.windows``). One row per instrument with a bar on
the session.

    beta_252d, corr_252d   OLS slope and correlation of the instrument's daily log returns on
                           SPY's over the trailing 252 sessions, on the sessions where both
                           returns exist (a return needs a bar on two consecutive sessions);
                           null with fewer than ``MIN_RETURNS`` (200) such returns, or no SPY
    dd_<key>               the worst fall of the instrument's close from its own running high
                           between the episode's window start and its ``trough`` (fraction,
                           negative), looked at on the sessions from the ``peak`` to the
                           trough (``quant.turning_points.drawdowns``): the running high starts
                           ``LEAD`` sessions before the peak, since a name can top out a few
                           sessions before the index
    recovery_sessions_<key>  sessions from the trough until a close first regained the
                           pre-episode high (the highest close from the window start to the
                           peak); 0 when the trough itself is at or above it

A column is null before the episode's ``known_from`` (its trough: no feature may know an
episode's depth before it ended), and for an instrument with fewer than ``MIN_COVERAGE`` (80%)
of the sessions from the peak to the trough on file (a later listing, a thin name). Recovery is
also null while the close has not regained the high, and stays null if that takes more than
``HORIZON`` (400) sessions after the trough: the window ends there, so the group reads a few
hundred sessions of closes, never the years in between. An episode before the bars we hold has
no rows in its window: every column of it is null.

The episodes are CODE CONSTANTS (``EPISODES``): a new episode is a new column and a new group
version, and a test checks the dates against ``config/site/regime/episodes.toml``. The windows
and thresholds are part of the definition: changing one is a new version.

Once the episode and its horizon are past, its columns never change, yet the nightly
recomputes them (the framework runs every group each session; a group has no cadence of its
own, ADR 0039). The cost is bounded by the window reads: closes only, one window at a time.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_between, sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import (
    BARS,
    CLOSE,
    panel,
    symbol_column,
    traded_rows,
)
from algotrade.quant.turning_points import drawdowns

type Matrix = npt.NDArray[np.float64]

NAME = "episode_behaviour"
VERSION = 1
SYMBOLS = "instruments/symbol_ids"
BETA_SESSIONS = 252  # returns in the beta window (one more close)
MIN_RETURNS = 200  # overlapping returns needed for beta and correlation
LEAD = 5  # sessions before the peak where an episode's window (and its running high) starts
HORIZON = 400  # sessions after the trough where an episode's window ends
MIN_COVERAGE = 0.8  # share of the sessions from peak to trough an instrument needs a bar on


@dataclass(frozen=True)
class Episode:
    """One reference episode: its key (the column suffix, the ``episodes.toml`` key) and its
    closing-basis S&P 500 ``peak`` and ``trough`` sessions (``known_from`` is the trough)."""

    key: str
    peak: date
    trough: date

    @cached_property
    def first(self) -> date:
        """The window's first session: ``LEAD`` sessions before the peak."""
        return sessions_ending(self.peak, LEAD + 1)[0]

    @cached_property
    def last(self) -> date:
        """The window's last session: ``HORIZON`` sessions after the trough."""
        return sessions_between(self.trough, self.trough + timedelta(days=2 * HORIZON))[HORIZON]


EPISODES = (
    Episode("covid_2020", date(2020, 2, 19), date(2020, 3, 23)),
    Episode("hikes_2022", date(2022, 1, 3), date(2022, 10, 12)),
    Episode("tariffs_2025", date(2025, 2, 19), date(2025, 4, 8)),
)
WINDOWS = tuple((e.first, e.last) for e in EPISODES)
CLOSES = Input(BARS, windows=WINDOWS, required=False).key  # the key of the windows frame

_SPY = "bars/1d.close of SPY"
_BETA_NULL = (
    f"SPY is not in the reference or has no bars, or fewer than {MIN_RETURNS} of the last "
    f"{BETA_SESSIONS} sessions have a return for both (a gap, a young listing)"
)


def _episode_null(e: Episode) -> str:
    return (
        f"the session is before the {e.key} trough ({e.trough}: the earliest it is known), "
        f"the instrument has fewer than {MIN_COVERAGE:.0%} of the sessions from the peak "
        f"({e.peak}) to the trough on file, or the stored bars do not reach the episode"
    )


FEATURES = (
    Feature(
        f"beta_{BETA_SESSIONS}d", "float32", "ratio",
        f"OLS beta of the daily log returns on SPY's over the trailing {BETA_SESSIONS} sessions",
        _BETA_NULL, valid_range=(-10, 10), inputs=(CLOSE, f"{SYMBOLS}.symbol"),
    ),
    Feature(
        f"corr_{BETA_SESSIONS}d", "float32", "ratio",
        f"Correlation of the daily log returns with SPY's over the trailing {BETA_SESSIONS} "
        "sessions",
        _BETA_NULL, valid_range=(-1, 1), inputs=(CLOSE, f"{SYMBOLS}.symbol"),
    ),
    *(
        Feature(
            f"dd_{e.key}", "float32", "decimal",
            f"The worst close-to-close fall from the instrument's own high in the {e.key} "
            f"episode ({e.peak} to {e.trough}), negative",
            _episode_null(e), valid_range=(-1, 0), inputs=(CLOSE,),
        )
        for e in EPISODES
    ),
    *(
        Feature(
            f"recovery_sessions_{e.key}", "int", "sessions",
            f"Sessions from the {e.trough} trough until the close first regained the "
            f"pre-episode high ({e.key})",
            f"the close has not yet regained the pre-episode high, or not within {HORIZON} "
            "sessions of the trough (not recovered: not a failure to compute), or "
            + _episode_null(e),
            valid_range=(0, None), inputs=(CLOSE,),
        )
        for e in EPISODES
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _log_returns(close: Matrix) -> Matrix:
    with np.errstate(divide="ignore", invalid="ignore"):
        levels = np.where(close > 0, np.log(close), np.nan)
    return levels[1:] - levels[:-1]


def beta_corr(close: Matrix, market: int | None) -> tuple[Matrix, Matrix]:
    """(beta, correlation) per column of a sessions x instruments close matrix against column
    ``market``, over the sessions where both returns exist; NaN under ``MIN_RETURNS`` of them."""
    n_ids = close.shape[1]
    if market is None:
        return np.full(n_ids, np.nan), np.full(n_ids, np.nan)
    r = _log_returns(close)
    rm = r[:, [market]]
    both = np.isfinite(r) & np.isfinite(rm)
    n = both.sum(axis=0)
    enough = n >= MIN_RETURNS
    count = np.where(enough, n, 1)
    x = np.where(both, r, 0.0)
    m = np.where(both, rm, 0.0)
    x = np.where(both, x - x.sum(axis=0) / count, 0.0)  # centred on the overlapping sessions
    m = np.where(both, m - m.sum(axis=0) / count, 0.0)
    sxm, sxx, smm = (x * m).sum(axis=0), (x * x).sum(axis=0), (m * m).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = np.where(enough & (smm > 0), sxm / smm, np.nan)
        corr = np.where(enough & (smm > 0) & (sxx > 0), sxm / np.sqrt(sxx * smm), np.nan)
    return beta, np.clip(corr, -1.0, 1.0)


def _window_matrix(
    closes: pd.DataFrame, index: int, e: Episode, session: date, ids: npt.NDArray[np.str_]
) -> Matrix:
    """The episode's closes up to the session as a sessions x instruments matrix over the
    exchange sessions of its window (NaN: no bar, or an instrument with none today)."""
    rows = closes[closes["window"].to_numpy() == index]
    grid = pd.DatetimeIndex(sessions_between(e.first, min(session, e.last)))
    out = np.full((len(grid), len(ids)), np.nan)
    ids_here = rows["instrument_id"]
    column = pd.Index(ids).get_indexer(ids_here.cat.categories)[ids_here.cat.codes.to_numpy()]
    day = grid.get_indexer(pd.DatetimeIndex(rows["day"]))
    keep = (column >= 0) & (day >= 0)
    out[day[keep], column[keep]] = rows["close"].to_numpy()[keep]
    return out


def episode_columns(
    closes: pd.DataFrame | None, index: int, e: Episode, session: date, ids: npt.NDArray[np.str_]
) -> tuple[Matrix, Matrix]:
    """(drawdown, recovery sessions) per instrument for episode ``e`` (NaN: UNKNOWN)."""
    drawdown, recovery = np.full(len(ids), np.nan), np.full(len(ids), np.nan)
    if closes is None or session < e.trough:
        return drawdown, recovery
    grid = sessions_between(e.first, min(session, e.last))
    if e.peak not in grid or e.trough not in grid:
        return drawdown, recovery  # the window is empty before the episode: nothing stored
    px = _window_matrix(closes, index, e, session, ids)
    peak, trough = grid.index(e.peak), grid.index(e.trough)
    seen = np.isfinite(px[peak : trough + 1]).sum(axis=0)
    covered = seen >= MIN_COVERAGE * (trough - peak + 1)
    with np.errstate(invalid="ignore"):
        high = np.fmax.reduce(px[: peak + 1], axis=0)  # all-NaN columns stay NaN
        reached = px[trough:] >= high
    for j in np.flatnonzero(covered):
        series = px[: trough + 1, j]
        present = np.flatnonzero(np.isfinite(series) & (series > 0))
        depth = drawdowns(series[present])[present >= peak]
        drawdown[j] = depth.min()
        if reached[:, j].any():
            recovery[j] = int(reached[:, j].argmax())
    return drawdown, recovery


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, BETA_SESSIONS + 1))
    beta, corr = beta_corr(px.close, symbol_column(inputs[SYMBOLS], px.ids))
    values: dict[str, Matrix] = {f"beta_{BETA_SESSIONS}d": beta, f"corr_{BETA_SESSIONS}d": corr}
    for index, e in enumerate(EPISODES):
        values[f"dd_{e.key}"], values[f"recovery_sessions_{e.key}"] = episode_columns(
            inputs[CLOSES], index, e, session, px.ids
        )
    frame = traded_rows(px, values, COLUMNS)
    for e in EPISODES:  # whole sessions, null where unknown
        name = f"recovery_sessions_{e.key}"
        frame[name] = frame[name].astype("Int64")
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Beta and correlation against SPY, and each reference episode's drawdown and recovery",
    (
        Input(BARS, lookback=BETA_SESSIONS),
        Input(SYMBOLS, required=False),
        Input(BARS, windows=WINDOWS, required=False),
    ),
    FEATURES,
    compute,
)
