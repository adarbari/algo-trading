"""``financials@v3``: trailing-twelve-month revenue, net income and diluted EPS, last fiscal-year
revenue, the year-ago revenue and EPS TTMs, and the latest quarter's revenue and EPS with the
same quarter a year earlier, from SEC company facts.

Inputs: ``instruments/shares`` rows of the concepts ``revenue``, ``net_income`` and
``eps_diluted``, read as ``instruments/shares_accepted``: every fact public at the session's
CLOSE, point in time by the instant SEC ACCEPTED the filing (``accepted_ts``; 16:00 New York
time, 13:00 on an early close). A 10-Q accepted at 16:30 on D is not in D's row and is in
D+1's; a fact without an acceptance time counts from the session after its filing date (v2
counted every fact ``filed <= session``: a date, so a filing accepted after the close counted
at that close, a one-session lookahead in every feature of this group; ADR 0067 amendment,
``fundamentals@v5`` has the same fix). The session's ``price_stats@v2`` (it sets which
instruments get a row), ``events/split`` and ``instruments/reference`` (the security type).

Each (concept, tag, period) takes its latest known value (a restatement replaces it from its
filing date). Revenue is reported under up to three tags; every tag is kept, the best-ranked
one wins per period for a reported quarter, and a quarter is never derived across tags. A TTM is,
in this order:

- ``QUARTERS``: the sum of the last four consecutive discrete quarters. A discrete quarter is
  a reported three-month fact, else the difference of two year-to-date facts of one fiscal year
  and one tag (six months minus three, nine minus six, and the fourth quarter as the annual
  figure minus nine months). The two facts must have been filed within ``DERIVE_GAP`` days of
  each other (one restatement generation: a restated annual figure is not subtracted from an
  unrestated nine-month figure) and a derived revenue quarter is never negative. Used when the
  newest quarter ends on or after the newest annual period;
- ``ANNUAL``: the latest fiscal year, when four quarters cannot be formed or the annual
  figure is newer (a filer that reports only annually);
- null when neither exists.

``revenue_ttm_year_ago`` and ``eps_diluted_ttm_year_ago`` are the same TTMs one year earlier
(each concept's own, so its growth is measured over its own TTM): four quarters ending 340 to
380 days before the newest one, or the previous fiscal year; null when that history is missing
or has a gap, so growth is never measured over more than a year.

The latest quarter (``revenue_qtr``, ``eps_diluted_qtr``) is the newest discrete quarter, as
above: a three-month fact as filed (a 10-Q), or for a 10-K the fourth quarter as the annual
figure minus the nine-month year-to-date figure (the same subtraction, with its restatement
and tag guards, that forms the TTM; for revenue and net income that equals the annual minus
the three quarters). It is null when the annual figure is newer than the newest quarter (the
fourth quarter cannot be derived: it would show a quarter that is not the latest). The same
quarter a year earlier (``*_qtr_year_ago``) is the discrete quarter ending 340 to 380 days
before it. ``qtr_as_of`` is the quarter's end; a concept whose latest quarter ends earlier
than the other's is null, so every non-null quarter column is of that one quarter, and all of
them are null when it ended more than ``stale_days`` before the session.

Diluted EPS is split-adjusted per fact: a fact filed before a split that took effect on or
before the session is divided by its ratio (filers restate the figures they file after a split),
so ``pe_ratio`` divides a split-adjusted close by a comparable EPS. The TTM EPS is the sum of
the quarterly figures, as quarterly EPS is not additive across share count changes this is an
approximation, the standard one. Every instrument of a CIK gets the company's figures
(``instruments/shares``): fine for share classes with equal economics, wrong for classes that
are not; an ADR's EPS is per ordinary share and the ADR ratio is not stored, so ``is_adr`` rows
get no P/E.

    revenue_ttm, net_income_ttm, eps_diluted_ttm   the TTMs (USD, USD, USD per share)
    revenue_ttm_year_ago, eps_diluted_ttm_year_ago the revenue and EPS TTMs a year earlier
    revenue_fy, revenue_fy_end                     the latest fiscal year's revenue and end
    ttm_as_of, ttm_filed, ttm_basis                the period end, filing date and basis of the
                                                   first TTM present of revenue, net income, EPS
    revenue_qtr, eps_diluted_qtr                   the latest quarter's revenue and diluted EPS
    revenue_qtr_year_ago, eps_diluted_qtr_year_ago the same quarter a year earlier
    qtr_as_of                                      the end of that quarter
    eps_stale                                      the EPS TTM itself is older than stale_days
    is_adr                                         the instrument is an ADR
    financials_status                              OK / PARTIAL / NO_TTM / NO_FACTS / STALE
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.ttm import (
    DERIVE_GAP,
    QUARTER_GAP,
    SPANS,
    YEAR_GAP,
    Fact,
    Quarters,
    Total,
    TtmParams,
    annual,
    discrete_quarters,
    latest_quarter,
    months,
    trailing,
)

__all__ = [
    "DERIVE_GAP",
    "GROUP",
    "QUARTER_GAP",
    "SPANS",
    "YEAR_GAP",
    "Quarters",
    "annual",
    "discrete_quarters",
    "latest_quarter",
    "months",
    "trailing",
]

NAME = "financials"
VERSION = 3
FACTS = "instruments/shares_accepted"  # by acceptance session, not by filing date
PRICE_STATS = "rollups/instrument/price_stats@v2"
SPLITS = "events/split"
REVENUE, NET_INCOME, EPS = "revenue", "net_income", "eps_diluted"
CONCEPTS = (REVENUE, NET_INCOME, EPS)
STATUSES = ("OK", "PARTIAL", "NO_TTM", "NO_FACTS", "STALE")
ADR = "ADR"
# The revenue tags, best first (the stored ``tag``); any other tag ranks last.
TAG_RANK = {
    "us-gaap:Revenues": 0,
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": 1,
    "us-gaap:SalesRevenueNet": 2,
}
REFERENCE = "instruments/reference"

_NO_FACTS = (
    "no revenue / net income / EPS fact public by the session's close (ETFs, funds, no CIK, "
    "issuers that report outside USD): NO_FACTS"
)
_COLS = tuple(f"{FACTS}.{c}" for c in ("concept", "value", "period_start", "period_end", "filed"))
_WHY_TTM = "; or neither four consecutive quarters nor a fiscal year of this concept are known"
_WHY_QTR_DATE = (
    "; or no discrete quarter can be formed (a fourth quarter needs the nine-month and the "
    "annual figure of one tag, filed close together), the annual figure is newer than the "
    "newest quarter, or the quarter ended more than stale_days (480) before the session"
)
_WHY_QTR = (
    _WHY_QTR_DATE + "; or this concept's newest quarter is older than the other concept's "
    "(every quarter column is of the one quarter qtr_as_of)"
)

FEATURES = (
    Feature(
        "revenue_ttm", "float", "usd",
        "Revenue over the trailing twelve months: the last four discrete quarters, else the "
        "latest fiscal year (us-gaap Revenues, else RevenueFromContractWithCustomer..., else "
        "SalesRevenueNet)",
        _NO_FACTS + _WHY_TTM, valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "revenue_ttm_year_ago", "float", "usd",
        "The revenue TTM one year earlier (the four quarters ending four quarters before, or "
        "the previous fiscal year): the base of revenue_growth_yoy",
        _NO_FACTS + "; or fewer than eight quarters (two fiscal years) of history",
        valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "net_income_ttm", "float", "usd",
        "Net income (NetIncomeLoss) over the trailing twelve months; negative for a loss",
        _NO_FACTS + _WHY_TTM, valid_range=(None, None), inputs=_COLS,
    ),
    Feature(
        "eps_diluted_ttm", "float32", "usd_per_share",
        "Diluted EPS (EarningsPerShareDiluted) over the trailing twelve months, summed from "
        "the quarters, split-adjusted to the session; negative for a loss",
        _NO_FACTS + _WHY_TTM, valid_range=(None, None), inputs=(*_COLS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "eps_diluted_ttm_year_ago", "float32", "usd_per_share",
        "The diluted EPS TTM one year earlier (the four quarters ending four quarters before "
        "the EPS TTM, or the previous fiscal year; split-adjusted like eps_diluted_ttm): the "
        "base of eps_growth_yoy",
        _NO_FACTS + "; or no EPS TTM; or fewer than eight quarters (two fiscal years) of EPS "
        "history, or a gap in them", valid_range=(None, None),
        inputs=(*_COLS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "revenue_fy", "float", "usd", "Revenue of the latest fiscal year reported",
        _NO_FACTS + "; or no annual revenue fact filed", valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "revenue_fy_end", "date", "date", "The end of that fiscal year",
        _NO_FACTS + "; or no annual revenue fact filed", inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "ttm_as_of", "date", "date",
        "The period end of the first TTM present of revenue, net income and EPS (the last "
        "quarter, or the fiscal year end of an annual one)",
        _NO_FACTS, inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "ttm_filed", "date", "date",
        "The filing date of the newest filing behind that TTM (it counts from the session whose "
        "close is after SEC's acceptance of it, not from this date)",
        _NO_FACTS, inputs=(f"{FACTS}.filed",),
    ),
    Feature(
        "ttm_basis", "str", "category",
        "QUARTERS: that TTM is the sum of four quarters; ANNUAL: it is the latest fiscal year "
        "(the other TTMs may differ)",
        _NO_FACTS, "label", categories=("QUARTERS", "ANNUAL"), inputs=(f"{FACTS}.period_start",),
    ),
    Feature(
        "revenue_qtr", "float", "usd",
        "Revenue of the latest reported quarter: a 10-Q's three-month figure as filed, or for a "
        "10-K the fourth quarter as the annual figure minus the nine months (one tag)",
        _NO_FACTS + _WHY_QTR, valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "revenue_qtr_year_ago", "float", "usd",
        "Revenue of the same quarter one year earlier (the discrete quarter ending 340 to 380 "
        "days before qtr_as_of): the base of revenue_growth_qtr_yoy",
        _NO_FACTS + _WHY_QTR + "; or the quarter a year earlier is not known",
        valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "eps_diluted_qtr", "float32", "usd_per_share",
        "Diluted EPS of the latest reported quarter (as filed, or for a 10-K the annual figure "
        "minus the nine months), split-adjusted to the session; negative for a loss",
        _NO_FACTS + _WHY_QTR, valid_range=(None, None), inputs=(*_COLS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "eps_diluted_qtr_year_ago", "float32", "usd_per_share",
        "Diluted EPS of the same quarter one year earlier, split-adjusted to the session: the "
        "base of eps_growth_qtr_yoy",
        _NO_FACTS + _WHY_QTR + "; or the quarter a year earlier is not known",
        valid_range=(None, None), inputs=(*_COLS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "qtr_as_of", "date", "date",
        "The end of the latest reported quarter that revenue_qtr and eps_diluted_qtr describe",
        _NO_FACTS + _WHY_QTR_DATE,
        inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "eps_stale", "bool", "flag",
        "The EPS TTM's own period ended more than stale_days (480) before the session: the "
        "value is shown but pe_ratio is null",
        "there is no EPS TTM (see eps_diluted_ttm)", inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "is_adr", "bool", "flag",
        "The instrument is an ADR: its per-share figures are per ordinary share and the ADR "
        "ratio is not stored, so pe_ratio is null",
        "never (false without an instruments/reference snapshot)",
        inputs=(f"{REFERENCE}.security_type",),
    ),
    Feature(
        "financials_status", "str", "category",
        "OK (all three TTMs); PARTIAL (some); NO_TTM (facts, but no TTM can be formed); "
        "NO_FACTS (none filed); STALE (the first TTM present ended more than stale_days, 480, "
        "before the session; the values are still shown)",
        "never", "label", categories=STATUSES, inputs=(f"{FACTS}.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


FinancialsParams = TtmParams


def split_lookback(p: FinancialsParams) -> int:
    """Sessions of splits loaded: more than ``history_days`` calendar days."""
    return int(p.history_days * 252 / 365) + 10


def _days(values: pd.Series) -> np.ndarray:
    return pd.to_datetime(values).to_numpy(dtype="datetime64[D]").astype(np.int64)


def _date(days: int | None) -> date | None:
    return None if days is None else date(1970, 1, 1) + timedelta(days=days)


def split_adjusted(facts: pd.DataFrame, splits: pd.DataFrame | None, session: date) -> pd.Series:
    """EPS values divided by the ratios of the splits that took effect after the fact was
    filed, up to the session."""
    values = facts["value"].astype(float)
    if splits is None or splits.empty or facts.empty:
        return values
    ratios = splits.assign(day=_days(splits["event_date"]))
    ratios = ratios[ratios["day"] <= (session - date(1970, 1, 1)).days]
    both = (
        facts[["instrument_id", "filed"]]
        .reset_index()
        .merge(ratios[["instrument_id", "day", "ratio"]], on="instrument_id")
    )
    both = both[both["filed"] < both["day"]]
    factor = both.groupby("index")["ratio"].prod().astype(float)
    return values / factor.reindex(facts.index).fillna(1.0)


def prepare_facts(
    facts: pd.DataFrame | None, splits: pd.DataFrame | None, session: date, p: FinancialsParams
) -> pd.DataFrame:
    """The concepts' facts: epoch-day periods, EPS split-adjusted, only the newest value of
    each period, in (instrument, concept, period) order."""
    columns = ["instrument_id", "concept", "start", "end", "value", "filed", "rank"]
    if facts is None or facts.empty or "value" not in facts.columns:
        return pd.DataFrame(columns=columns)
    rows = facts[facts["concept"].isin(CONCEPTS) & facts["value"].notna()].copy()
    rows = rows[rows["period_start"].notna() & rows["period_end"].notna()]
    out = pd.DataFrame(
        {
            "instrument_id": rows["instrument_id"].astype(str),
            "concept": rows["concept"],
            "start": _days(rows["period_start"]),
            "end": _days(rows["period_end"]),
            "value": rows["value"].astype(float),
            "filed": _days(rows["filed"]),
            "tag": rows["tag"].astype(str) if "tag" in rows.columns else "",
        }
    )
    out["rank"] = out["tag"].map(TAG_RANK).fillna(len(TAG_RANK)).astype(int)
    out = out[out["end"] >= (session - timedelta(days=p.history_days) - date(1970, 1, 1)).days]
    eps = out["concept"] == EPS
    out.loc[eps, "value"] = split_adjusted(out[eps], splits, session)
    key = ["instrument_id", "concept", "tag", "start", "end"]
    out = out.sort_values([*key, "filed"], kind="stable")
    return out.drop_duplicates(key, keep="last")[columns]


type Latest = dict[str, tuple[tuple[int, float, int], float | None]]


def _quarters(latest: Latest, stale_before: int) -> tuple[int | None, Latest]:
    """The one quarter the quarter columns describe: the newest end among revenue and EPS (none
    when it ended before ``stale_before``) and the concepts whose latest quarter is that one."""
    ends = [latest[c][0][0] for c in (REVENUE, EPS) if c in latest]
    if not ends or max(ends) < stale_before:
        return None, {}
    end = max(ends)
    return end, {c: latest[c] for c in (REVENUE, EPS) if c in latest and latest[c][0][0] == end}


def _row(
    found: dict[str, tuple[Total, float | None]],
    latest: Latest,
    fiscal: Fact | None,
    stale_before: int,
    adr: bool,
) -> dict[str, object]:
    first = next((found[c][0] for c in CONCEPTS if c in found), None)  # revenue, else net income..
    if first is None:
        status = "NO_TTM"
    elif first[1] < stale_before:
        status = "STALE"
    else:
        status = "OK" if len(found) == len(CONCEPTS) else "PARTIAL"
    revenue, eps = found.get(REVENUE), found.get(EPS)
    qtr_end, qtr = _quarters(latest, stale_before)
    rev_q, eps_q = qtr.get(REVENUE), qtr.get(EPS)
    return {
        "revenue_ttm": revenue[0][0] if revenue else None,
        "revenue_ttm_year_ago": revenue[1] if revenue else None,
        "net_income_ttm": found[NET_INCOME][0][0] if NET_INCOME in found else None,
        "eps_diluted_ttm": eps[0][0] if eps else None,
        "eps_diluted_ttm_year_ago": eps[1] if eps else None,
        "revenue_fy": fiscal[2] if fiscal else None,
        "revenue_fy_end": _date(fiscal[1]) if fiscal else None,
        "ttm_as_of": _date(first[1]) if first else None,
        "ttm_filed": _date(first[2]) if first else None,
        "ttm_basis": None if first is None else "ANNUAL" if first[3] else "QUARTERS",
        "revenue_qtr": rev_q[0][1] if rev_q else None,
        "revenue_qtr_year_ago": rev_q[1] if rev_q else None,
        "eps_diluted_qtr": eps_q[0][1] if eps_q else None,
        "eps_diluted_qtr_year_ago": eps_q[1] if eps_q else None,
        "qtr_as_of": _date(qtr_end),
        "eps_stale": None if eps is None else eps[0][1] < stale_before,
        "is_adr": adr,
        "financials_status": status,
    }


def _adrs(reference: pd.DataFrame | None) -> set[str]:
    if reference is None or "security_type" not in reference.columns:
        return set()
    return set(reference.loc[reference["security_type"] == ADR, "instrument_id"].astype(str))


def compute(inputs: Inputs, session: date, p: FinancialsParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id"]]
    rows = prepare_facts(inputs.get(FACTS), inputs.get(SPLITS), session, p)
    stale_before = (session - timedelta(days=p.stale_days) - date(1970, 1, 1)).days
    adrs = _adrs(inputs.get(REFERENCE))
    by_instrument: dict[str, dict[str, list[Fact]]] = {}
    for iid, concept, start, end, value, filed, rank in zip(
        *(rows[c].tolist() for c in rows.columns), strict=True
    ):
        facts = by_instrument.setdefault(iid, {}).setdefault(concept, [])
        facts.append((start, end, value, filed, rank))
    results = {}
    for iid, concepts in by_instrument.items():
        found = {c: t for c, f in concepts.items() if (t := trailing(f, c == REVENUE)) is not None}
        latest = {
            c: q
            for c, f in concepts.items()
            if c != NET_INCOME and (q := latest_quarter(f, c == REVENUE)) is not None
        }
        years = annual(concepts.get(REVENUE, []))
        results[iid] = _row(found, latest, years[-1] if years else None, stale_before, iid in adrs)
    ids = sorted(set(today["instrument_id"].astype(str)) | set(results))
    frame = pd.DataFrame(
        [results.get(i, {"financials_status": "NO_FACTS", "is_adr": i in adrs}) for i in ids]
    )
    return frame.assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Trailing-twelve-month revenue, net income and diluted EPS (and the TTMs a year earlier), "
    "the last fiscal year's revenue and the latest quarter's revenue and diluted EPS with the "
    "same quarter a year earlier (SEC company facts, point in time by SEC acceptance)",
    (
        Input(PRICE_STATS),
        Input(FACTS, required=False),
        Input(SPLITS, lookback=split_lookback, required=False),
        Input(REFERENCE, required=False),
    ),
    FEATURES,
    compute,
    FinancialsParams(),
)
