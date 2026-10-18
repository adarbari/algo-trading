"""``analyst_ratings@v1``: how many analysts say buy, hold or sell, and how that moved.

Inputs: ``analyst/estimate_snapshots`` as the session sees it (our own nightly history of
Finnhub's recommendation trend: ``data.analyst.reading``) and the session's ``universe`` (one row
per equity). Finnhub only, ``kind = recommendation``: one record per month, whose counts are
what the vendor shows the day it is asked. ``licence = "personal"`` on every feature (ADR 0068,
ADR 0069).

    rating_strong_buy ... rating_strong_sell   analysts at each rating, the newest month
    rating_count                               their sum
    rating_score                               the mean rating on 1 to 5: 5 is strong buy, 1
                                               strong sell
    rating_month                               the month the counts are for (its first day)
    rating_score_change_90d                    the score now less the score in our snapshot
                                               about 90 days back
    ratings_status                             OK / STALE / NOT_COVERED / NOT_FETCHED
                                               (``analyst_status``)

The row is the newest month of the name's newest snapshot (never mixed with an older fetch). The
score is ``(5 sb + 4 b + 3 h + 2 s + 1 ss) / count``, null when the count is 0 (nobody rates the
name). A STALE snapshot (older than ``stale_days``, 45: the trend is monthly, so a month and a
half without a refresh) serves no values: they read as not stored, the status stays.

The change is the history we hold, never a vendor history (the vendor restates its months): the
newest snapshot's score less that of the latest snapshot 90 to 90 + ``SNAPSHOT_SLACK`` (7) days
before the NEWEST snapshot (not before the session: the window is 90 days whatever the newest
snapshot's age). It is null until a snapshot that old exists: our history starts at
the first nightly snapshot (2026-10-19 at the earliest), so the first value is 90 days later.
Only snapshots for a session on or before this one are read.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence, Range
from algotrade.features.rollups.consensus.analyst_status import (
    FINNHUB,
    HISTORY_LOOKBACK,
    OK,
    RECOMMENDATION,
    SNAPSHOTS,
    STATUSES,
    UNCOVERED,
    UNIVERSE,
    AnalystParams,
    days_back,
    history_rows,
    population,
    resolve,
    vendor_rows,
)

NAME = "analyst_ratings"
VERSION = 1
_P: Licence = "personal"
_SNAP = f"{SNAPSHOTS}."
_STATUS = "ratings_status"
CHANGE_DAYS = 90  # calendar days back for the score change: part of the definition
# The vendor's columns, worst last, and the points each is worth: strong buy 5 ... strong sell 1.
POINTS = {"strong_buy": 5, "buy": 4, "hold": 3, "sell": 2, "strong_sell": 1}
_WHY = (
    "ratings_status is STALE (the newest snapshot is older than stale_days), NOT_COVERED (the "
    "vendor has no recommendation trend for the name) or NOT_FETCHED (never asked: the nightly "
    "rotation has not reached it)"
)


@dataclass(frozen=True)
class RatingsParams(AnalystParams):
    stale_days: int = 45  # the trend is monthly: a snapshot older than this is STALE


def _count(name: str, what: str) -> Feature:
    return Feature(
        f"rating_{name}", "int", "count", what, _WHY, valid_range=(0, None),
        inputs=(f"{_SNAP}{name}", f"{_SNAP}period"), licence=_P, null_status=_STATUS,
        uncovered_statuses=UNCOVERED,
    )  # fmt: skip


def _value(name: str, dtype: str, unit: str, what: str, null: str, valid_range: Range) -> Feature:
    return Feature(
        name, dtype, unit, what, null, valid_range=valid_range,
        inputs=tuple(f"{_SNAP}{c}" for c in (*POINTS, "period")), licence=_P,
        null_status=_STATUS, uncovered_statuses=UNCOVERED,
    )  # fmt: skip


FEATURES = (
    _count("strong_buy", "Analysts who rate the stock a strong buy, in the newest month"),
    _count("buy", "Analysts who rate the stock a buy"),
    _count("hold", "Analysts who rate the stock a hold"),
    _count("sell", "Analysts who rate the stock a sell"),
    _count("strong_sell", "Analysts who rate the stock a strong sell"),
    _value(
        "rating_count", "int", "count",
        "How many analysts the five ratings add up to: few is a thin consensus",
        _WHY + ", or the vendor gave no count for one rating", (0, None),
    ),
    _value(
        "rating_score", "float32", "ratio",
        "The mean rating on a scale of 1 to 5: 5 is every analyst at strong buy, 3 hold, 1 "
        "strong sell",
        _WHY + ", or no analyst rates the name (count 0)", (1.0, 5.0),
    ),
    Feature(
        "rating_month", "date", "date",
        "The month the counts are for, as its first day: the newest month of the newest snapshot",
        _WHY, inputs=(f"{_SNAP}period",), licence=_P, null_status=_STATUS,
        uncovered_statuses=UNCOVERED,
    ),
    _value(
        "rating_score_change_90d", "float32", "ratio",
        f"The score now less the score in our snapshot about {CHANGE_DAYS} days ago: positive is "
        "analysts turning more bullish",
        _WHY + f"; or no snapshot of ours is {CHANGE_DAYS} days old yet (our history starts "
        "2026-10-19), or either score is null", valid_range=(-4.0, 4.0),
    ),
    Feature(
        _STATUS, "str", "category",
        "OK: a snapshot at most stale_days (45) old; STALE: older, values not served; "
        "NOT_COVERED: the vendor has no recommendation trend for the name; NOT_FETCHED: never "
        "asked",
        "never", "label", categories=STATUSES, inputs=(f"{_SNAP}kind",), licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _snapshots(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (name, snapshot): its ``day`` (the session it is for), its newest ``month``
    with the counts, ``count`` (null unless all five are there) and ``score`` (null when the
    count is 0)."""
    rows = rows.assign(month=pd.to_datetime(rows["period"], errors="coerce")).dropna(
        subset=["month"]
    )
    rows = rows.assign(day=pd.to_datetime(rows["session_date"]).dt.normalize())
    rows = rows.sort_values(["instrument_id", "day", "month"], kind="stable")
    rows = rows.drop_duplicates(["instrument_id", "day"], keep="last")
    counts = rows[list(POINTS)].apply(pd.to_numeric, errors="coerce").astype("float64")
    total = counts.sum(axis=1, min_count=len(POINTS))
    points = sum(counts[name] * weight for name, weight in POINTS.items())
    out = rows[["instrument_id", "day", "month"]].copy()
    out[list(POINTS)] = counts
    out["count"] = total
    out["score"] = (points / total.where(total > 0)).astype("float64")
    return out


