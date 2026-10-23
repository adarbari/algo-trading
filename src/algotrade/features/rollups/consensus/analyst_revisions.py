"""``analyst_revisions@v2``: how the consensus for the current fiscal year has moved.

Inputs: ``analyst_estimates@v2`` for the session (required: FY1 as the session knows it, its year
end, EPS, revenue, analyst count and the vendor it came from) and ``analyst/estimate_snapshots``
as the session sees it (our own nightly history of FMP's and Yahoo's annual estimates:
``data.analyst.reading``). One row per estimates row, so a name reads as ``analyst_estimates@v2``
reads it: its ``estimates_status`` STALE, NOT_COVERED or NOT_FETCHED passes through to
``revisions_status`` with null values (ADR 0072: the two uncovered statuses read as "not
covered", STALE as old data), and ``revisions_source`` is its ``estimates_source``. The history a
revision compares with is ONLY that vendor's snapshots of the name (``history_of_chosen``): after
a name flips vendor (FMP's estimates lapse, or return) its revisions are BUILDING / NO_PRIOR
until the new vendor's own snapshots span the windows (90 days; sooner only if it had already
been fetching the name), never a difference across
vendors (their EPS bases differ; ADR 0080). A column cannot carry the licence of the vendor it
holds for a name, so every feature carries the stricter: ``licence = "yahoo"`` (ADR 0068, 0069,
0080). v2 (v1: FMP only) adds ``revisions_source``; every v1 column is unchanged.

    eps_fy1_revision_30d, _60d, _90d      (EPS of FY1 now - EPS of the same year N days ago) /
                                          |EPS then|, in percent
    revenue_fy1_revision_30d, _90d        the same for revenue
    eps_fy1_analysts_change_90d           analysts behind the EPS now less 90 days ago
    revisions_status                      OK / BUILDING / NO_PRIOR, or STALE / NOT_COVERED /
                                          NOT_FETCHED as ``estimates_status`` says
    revisions_source                      fmp / yahoo: ``estimates_source``, the vendor compared

"Now" is the newest snapshot (the one ``analyst_estimates@v2`` serves) and "N days ago" is
measured from ITS day, not from the session: a past value is the same fiscal YEAR in an earlier
snapshot, the estimate row whose year end is within ``PERIOD_SLACK`` (10) days of FY1's year end,
in the latest snapshot for a session from ``N + SNAPSHOT_SLACK`` (7) to ``N`` days before the
newest one that holds such a row. Never matched on the ``FY1`` label: when the 10-K makes FY1 the
next year the year end moves by a year and nothing matches, unless the old snapshots listed the
new year as FY2, which is then a revision of that year. A 52 or 53 week year whose date moved by
days still matches. Only snapshots for a session on or before this one are read (the reader hides
the ones published after the next open), and only our own: never a vendor history.

    OK         a snapshot of the same year exists for every window (30, 60 and 90 days)
    BUILDING   an earlier snapshot of the year exists, but not for every window: the history is
               still short, or a night was missed
    NO_PRIOR   no earlier snapshot of this year: it only now appears, or FY1 has no year end

The history starts at our first snapshot (2026-10-19 at the earliest), so the 30-day columns are
null until about 2026-11-18 and the 90-day ones until about 2027-01-17. A revision is null when
the old value is missing or smaller than ``MIN_BASE`` (the shared floor of
``earnings_revisions@v1``; for revenue only a missing or zero old value): a percent of nearly
nothing, whatever the status; a loss-maker's negative base counts by its size. The windows, the
slacks, the floor and matching by year end are part of the definition: changing one is a new
version. There is no 7-day window: a covered name is refreshed about weekly.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.consensus.analyst_status import (
    ESTIMATES,
    HISTORY_LOOKBACK,
    NOT_COVERED,
    NOT_FETCHED,
    OK,
    SNAPSHOTS,
    SOURCES,
    STALE,
    UNCOVERED,
    days_back,
    history_of_chosen,
)
from algotrade.features.rollups.consensus.earnings_surprise import MIN_BASE, change_pct

NAME = "analyst_revisions"
VERSION = 2
ESTIMATES_TABLE = "rollups/instrument/analyst_estimates@v2"
BUILDING, NO_PRIOR = "BUILDING", "NO_PRIOR"
STATUSES = (OK, BUILDING, NO_PRIOR, STALE, NOT_COVERED, NOT_FETCHED)
WINDOWS = (30, 60, 90)  # calendar days back
PERIOD_SLACK = 10  # days: a year end this close to FY1's is the same fiscal year
_P: Licence = "yahoo"  # the stricter of the two vendors (ADR 0080)
_SNAP = f"{SNAPSHOTS}."
_EST = "analyst_estimates."
_SOURCE = "revisions_source"
_PCT = (-10000.0, 10000.0)  # percent: a small base makes huge revisions, kept and flagged
_FROM = "2026-10-19"  # our first snapshot at the earliest
_WHY = (
    "revisions_status is STALE, NOT_COVERED or NOT_FETCHED (as estimates_status of "
    "analyst_estimates@v2 says); or no snapshot of ours holds the same fiscal year {days} days "
    "before the newest one (our history starts " + _FROM + "); or {base}"
)
_BASE = f"the old value is missing or below {MIN_BASE}"
_REVENUE_BASE = "the old revenue is missing or zero"
_STATUS = "revisions_status"


def _revision(name: str, days: int, what: str, now: str, then: str) -> Feature:
    base = _REVENUE_BASE if name == "revenue" else _BASE
    return Feature(
        f"{name}_fy1_revision_{days}d", "float32", "pct_points",
        f"Change of the first estimate year's {what} over {days} days, in percent of the old "
        f"value: 5 is an estimate 5% higher than {days} days ago, same fiscal year",
        _WHY.format(days=days, base=base), valid_range=_PCT,
        inputs=(f"{_EST}{now}@v2", f"{_EST}fy1_period_end@v2", f"{_SNAP}{then}", f"{_SNAP}period"),
        licence=_P, null_status=_STATUS, uncovered_statuses=UNCOVERED,
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
        _WHY.format(days=90, base="either snapshot gave no count"), valid_range=(-1000, 1000),
        inputs=(
            f"{_EST}eps_fy1_analysts@v2",
            f"{_EST}fy1_period_end@v2",
            f"{_SNAP}num_analysts_eps",
            f"{_SNAP}period",
        ),
        licence=_P, null_status=_STATUS, uncovered_statuses=UNCOVERED,
    ),
    Feature(
        "revisions_status", "str", "category",
        "OK: a snapshot of the same fiscal year exists for every window (30, 60, 90 days); "
        "BUILDING: an earlier snapshot exists, not for every window; NO_PRIOR: no earlier "
        "snapshot of this fiscal year; STALE, NOT_COVERED, NOT_FETCHED: as the estimates' status",
        "never", "label", categories=STATUSES,
        inputs=(f"{_EST}estimates_status@v2", f"{_EST}fy1_period_end@v2", f"{_SNAP}period"),
        licence=_P,
    ),
    Feature(
        _SOURCE, "str", "category",
        "fmp or yahoo: the vendor the estimates (and so the revisions) come from; the history "
        "compared is that vendor's alone",
        "never", "label", categories=SOURCES,
        inputs=(f"{_EST}estimates_source@v2", f"{_SNAP}source"), licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame[name], errors="coerce").astype("float64")


def _same_year(now: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """The snapshot rows of each name that are its FY1 year: ``end`` within ``PERIOD_SLACK`` days
    of ``fy1``, one per (name, snapshot ``day``), the nearest; with the name's ``taken``."""
    rows = rows.assign(end=pd.to_datetime(rows["period"], errors="coerce")).dropna(subset=["end"])
    rows = rows.assign(day=pd.to_datetime(rows["session_date"]).dt.normalize())
    both = now[["instrument_id", "fy1", "taken"]].merge(rows, on="instrument_id")
    both["gap"] = (both["end"] - both["fy1"]).abs()
    both = both[both["gap"] <= pd.Timedelta(days=PERIOD_SLACK)]
    both = both.sort_values(["instrument_id", "day", "gap"], kind="stable")
    return both.drop_duplicates(["instrument_id", "day"], keep="first")


