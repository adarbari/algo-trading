"""The ``pit = "lag"`` rule (ADR 0048): the vintage date of a value that is never revised.

ALFRED dates every vintage of a revised series (``realtime_start``). An unrevised series (a
market close, a spread) and observations before ALFRED's first vintage have no such date: the
value is taken as public ``release_lag_days`` calendar days after its observation date
(``config/site/macro.toml``) and flagged ``lagged``, so a reader can say which values relied on
the rule. Pure: the ingestion task (``tasks/macro``) calls it before writing ``macro/series``.
"""

import pandas as pd

from algotrade.storage.tables.schemas import LAGGED


def lagged_vintages(observations: pd.DataFrame, release_lag_days: int) -> pd.DataFrame:
    """``observations`` (an ``obs_date`` column, any others kept) with ``vintage_date`` =
    ``obs_date`` + ``release_lag_days`` and ``vintage_kind`` = ``lagged``; dates as ``date``.
    One vintage per observation per call: when a later fetch of a ``lagged`` key brings a
    different value, the writer stores it as a NEW vintage dated the run's session, never as an
    overwrite of the stored one (a session before the run must still see the old value)."""
    if release_lag_days < 0:
        raise ValueError(f"release_lag_days must be >= 0, got {release_lag_days}")
    out = observations.copy()
    obs = pd.to_datetime(out["obs_date"])
    out["obs_date"] = obs.dt.date
    out["vintage_date"] = (obs + pd.Timedelta(days=release_lag_days)).dt.date
    out["vintage_kind"] = LAGGED
    return out
