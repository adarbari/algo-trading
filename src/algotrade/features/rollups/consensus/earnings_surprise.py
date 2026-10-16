"""``earnings_surprise@v1``: how the last reports compared with the consensus forecast.

Input: ``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``: one row
per instrument and report date, point in time). A report counts at session S only when its
result was known by it (``known_from <= S``, a report date on or before S) and carries a
reported EPS; the forecast is the one the calendar showed with that result. The surprise is
computed here from the two numbers, never taken from the vendor's ``surprise_pct``:

    surprise_pct = (eps_reported - eps_forecast) / |eps_forecast| x 100

null when the forecast is missing or exactly zero (a percent of nothing). A report is a *beat*
when the surprise is above zero; meeting the forecast is not a beat.

    last_report_date    the date of the latest counted report (so a stale last report shows)
    last_eps_reported   that report's reported EPS, per share
    last_eps_forecast   the forecast it was reported against
    last_surprise_pct   the surprise of that report
    surprise_mean_4q    the mean surprise over the last four counted reports that have a
                        forecast (the last four reports, however far back: pair with
                        last_report_date)
    beats_4q            how many of those reports beat their forecast
    reports_4q          how many of the last four counted reports have a surprise (the
                        denominator of beats_4q and of the mean)

One row per instrument with an ``events/earnings`` row known by the session (dense over
them), with ``surprise_status`` OK (the last report has a surprise), NO_REPORT (no reported
result known by the session: a name that has not reported, or whose results the calendar never
held) or NO_FORECAST (the last report has no usable forecast, so its surprise is null; earlier
reports can still fill the four-report columns). The four-report window, the zero rule and
the strict beat are part of the definition: changing one is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_surprise"
VERSION = 1
OK, NO_REPORT, NO_FORECAST = "OK", "NO_REPORT", "NO_FORECAST"
REPORTS = 4  # the reports the four-report columns cover
_EPS = (-1000.0, 1000.0)  # dollars per share: a sanity bound, values outside are kept
_PCT = (-10000.0, 10000.0)  # percent: a tiny forecast makes huge surprises, kept and flagged

_RESULT = (f"{earnings.EVENTS}.eps_reported", f"{earnings.EVENTS}.ts")
_BOTH = (*_RESULT, f"{earnings.EVENTS}.eps_forecast")
_NONE = "no reported result known by the session"
_FORECAST = "the report has no forecast (or a forecast of exactly zero)"

FEATURES = (
    Feature(
        "surprise_status", "str", "category",
        "OK: the last known report has a surprise; NO_REPORT: no reported result known by the "
        "session; NO_FORECAST: the last report has no usable forecast",
        "never", "label", categories=(OK, NO_REPORT, NO_FORECAST), inputs=_RESULT,
    ),
    Feature(
        "last_report_date", "date", "date",
        "The date of the latest report whose result was known by the session",
        _NONE, inputs=_RESULT,
    ),
    Feature(
        "last_eps_reported", "float32", "usd_per_share",
        "Earnings per share the latest report gave, as the calendar stores it",
        _NONE, valid_range=_EPS, inputs=_RESULT,
    ),
    Feature(
        "last_eps_forecast", "float32", "usd_per_share",
        "The consensus forecast of earnings per share that report was measured against",
        f"{_NONE}, or the calendar held no forecast for it", valid_range=_EPS, inputs=_BOTH,
    ),
    Feature(
        "last_surprise_pct", "float32", "pct_points",
        "(reported - forecast) / |forecast| of the latest report, in percent: 10 is 10% above "
        "the forecast, -10 is 10% below it; computed here, not the vendor's figure",
        f"{_NONE}, or {_FORECAST}", valid_range=_PCT, inputs=_BOTH,
    ),
    Feature(
        "surprise_mean_4q", "float32", "pct_points",
        f"Mean surprise over the last {REPORTS} known reports that have a forecast",
        f"{_NONE}, or none of the last {REPORTS} reports has a usable forecast",
        valid_range=_PCT, inputs=_BOTH,
    ),
    Feature(
        "beats_4q", "int", "count",
        f"How many of the last {REPORTS} known reports reported above their forecast",
        f"{_NONE}, or none of the last {REPORTS} reports has a usable forecast",
        valid_range=(0, REPORTS), inputs=_BOTH,
    ),
    Feature(
        "reports_4q", "int", "count",
        f"How many of the last {REPORTS} known reports have a surprise: the base of "
        "surprise_mean_4q and beats_4q",
        _NONE, valid_range=(0, REPORTS), inputs=_BOTH,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series:
    """A numeric column, NaN where the calendar gave none (or the column is absent)."""
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[name], errors="coerce")


def change_pct(value: pd.Series, base: pd.Series) -> pd.Series:
    """``value`` against ``base`` in percent of ``|base|`` (the surprise of a result against its
    forecast, the revision of a forecast against an older one); NaN when ``base`` is zero."""
    return (value - base) / base.abs().where(base != 0.0) * 100.0


def _counted(stored: pd.DataFrame, session: date) -> pd.DataFrame:
    """One row per (instrument, report) known by ``session``, with the reported result and the
    forecast as numbers and the surprise computed."""
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept for the invariant
        stored = stored[pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date <= session]
    rows = earnings.valid_events(stored, session)
    rows = rows.assign(
        instrument_id=rows["instrument_id"].astype(str),
        reported=_numbers(rows, "eps_reported"),
        forecast=_numbers(rows, "eps_forecast"),
    )
    rows = rows.assign(surprise=change_pct(rows["reported"], rows["forecast"]))
    return rows.sort_values(["instrument_id", "report"], kind="stable")


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    rows = _counted(stored, session)
    ids = pd.Index(sorted(set(rows["instrument_id"])), name="instrument_id")
    done = rows[rows["reported"].notna() & (rows["report"] <= session)]
    last = done.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")
    recent = done.groupby("instrument_id").tail(REPORTS)
    scored = recent[recent["surprise"].notna()].groupby("instrument_id")["surprise"]
    out = pd.DataFrame(index=ids)
    out["last_report_date"] = last["report"].reindex(ids)
    out["last_eps_reported"] = last["reported"].reindex(ids)
    out["last_eps_forecast"] = last["forecast"].reindex(ids)
    out["last_surprise_pct"] = last["surprise"].reindex(ids)
    out["surprise_mean_4q"] = scored.mean().reindex(ids)
    out["beats_4q"] = scored.apply(lambda s: int((s > 0).sum())).reindex(ids)
    out["reports_4q"] = scored.size().reindex(ids)
    reported = out["last_eps_reported"].notna()
    out["surprise_status"] = np.where(
        ~reported, NO_REPORT, np.where(out["last_surprise_pct"].notna(), OK, NO_FORECAST)
    )
    # A name that reported with no usable forecast in the last four has a base of 0, not null.
    out.loc[reported, "reports_4q"] = out.loc[reported, "reports_4q"].fillna(0)
    out["beats_4q"] = out["beats_4q"].where(out["reports_4q"].fillna(0) > 0)
    for column in ("beats_4q", "reports_4q"):
        out[column] = out[column].astype("Int64")
    return out.reset_index()[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the last earnings reports compared with the consensus forecast (surprise, beats)",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
