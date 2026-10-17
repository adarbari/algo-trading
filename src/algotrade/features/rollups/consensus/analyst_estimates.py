"""``analyst_estimates@v1``: what analysts expect for the current and the next fiscal year.

Inputs: ``analyst/estimate_snapshots`` as the session sees it (our own nightly history of FMP's
annual estimates: ``data.analyst.reading``), the session's ``universe`` (one row per equity) and
``financials@v2`` for the last fiscal year end known. Annual estimates only (``kind =
estimates_annual``), FMP only; the rows are the vendor's newest snapshot of the name, so the
fiscal years are the ones listed in ONE fetch. Every feature is derived from a personal-use
source: ``licence = "personal"`` (ADR 0068, ADR 0069).

    fy1_period_end, fy2_period_end   the fiscal year ends of the first and second estimate year
    eps_fy1, eps_fy2                 the consensus (average) EPS of each, USD per share
    revenue_fy1, revenue_fy2         the consensus (average) revenue of each, USD
    eps_fy1_analysts                 analysts behind the EPS of FY1 (revenue likewise)
    estimates_age_days               days from the snapshot's session to this one
    estimates_status                 OK / STALE / NOT_COVERED / NOT_FETCHED (``analyst_status``)

FY1 is the first estimate year ending MORE THAN ``fy_slack_days`` (60) after the last fiscal year
end of an annual report known at the session (``financials@v2``'s ``revenue_fy_end``: the latest
annual fact filed by then, so the year just reported is never FY1 while the vendor still lists
it; the slack absorbs a 52/53-week year whose vendor date differs by days). Without a known
annual report FY1 is the first estimate year ending after the session. FY2 is the next listed.
**At the fiscal-year roll FY1 moves when the 10-K becomes known**, so a forward P/E over FY1 jumps
once, on the session the filing is public: it is a change of the year, not of the estimate.

A STALE snapshot (more than ``stale_days``, 21) serves no values: they read as not stored, the
age and status stay. Not a unit of currency: a foreign filer's estimates are in the vendor's
reporting currency (the formulas that divide them by a USD price handle ADRs, later).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence, Range
from algotrade.features.rollups.consensus.analyst_status import (
    ESTIMATES,
    LOOKBACK,
    OK,
    SNAPSHOTS,
    STATUSES,
    UNCOVERED,
    UNIVERSE,
    AnalystParams,
    population,
    resolve,
    vendor_rows,
)

NAME = "analyst_estimates"
VERSION = 1
FINANCIALS = "rollups/instrument/financials@v2"
_P: Licence = "personal"
_SNAP = f"{SNAPSHOTS}."
_WHY = (
    "analyst_status is STALE (the newest snapshot is older than stale_days), NOT_COVERED (the "
    "vendor has no estimates for the name) or NOT_FETCHED (never asked: the nightly rotation "
    "has not reached it); or the snapshot lists no year ending after the last annual report"
)
_STATUS = "estimates_status"


@dataclass(frozen=True)
class EstimatesParams(AnalystParams):
    fy_slack_days: int = 60  # a year end within this of the last annual report is that report

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.fy_slack_days < 300:
            raise ValueError("fy_slack_days must be in 0..299")


def _feature(
    name: str, dtype: str, unit: str, what: str, column: str, valid_range: Range | None = None
) -> Feature:
    return Feature(
        name, dtype, unit, what, _WHY, inputs=(f"{_SNAP}{column}", f"{_SNAP}period"),
        licence=_P, null_status=_STATUS, uncovered_statuses=UNCOVERED, valid_range=valid_range,
    )  # fmt: skip


FEATURES = (
    _feature(
        "fy1_period_end", "date", "date",
        "The fiscal year end of the first estimate year: the first the vendor lists after the "
        "last annual report known (the current year, not yet reported)", "period",
    ),
    _feature(
        "fy2_period_end", "date", "date",
        "The fiscal year end of the second estimate year, the next one listed", "period",
    ),
    _feature(
        "eps_fy1", "float32", "usd_per_share",
        "The analysts' average estimate of earnings per share for the first estimate year, as "
        "the newest snapshot of the session says", "eps_avg", valid_range=(-1000.0, 1000.0),
    ),
    _feature(
        "eps_fy2", "float32", "usd_per_share",
        "The analysts' average estimate of earnings per share for the second estimate year",
        "eps_avg", valid_range=(-1000.0, 1000.0),
    ),
    _feature(
        "revenue_fy1", "float", "usd",
        "The analysts' average estimate of revenue for the first estimate year, in the vendor's "
        "reporting currency", "revenue_avg", valid_range=(0, None),
    ),
    _feature(
        "revenue_fy2", "float", "usd",
        "The analysts' average estimate of revenue for the second estimate year",
        "revenue_avg", valid_range=(0, None),
    ),
    _feature(
        "eps_fy1_analysts", "int", "count",
        "How many analysts' estimates the first year's EPS average (few: a thin consensus)",
        "num_analysts_eps", valid_range=(0, 1000),
    ),
    _feature(
        "revenue_fy1_analysts", "int", "count",
        "How many analysts' estimates the first year's revenue average",
        "num_analysts_revenue", valid_range=(0, 1000),
    ),
    Feature(
        "estimates_age_days", "int", "days",
        "Days from the snapshot's session to this session: how old the estimates are (shown for "
        "OK and STALE)",
        "estimates_status is NOT_COVERED or NOT_FETCHED: no snapshot of the name",
        valid_range=(0, None), inputs=(f"{_SNAP}session_date",), licence=_P,
        null_status=_STATUS, uncovered_statuses=UNCOVERED,
    ),
    Feature(
        _STATUS, "str", "category",
        "OK: a snapshot at most stale_days (21) old; STALE: older, values not served; "
        "NOT_COVERED: the vendor has no estimates for the name; NOT_FETCHED: never asked",
        "never", "label", categories=STATUSES, inputs=(f"{_SNAP}kind",), licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)
_VALUES = ("eps_avg", "revenue_avg", "num_analysts_eps", "num_analysts_revenue")


def _year_ends(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["period"], errors="coerce").dt.date


def _threshold(
    ids: list[str], financials: pd.DataFrame | None, session: date, slack: int
) -> dict[str, date]:
    """Per name the date a year end must exceed to be FY1: the last annual report's year end
    plus the slack, else the session."""
    found: dict[str, date] = {}
    if financials is not None and "revenue_fy_end" in financials.columns:
        known = financials.dropna(subset=["revenue_fy_end"])
        found = {
            str(i): pd.Timestamp(d).date() + timedelta(days=slack)
            for i, d in zip(known["instrument_id"], known["revenue_fy_end"], strict=True)
        }
    return {i: found.get(i, session) for i in ids}


def _years(rows: pd.DataFrame, after: dict[str, date]) -> pd.DataFrame:
    """The first two estimate years ending after each name's threshold: the rows with ``end``
    and ``n`` (1 or 2)."""
    rows = rows.assign(end=_year_ends(rows)).dropna(subset=["end"])
    limits = pd.Series(
        list(after.values()), index=pd.Index(list(after), dtype=object), dtype=object
    )
    rows = rows.join(limits.rename("after"), on="instrument_id")
    rows = rows[(rows["end"] > rows["after"]).fillna(False).astype(bool)]
    rows = rows.sort_values(["instrument_id", "end"], kind="stable")
    rows = rows.groupby("instrument_id").head(2)
    return rows.assign(n=rows.groupby("instrument_id").cumcount() + 1)


def _column(out: pd.DataFrame, years: pd.DataFrame, n: int, name: str, source: str) -> None:
    got = years[years["n"] == n].set_index("instrument_id")[source]
    out[name] = out["instrument_id"].map(got)


def compute(inputs: Inputs, session: date, p: EstimatesParams) -> pd.DataFrame:
    snapshots = inputs.get(SNAPSHOTS)
    ids = population(inputs[UNIVERSE], snapshots)
    rows = vendor_rows(snapshots, ESTIMATES)
    status = resolve(ids, rows, snapshots, session, p)
    out = pd.DataFrame({"instrument_id": status["instrument_id"]})
    out[_STATUS] = status["status"]
    out["estimates_age_days"] = pd.to_numeric(status["age_days"])
    served = set(status.loc[status["status"] == OK, "instrument_id"])
    after = _threshold(sorted(served), inputs.get(FINANCIALS), session, p.fy_slack_days)
    years = _years(rows[rows["instrument_id"].isin(served)], after)
    for n in (1, 2):
        _column(out, years, n, f"fy{n}_period_end", "end")
        _column(out, years, n, f"eps_fy{n}", "eps_avg")
        _column(out, years, n, f"revenue_fy{n}", "revenue_avg")
    _column(out, years, 1, "eps_fy1_analysts", "num_analysts_eps")
    _column(out, years, 1, "revenue_fy1_analysts", "num_analysts_revenue")
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Analysts' consensus EPS and revenue for the current and next fiscal year (FMP annual "
    "estimates, our own point-in-time snapshots; personal-use licence)",
    (
        Input(UNIVERSE),
        Input(SNAPSHOTS, lookback=LOOKBACK, required=False),
        Input(FINANCIALS, required=False),
    ),
    FEATURES,
    compute,
    EstimatesParams(),
    # The vendor's free plan covers few names and its key may be absent: a screen reading it
    # without the table warns, never PARTIAL (ADR 0055, ADR 0068).
    optional=True,
)