def _at(same: pd.DataFrame, days: int) -> pd.DataFrame:
    """The latest snapshot of the same year in the window ``days`` before the newest snapshot
    (each name's ``taken``), per name."""
    since, until = days_back(same["taken"], days)
    window = same[(same["day"] >= since) & (same["day"] <= until)]
    return window.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")


def _measured(served: pd.DataFrame, history: pd.DataFrame, session: date) -> pd.DataFrame:
    """The revisions and ``revisions_status`` of the names whose estimates are served (OK)."""
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
    same = _same_year(now.dropna(subset=["fy1"]), history)
    ids = now["instrument_id"]
    out = pd.DataFrame({"instrument_id": ids})
    seen = pd.Series(True, index=now.index)
    for days in WINDOWS:
        then = _at(same, days)
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
    older = same[same["day"] < same["taken"]]
    out[_STATUS] = np.select(
        [seen, ids.isin(set(older["instrument_id"]))], [OK, BUILDING], default=NO_PRIOR
    )
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    estimates = inputs[ESTIMATES_TABLE]
    assert estimates is not None  # required input
    status = estimates["estimates_status"].astype(object)
    chosen = estimates.set_index(estimates["instrument_id"].astype(str))["estimates_source"]
    history = history_of_chosen(inputs.get(SNAPSHOTS), ESTIMATES, chosen, session)
    measured = _measured(estimates[status == OK], history, session)
    passed = estimates[status != OK]
    rest = pd.DataFrame(
        {
            "instrument_id": passed["instrument_id"].astype(str).to_numpy(),
            _STATUS: status[status != OK].to_numpy(),  # STALE, NOT_COVERED or NOT_FETCHED
        }
    )
    out = pd.concat([measured, rest], ignore_index=True)
    out[_SOURCE] = out["instrument_id"].map(chosen)
    return out.reindex(columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the consensus EPS and revenue of the current fiscal year have been revised over 30, 60 "
    "and 90 days (FMP annual estimates, else Yahoo's; our own point-in-time snapshots; "
    "owner-only licence)",
    (
        Input(ESTIMATES_TABLE),
        Input(SNAPSHOTS, lookback=HISTORY_LOOKBACK, required=False),
    ),
    FEATURES,
    compute,
    optional=True,  # a screen without the table warns, never PARTIAL (ADR 0055, ADR 0068)
    sole_source="two free vendors, FMP first then Yahoo, no further fallback: ADR 0055 "
    "amendment, ADR 0068, ADR 0080",
)
