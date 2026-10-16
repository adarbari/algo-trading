"""``earnings_revisions@v1``: how the consensus forecast of the next report has moved.

Input: ``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``) for the
next report, plus the raw snapshots for the forecast the same quarter had earlier. Each night
stores one snapshot of the calendar with its forecasts, so the forecast of one fiscal quarter
can be compared across nights. The history starts on 2026-10-02 (the first snapshot that
holds forecasts), so the 7-day columns are null until 2026-10-09 and the 30-day columns until
about 2026-11-01.

The next report is the first valid one on or after the session (as ``next_earnings_date``
reads it); its forecast, estimate count and fiscal quarter are the values the session knew. A
past value is the forecast of the SAME fiscal quarter in the latest snapshot stored on or
before ``session - N days``, no more than ``SNAPSHOT_SLACK`` days before it (a night the fetch
failed or a holiday must not reach back to a stale forecast). Only snapshots stored on or
before the session count (a snapshot stored later never moves the value), and a row a snapshot
carried forward over a failed fetch (``carried_from``) is not an observation of that night.

    next_eps_forecast           the next report's forecast, EPS per share
    estimate_count              how many analysts the forecast averages
    forecast_revision_7d        (forecast now - forecast 7 days ago) / |forecast 7 days ago|, in
                                percent, for the same fiscal quarter
    forecast_revision_30d       the same against 30 days ago
    estimate_count_change_30d   estimate_count now - the count 30 days ago, same quarter
    revision_status             OK: a snapshot 7 days back holds the same fiscal quarter;
                                BUILDING: no snapshot reaches back 7 days yet; NO_PRIOR: one
                                does, but not a row of this quarter for the name (a quarter
                                that just appeared, a night its row was only carried over);
                                NO_FORECAST: the next report has no forecast; NO_NEXT: no
                                next report is known

A revision is null when the old forecast is missing or smaller than ``MIN_BASE`` (five cents:
a percent of nearly nothing), whatever the status. A forecast whose sign the calendar lost on
one night reads as a revision of about +/-200%. One row per instrument with an
``events/earnings`` row known by the session. The windows (7 and 30 days), the slack, the base
floor and matching by fiscal quarter are part of the definition: changing one is a new version.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.consensus.earnings_surprise import MIN_BASE, change_pct
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_revisions"
VERSION = 1
OK, BUILDING, NO_PRIOR = "OK", "BUILDING", "NO_PRIOR"
NO_FORECAST, NO_NEXT = "NO_FORECAST", "NO_NEXT"
SHORT, LONG = 7, 30  # calendar days back for the two revisions
SNAPSHOT_SLACK = 4  # a snapshot serves a date at most this many days after it (weekend, holiday)
HISTORY_FROM = "2026-10-02"  # the first stored snapshot with forecasts
FISCAL_QUARTER = "fiscal_quarter"
_PCT = (-10000.0, 10000.0)  # percent: a small forecast makes huge revisions, kept and flagged

_NEXT = f"{earnings.EVENTS}.ts"
_FORECAST = f"{earnings.EVENTS}.eps_forecast"
_PAST = (_FORECAST, f"{earnings.EVENTS}.{FISCAL_QUARTER}")
_NO_NEXT = "no report date on or after the session is known"
_NO_FORECAST = "the next report has no forecast in the calendar"
_SHORT = (
    f"no snapshot stored {SHORT} days before the session (history starts {HISTORY_FROM}), or "
    "it holds no row of the next report's fiscal quarter"
)
_LONG = _SHORT.replace(str(SHORT), str(LONG))
_BASE = f"the old forecast is missing or below {MIN_BASE} per share"

FEATURES = (
    Feature(
        "revision_status", "str", "category",
        f"OK: the {SHORT}-day comparison exists; BUILDING: no snapshot reaches back {SHORT} "
        "days yet; NO_PRIOR: that snapshot has no row of the quarter; NO_FORECAST: the next "
        "report has no forecast; NO_NEXT: no next report known",
        "never", "label", categories=(OK, BUILDING, NO_PRIOR, NO_FORECAST, NO_NEXT),
        inputs=(_NEXT, *_PAST),
    ),
    Feature(
        "next_eps_forecast", "float32", "usd_per_share",
        "The consensus forecast of earnings per share for the next report, as known on the "
        "session",
        f"{_NO_NEXT}, or {_NO_FORECAST}", valid_range=(-1000.0, 1000.0), inputs=(_NEXT, _FORECAST),
    ),
    Feature(
        "estimate_count", "int", "count",
        "How many analysts' estimates the next report's forecast averages",
        f"{_NO_NEXT}, or the calendar gave no count", valid_range=(0, None),
        inputs=(_NEXT, f"{earnings.EVENTS}.estimates"),
    ),
    Feature(
        "forecast_revision_7d", "float32", "pct_points",
        f"Change of the next report's forecast over {SHORT} days, in percent of the old "
        "forecast: 5 is a forecast 5% higher than a week ago, same fiscal quarter",
        f"{_NO_NEXT}, {_NO_FORECAST}, {_SHORT}, or {_BASE}", valid_range=_PCT,
        inputs=(_NEXT, *_PAST),
    ),
    Feature(
        "forecast_revision_30d", "float32", "pct_points",
        f"Change of the next report's forecast over {LONG} days, in percent of the old "
        "forecast, same fiscal quarter",
        f"{_NO_NEXT}, {_NO_FORECAST}, {_LONG}, or {_BASE}", valid_range=_PCT,
        inputs=(_NEXT, *_PAST),
    ),
    Feature(
        "estimate_count_change_30d", "int", "count",
        f"Analysts' estimates now minus {LONG} days ago for the same fiscal quarter: "
        "positive is a quarter more analysts cover",
        f"{_NO_NEXT}, {_LONG}, or either snapshot gave no count", valid_range=(-1000, 1000),
        inputs=(_NEXT, f"{earnings.EVENTS}.estimates", f"{earnings.EVENTS}.{FISCAL_QUARTER}"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series:
    """A numeric column, NaN where the calendar gave none (or the column is absent)."""
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[name], errors="coerce")


def _observations(stored: pd.DataFrame, session: date) -> pd.DataFrame:
    """What each night's calendar said, for the nights stored on or before ``session``: one
    row per (instrument, fiscal quarter, night) with the forecast and count, carried-forward
    copies and the 8-K results rows (no forecast) left out."""
    rows = stored
    if "source" in rows.columns:
        rows = rows[rows["source"] != earnings.SEC_8K_SOURCE]
    if earnings.CARRIED_FROM in rows.columns:
        rows = rows[rows[earnings.CARRIED_FROM].isna()]
    night = pd.to_datetime(rows["session_date"]).dt.date
    rows = rows[night <= session]
    quarter = rows[FISCAL_QUARTER] if FISCAL_QUARTER in rows.columns else None
    obs = pd.DataFrame(
        {
            "instrument_id": rows["instrument_id"].astype(str),
            "night": pd.to_datetime(rows["session_date"]).dt.normalize(),
            "report": earnings.report_days(rows),
            FISCAL_QUARTER: quarter if quarter is not None else None,
            "forecast": _numbers(rows, "eps_forecast"),
            "estimates": _numbers(rows, "estimates"),
        }
    )
    return obs.sort_values(["night", "report", "instrument_id"], kind="stable")


def _at(obs: pd.DataFrame, session: date, days: int) -> tuple[pd.DataFrame, bool]:
    """The latest observation of each (instrument, fiscal quarter) in the nights from
    ``session - days - SNAPSHOT_SLACK`` to ``session - days``, and whether any night is there."""
    target = pd.Timestamp(session - timedelta(days=days))
    window = obs[(obs["night"] <= target) & (obs["night"] >= target - timedelta(SNAPSHOT_SLACK))]
    latest = window.dropna(subset=[FISCAL_QUARTER]).drop_duplicates(
        ["instrument_id", FISCAL_QUARTER], keep="last"
    )
    return latest, len(window) > 0


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept for the invariant
        stored = stored[pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date <= session]
    rows = earnings.valid_events(stored, session)
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    rows = rows.sort_values(["instrument_id", "report"], kind="stable")
    ids = pd.Index(sorted(set(rows["instrument_id"])), name="instrument_id")
    upcoming = rows[rows["report"] >= session].drop_duplicates("instrument_id", keep="first")
    nxt = pd.DataFrame(
        {
            "instrument_id": upcoming["instrument_id"].to_numpy(),
            "next_eps_forecast": _numbers(upcoming, "eps_forecast").to_numpy(),
            "estimate_count": _numbers(upcoming, "estimates").to_numpy(),
            FISCAL_QUARTER: (
                upcoming[FISCAL_QUARTER].to_numpy()
                if FISCAL_QUARTER in upcoming.columns
                else [None] * len(upcoming)
            ),
        }
    )
    obs = _observations(stored, session)
    out = pd.DataFrame({"instrument_id": ids}).merge(nxt, on="instrument_id", how="left")
    exists = {}
    for days in (SHORT, LONG):
        old, exists[days] = _at(obs, session, days)
        old = old.rename(columns={"forecast": f"old_{days}", "estimates": f"count_{days}"})
        old = old.assign(**{f"seen_{days}": True}).drop(columns=["night", "report"])
        out = out.merge(old, on=["instrument_id", FISCAL_QUARTER], how="left")
    out["forecast_revision_7d"] = change_pct(out["next_eps_forecast"], out[f"old_{SHORT}"])
    out["forecast_revision_30d"] = change_pct(out["next_eps_forecast"], out[f"old_{LONG}"])
    out["estimate_count_change_30d"] = out["estimate_count"] - out[f"count_{LONG}"]
    has_next = out["instrument_id"].isin(upcoming["instrument_id"])
    seen = out[f"seen_{SHORT}"].eq(True)
    out["revision_status"] = np.select(
        [
            ~has_next,
            out["next_eps_forecast"].isna(),
            seen,
            np.full(len(out), not exists[SHORT]),
        ],
        [NO_NEXT, NO_FORECAST, OK, BUILDING],
        default=NO_PRIOR,
    )
    for column in ("estimate_count", "estimate_count_change_30d"):
        out[column] = out[column].astype("Int64")
    return out[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the consensus forecast of the next earnings report has been revised (7 and 30 days)",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