def _change(snaps: pd.DataFrame, newest: pd.DataFrame) -> pd.Series:
    """Per name the newest snapshot's score less the score of the latest snapshot in the window
    ``CHANGE_DAYS`` before the NEWEST snapshot's day; a name without both has none."""
    now = newest.set_index("instrument_id")
    since, until = days_back(now["day"], CHANGE_DAYS)
    window = pd.DataFrame({"since": since, "until": until}).reset_index()
    old = snaps.merge(window, on="instrument_id")
    old = old[(old["day"] >= old["since"]) & (old["day"] <= old["until"])]
    old = old.sort_values("day", kind="stable").drop_duplicates("instrument_id", keep="last")
    return now["score"] - old.set_index("instrument_id")["score"].reindex(now.index)


def compute(inputs: Inputs, session: date, p: RatingsParams) -> pd.DataFrame:
    snapshots = inputs.get(SNAPSHOTS)
    ids = population(inputs[UNIVERSE], snapshots, FINNHUB)
    rows = vendor_rows(snapshots, RECOMMENDATION, FINNHUB)
    status = resolve(ids, rows, snapshots, session, p, FINNHUB)
    out = pd.DataFrame({"instrument_id": status["instrument_id"]})
    out[_STATUS] = status["status"]
    served = set(status.loc[status["status"] == OK, "instrument_id"])
    snaps = _snapshots(history_rows(snapshots, RECOMMENDATION, FINNHUB, session))
    snaps = snaps[snaps["instrument_id"].isin(served)]
    newest = snaps[snaps["day"] == snaps.groupby("instrument_id")["day"].transform("max")]
    now = newest.set_index("instrument_id")
    for name in POINTS:
        out[f"rating_{name}"] = out["instrument_id"].map(now[name])
    out["rating_count"] = out["instrument_id"].map(now["count"])
    out["rating_score"] = out["instrument_id"].map(now["score"])
    out["rating_month"] = out["instrument_id"].map(now["month"].dt.date)
    out["rating_score_change_90d"] = out["instrument_id"].map(_change(snaps, newest))
    for column in ("rating_count", *(f"rating_{name}" for name in POINTS)):
        out[column] = out[column].astype("Int64")
    return out[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How many analysts rate each stock strong buy to strong sell, the mean rating and its change "
    "over 90 days (Finnhub recommendation trend, our own point-in-time snapshots; personal-use "
    "licence)",
    (Input(UNIVERSE), Input(SNAPSHOTS, lookback=HISTORY_LOOKBACK, required=False)),
    FEATURES,
    compute,
    RatingsParams(),
    optional=True,  # a screen without the table warns, never PARTIAL (ADR 0055, ADR 0068)
)
