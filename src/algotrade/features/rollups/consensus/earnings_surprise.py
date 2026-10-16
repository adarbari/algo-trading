"""``earnings_surprise@v1``: how the last reports compared with the consensus forecast.

Input: ``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``: one row
per instrument and report date, point in time). A report counts at session S only when its
result was known by it (``known_from <= S``, a report date on or before S) and carries a
reported EPS; the forecast is the one the calendar showed with that result. The surprise is
computed here from the two numbers, never the vendor's value:

    surprise_eps = eps_reported - eps_forecast                       (dollars per share)
    surprise_pct = surprise_eps / |eps_forecast| x 100

``surprise_pct`` is null when ``|eps_forecast|`` is below ``MIN_BASE`` (five cents: a percent of
nearly nothing is noise); ``surprise_eps`` has no base. A report is a *beat* when
``eps_reported > eps_forecast`` (meeting the forecast is not a beat), whatever the base.

The calendar can drop the minus sign of a loss-maker's forecast. The vendor's own
``surprise_pct`` is a witness for that, never a value: a report is a SIGN_CONFLICT when the
vendor's figure is present, differs from ours by more than ``TOLERANCE`` points and matches the
surprise computed against the NEGATED forecast within ``TOLERANCE``. Its surprise is null (the
forecast is not flipped) and it is left out of the four-report columns. Where the vendor gave
no figure our value stands.

    last_report_date    the date of the latest counted report (so a stale last report shows)
    last_eps_reported   that report's reported EPS, per share
    last_eps_forecast   the forecast it was reported against
    last_surprise_eps   that report's surprise in dollars per share (no base)
    last_surprise_pct   that report's surprise in percent of the forecast
    surprise_median_4q  the median ``surprise_pct`` of the last four counted reports (the
                        median, so one placeholder result cannot move it; however far back
                        the reports are: pair with last_report_date)
    beats_4q            how many of the last four counted reports beat their forecast
    reports_4q          how many of the last four counted reports can be compared (a forecast
                        and no SIGN_CONFLICT): the base of beats_4q

One row per instrument with an ``events/earnings`` row known by the session (dense over
them), with ``surprise_status`` OK (the last report can be compared), NO_REPORT (no reported
result known by the session: a name that has not reported, or whose results the calendar never
held), NO_FORECAST (the last report has no forecast) or SIGN_CONFLICT (the last report's
forecast sign is in doubt, above); in the last two the surprise columns of that report are null
and earlier reports can still fill the four-report columns. The four-report window, the floor,
the tolerance and the strict beat are part of the definition: changing one is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_surprise"
VERSION = 1
OK, NO_REPORT, NO_FORECAST, SIGN_CONFLICT = "OK", "NO_REPORT", "NO_FORECAST", "SIGN_CONFLICT"
REPORTS = 4  # the reports the four-report columns cover
MIN_BASE = 0.05  # |forecast| below this (US dollars per share) gives no percent surprise
TOLERANCE = 0.5  # percent points: the vendor's figure "matches" ours within this
_EPS = (-1000.0, 1000.0)  # dollars per share: a sanity bound, values outside are kept
_EPS_GAP = (-2000.0, 2000.0)  # a difference of two such values
_PCT = (-10000.0, 10000.0)  # percent: a small forecast makes huge surprises, kept and flagged

_RESULT = (f"{earnings.EVENTS}.eps_reported", f"{earnings.EVENTS}.ts")
_BOTH = (*_RESULT, f"{earnings.EVENTS}.eps_forecast")
_CHECKED = (*_BOTH, f"{earnings.EVENTS}.surprise_pct")
_NONE = "no reported result known by the session"
_COMPARE = "the last report has no forecast, or its forecast sign is in doubt (SIGN_CONFLICT)"
_SMALL = f"the forecast is below {MIN_BASE} per share in size"

FEATURES = (
    Feature(
        "surprise_status", "str", "category",
        "OK: the last known report can be compared with its forecast; NO_REPORT: no reported "
        "result known by the session; NO_FORECAST: the last report has no forecast; "
        "SIGN_CONFLICT: the sign of the last report's forecast is in doubt, so it has no surprise",
        "never", "label", categories=(OK, NO_REPORT, NO_FORECAST, SIGN_CONFLICT),
        inputs=_CHECKED,
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
        "last_surprise_eps", "float32", "usd_per_share",
        "Reported minus forecast earnings per share of the latest report, in dollars: the "
        "surprise with no base, so a small forecast does not blow it up",
        f"{_NONE}, or {_COMPARE}", valid_range=_EPS_GAP, inputs=_CHECKED,
    ),
    Feature(
        "last_surprise_pct", "float32", "pct_points",
        "(reported - forecast) / |forecast| of the latest report, in percent: 10 is 10% above "
        "the forecast, -10 is 10% below it; computed here, not the vendor's figure",
        f"{_NONE}, or {_COMPARE}, or {_SMALL}", valid_range=_PCT, inputs=_CHECKED,
    ),
    Feature(
        "surprise_median_4q", "float32", "pct_points",
        f"Median percent surprise over the last {REPORTS} known reports that can be compared",
        f"{_NONE}, or none of the last {REPORTS} reports has a forecast of at least "
        f"{MIN_BASE} per share in size and a sign that is not in doubt",
        valid_range=_PCT, inputs=_CHECKED,
    ),
    Feature(
        "beats_4q", "int", "count",
        f"How many of the last {REPORTS} known reports reported above their forecast",
        f"{_NONE}, or none of the last {REPORTS} reports can be compared",
        valid_range=(0, REPORTS), inputs=_CHECKED,
    ),
    Feature(
        "reports_4q", "int", "count",
        f"How many of the last {REPORTS} known reports can be compared with a forecast: the "
        "base of beats_4q",
        _NONE, valid_range=(0, REPORTS), inputs=_CHECKED,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series:
    """A numeric column, NaN where the calendar gave none (or the column is absent)."""
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[name], errors="coerce")


def change_pct(value: pd.Series, base: pd.Series, floor: float = MIN_BASE) -> pd.Series:
    """``value`` against ``base`` in percent of ``|base|`` (the surprise of a result against its
    forecast, the revision of a forecast against an older one); NaN when ``|base|`` is below
    ``floor`` or ``base`` is zero or missing."""
    size = base.abs()
    return (value - base) / size.where((size >= floor) & (base != 0.0)) * 100.0


def _counted(stored: pd.DataFrame, session: date) -> pd.DataFrame:
    """One row per (instrument, report) known by ``session`` with the result, the forecast, and
    ``usable`` (a forecast and no sign conflict), ``conflict``, ``eps_gap``, ``surprise`` and
    ``beat`` of a usable one."""
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept for the invariant
        stored = stored[pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date <= session]
    rows = earnings.valid_events(stored, session)
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    reported, forecast = _numbers(rows, "eps_reported"), _numbers(rows, "eps_forecast")
    # The vendor's figure is a witness only: it flags a forecast whose sign the calendar lost.
    vendor = _numbers(rows, "surprise_pct")
    ours = change_pct(reported, forecast, floor=0.0)
    flipped = change_pct(reported, -forecast, floor=0.0)
    conflict = (
        vendor.notna()
        & ((ours - vendor).abs() > TOLERANCE)
        & ((flipped - vendor).abs() <= TOLERANCE)
    )
    usable = forecast.notna() & ~conflict
    rows = rows.assign(
        reported=reported,
        forecast=forecast,
        conflict=conflict,
        usable=usable,
        eps_gap=(reported - forecast).where(usable),
        surprise=change_pct(reported, forecast).where(usable),
        beat=(reported > forecast) & usable,
    )
    return rows.sort_values(["instrument_id", "report"], kind="stable")


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    rows = _counted(stored, session)
    ids = pd.Index(sorted(set(rows["instrument_id"])), name="instrument_id")
    done = rows[rows["reported"].notna() & (rows["report"] <= session)]
    last = done.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")
    recent = done.groupby("instrument_id").tail(REPORTS)
    comparable = recent[recent["usable"]].groupby("instrument_id")
    out = pd.DataFrame(index=ids)
    out["last_report_date"] = last["report"].reindex(ids)
    out["last_eps_reported"] = last["reported"].reindex(ids)
    out["last_eps_forecast"] = last["forecast"].reindex(ids)
    out["last_surprise_eps"] = last["eps_gap"].reindex(ids)
    out["last_surprise_pct"] = last["surprise"].reindex(ids)
    out["surprise_median_4q"] = (
        recent[recent["surprise"].notna()]
        .groupby("instrument_id")["surprise"]
        .median()
        .reindex(ids)
    )
    out["beats_4q"] = comparable["beat"].sum().reindex(ids)
    out["reports_4q"] = comparable.size().reindex(ids)
    reported = out["last_eps_reported"].notna()
    last_conflict = last["conflict"].reindex(ids).fillna(False).astype(bool)
    out["surprise_status"] = np.select(
        [~reported, last_conflict, out["last_surprise_eps"].isna()],
        [NO_REPORT, SIGN_CONFLICT, NO_FORECAST],
        default=OK,
    )
    # A name that reported with nothing comparable in the last four has a base of 0, not null.
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
