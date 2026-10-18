"""``analyst_revisions@v1``: how the consensus for the current fiscal year has moved.

Inputs: ``analyst_estimates@v1`` for the session (FY1 as the session knows it: its year end, EPS,
revenue and analyst count) and ``analyst/estimate_snapshots`` as the session sees it (our own
nightly history of FMP's annual estimates: ``data.analyst.reading``). One row per name whose
estimates are served (``estimates_status`` OK): a name the vendor does not cover, one never asked
and one whose snapshot is STALE have no row. ``licence = "personal"`` on every feature (ADR 0068,
ADR 0069).

    eps_fy1_revision_30d, _60d, _90d      (EPS of FY1 now - EPS of the same year N days ago) /
                                          |EPS then|, in percent
    revenue_fy1_revision_30d, _90d        the same for revenue
    eps_fy1_analysts_change_90d           analysts behind the EPS now less 90 days ago
    revisions_status                      OK / BUILDING / NO_PRIOR

A past value is the same fiscal YEAR in an earlier snapshot: the estimate row whose year end is
within ``PERIOD_SLACK`` (10) days of FY1's year end, in the latest snapshot for a session from
``N + SNAPSHOT_SLACK`` (7) to ``N`` days before this one that holds such a row. Never matched on
the ``FY1`` label: when the 10-K makes FY1 the next year the year end moves by a year, nothing
matches and the revisions are null, not a jump. A 52 or 53 week year whose date moved by days
still matches. Only snapshots for a session on or before this one are read (the reader hides the
ones published after the next open), and only our own: never a vendor history.

    OK         a snapshot of the same year exists for every window (30, 60 and 90 days)
    BUILDING   an earlier snapshot of the year exists, but not for every window: the history is
               still short, or a night was missed
    NO_PRIOR   no earlier snapshot of this year: it only now appears, or FY1 has no year end

The history starts at our first snapshot (2026-10-19 at the earliest), so the 30-day columns are
null until about 2026-11-18 and the 90-day ones until about 2027-01-17. A revision is null when
the old value is missing or smaller than ``MIN_BASE`` (the shared floor of
``earnings_revisions@v1``: a percent of nearly nothing), whatever the status; a loss-maker's
negative base counts by its size. The windows, the slacks, the floor and matching by year end are
part of the definition: changing one is a new version. There is no 7-day window: a covered name
is refreshed about weekly.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.consensus.analyst_status import (
    ESTIMATES,
    HISTORY_LOOKBACK,
    OK,
    SNAPSHOTS,
    VENDOR,
    days_back,
    history_rows,
)
from algotrade.features.rollups.consensus.earnings_surprise import MIN_BASE, change_pct

NAME = "analyst_revisions"
VERSION = 1
ESTIMATES_TABLE = "rollups/instrument/analyst_estimates@v1"
BUILDING, NO_PRIOR = "BUILDING", "NO_PRIOR"
STATUSES = (OK, BUILDING, NO_PRIOR)
WINDOWS = (30, 60, 90)  # calendar days back
PERIOD_SLACK = 10  # days: a year end this close to FY1's is the same fiscal year
_P: Licence = "personal"
_SNAP = f"{SNAPSHOTS}."
_EST = "analyst_estimates."
_PCT = (-10000.0, 10000.0)  # percent: a small base makes huge revisions, kept and flagged
_FROM = "2026-10-19"  # our first snapshot at the earliest
_NO_ROW = (
    "the name has no row: the vendor has no current estimates for it (not covered, never asked "
    "or STALE)"
)


def _null(days: int) -> str:
    return (
        f"{_NO_ROW}; or no snapshot of ours holds the same fiscal year {days} days back (our "
        f"history starts {_FROM}); or the old value is missing or below {MIN_BASE}"
    )


def _revision(name: str, days: int, what: str, now: str, then: str) -> Feature:
    return Feature(
        f"{name}_fy1_revision_{days}d", "float32", "pct_points",
        f"Change of the first estimate year's {what} over {days} days, in percent of the old "
        f"value: 5 is an estimate 5% higher than {days} days ago, same fiscal year",
        _null(days), valid_range=_PCT,
        inputs=(f"{_EST}{now}@v1", f"{_EST}fy1_period_end@v1", f"{_SNAP}{then}", f"{_SNAP}period"),
        licence=_P,
    )  # fmt: skip


FEATURES = (
    _revision("eps", 30, "EPS estimate", "eps_fy1", "eps_avg"),
    _revision("eps", 60, "EPS estimate", "eps_fy1", "eps_avg"),
    _revision("eps", 90, "EPS estimate", "eps_fy1", "eps_avg"),
    _revision("revenue", 30, "revenue estimate", "revenue_fy1", "revenue_avg"),
    _revision("revenue", 90, "revenue estimate", "revenue_fy1", "revenue_avg"),
    Feature(
        "eps_fy1_analysts_change_90d", "int", "count",
        "How many analysts' estimates the first year's EPS averages now less 90 days ago for "
        "the same fiscal year: positive is more analysts covering",
        _null(90).replace(f" or below {MIN_BASE}", " or no count"), valid_range=(-1000, 1000),
        inputs=(
            f"{_EST}eps_fy1_analysts@v1",
            f"{_EST}fy1_period_end@v1",
            f"{_SNAP}num_analysts_eps",
            f"{_SNAP}period",
        ),
        licence=_P,
    ),
    Feature(
        "revisions_status", "str", "category",
        "OK: a snapshot of the same fiscal year exists for every window (30, 60, 90 days); "
        "BUILDING: an earlier snapshot exists, not for every window; NO_PRIOR: no earlier "
        "snapshot of this fiscal year",
        "never", "label", categories=STATUSES,
        inputs=(f"{_EST}estimates_status@v1", f"{_EST}fy1_period_end@v1", f"{_SNAP}period"),
        licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame[name], errors="coerce").astype("float64")


def _same_year(now: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """The snapshot rows of each name that are its FY1 year: ``end`` within ``PERIOD_SLACK`` days
    of ``fy1``, one per (name, snapshot ``day``), the nearest."""
    rows = rows.assign(end=pd.to_datetime(rows["period"], errors="coerce")).dropna(subset=["end"])
    rows = rows.assign(day=pd.to_datetime(rows["session_date"]).dt.normalize())
    both = now[["instrument_id", "fy1"]].merge(rows, on="instrument_id")
    both["gap"] = (both["end"] - both["fy1"]).abs()
    both = both[both["gap"] <= pd.Timedelta(days=PERIOD_SLACK)]
    both = both.sort_values(["instrument_id", "day", "gap"], kind="stable")
    return both.drop_duplicates(["instrument_id", "day"], keep="first")


def _at(same: pd.DataFrame, session: date, days: int) -> pd.DataFrame:
    """The latest snapshot of the same year in the window ``days`` back, per name."""
    since, until = days_back(session, days)
    window = same[(same["day"] >= pd.Timestamp(since)) & (same["day"] <= pd.Timestamp(until))]
    return window.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    estimates = inputs.get(ESTIMATES_TABLE)
    if estimates is None:
        return pd.DataFrame(columns=["instrument_id", *COLUMNS])
    served = estimates[estimates["estimates_status"].astype(object) == OK]
    now = pd.DataFrame(
        {
            "instrument_id": served["instrument_id"].astype(str).to_numpy(),
            "fy1": pd.to_datetime(served["fy1_period_end"], errors="coerce").to_numpy(),
            "eps": _numbers(served, "eps_fy1").to_numpy(),
            "revenue": _numbers(served, "revenue_fy1").to_numpy(),
            "analysts": _numbers(served, "eps_fy1_analysts").to_numpy(),
            "taken": (
                pd.Timestamp(session) - pd.to_timedelta(_numbers(served, "estimates_age_days"), "D")
            ).to_numpy(),
        }
    )
    history = history_rows(inputs.get(SNAPSHOTS), ESTIMATES, VENDOR, session)
    same = _same_year(now.dropna(subset=["fy1"]), history)
    ids = now["instrument_id"]
    out = pd.DataFrame({"instrument_id": ids})
    seen = pd.Series(True, index=now.index)
    for days in WINDOWS:
        then = _at(same, session, days)
        for column, old in (("eps_avg", "eps"), ("revenue_avg", "revenue")):
            out[f"{old}_then_{days}"] = ids.map(then[column]).astype("float64")
        out[f"analysts_then_{days}"] = ids.map(then["num_analysts_eps"]).astype("float64")
        seen &= ids.isin(then.index)
    for days in (30, 60, 90):
        out[f"eps_fy1_revision_{days}d"] = change_pct(now["eps"], out[f"eps_then_{days}"])
    for days in (30, 90):
        out[f"revenue_fy1_revision_{days}d"] = change_pct(
            now["revenue"], out[f"revenue_then_{days}"]
        )
    change = (now["analysts"] - out["analysts_then_90"]).round()
    out["eps_fy1_analysts_change_90d"] = change.astype("Int64")
    older = same.merge(now[["instrument_id", "taken"]], on="instrument_id")
    earlier = set(older.loc[older["day"] < older["taken"], "instrument_id"])
    out["revisions_status"] = np.select([seen, ids.isin(earlier)], [OK, BUILDING], default=NO_PRIOR)
    return out[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the consensus EPS and revenue of the current fiscal year have been revised over 30, 60 "
    "and 90 days (FMP annual estimates, our own point-in-time snapshots; personal-use licence)",
    (
        Input(ESTIMATES_TABLE, required=False),
        Input(SNAPSHOTS, lookback=HISTORY_LOOKBACK, required=False),
    ),
    FEATURES,
    compute,
    optional=True,  # a screen without the table warns, never PARTIAL (ADR 0055, ADR 0068)
)
