"""``financials@v1``: trailing-twelve-month revenue, net income and diluted EPS, last fiscal-year
revenue and the year-ago revenue TTM, from SEC company facts.

Inputs: ``instruments/shares`` rows of the concepts ``revenue``, ``net_income`` and
``eps_diluted`` (every fact FILED on or before the session, point in time by filing date), the
session's ``price_stats@v2`` (it sets which instruments get a row) and ``events/split``.

For each concept the latest known value of every reported period is used (a restatement
replaces the value from its filing date). A TTM is, in this order:

- ``QUARTERS``: the sum of the last four consecutive discrete quarters. A discrete quarter is
  a reported three-month fact, else the difference of year-to-date facts of one fiscal year
  (six months minus three, nine minus six, and the fourth quarter as the annual figure minus
  nine months). Used when the newest quarter ends on or after the newest annual period;
- ``ANNUAL``: the latest fiscal year, when four quarters cannot be formed or the annual
  figure is newer (a filer that reports only annually);
- null when neither exists.

``revenue_ttm_year_ago`` is the same TTM one year earlier (the four quarters ending four
quarters before, or the previous fiscal year), so growth is the expression feature
``revenue_growth_yoy``. Diluted EPS is split-adjusted per fact: a fact filed before a split that
took effect on or before the session is divided by its ratio (filers restate the figures they
file after a split), so ``pe_ratio`` divides a split-adjusted close by a comparable EPS. The
TTM EPS is the sum of the quarterly figures, as quarterly EPS is not additive across share
count changes this is an approximation, the standard one.

    revenue_ttm, net_income_ttm, eps_diluted_ttm   the TTMs (USD, USD, USD per share)
    revenue_ttm_year_ago                           the revenue TTM a year earlier
    revenue_fy, revenue_fy_end                     the latest fiscal year's revenue and end
    ttm_as_of, ttm_filed                           the oldest TTM period end (all are current to
                                                   at least this date) / the newest filing date
    ttm_basis                                      QUARTERS, or ANNUAL when any TTM is annual
    financials_status                              OK / PARTIAL / NO_TTM / NO_FACTS / STALE
"""

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "financials"
VERSION = 1
FACTS = "instruments/shares"
PRICE_STATS = "rollups/instrument/price_stats@v2"
SPLITS = "events/split"
REVENUE, NET_INCOME, EPS = "revenue", "net_income", "eps_diluted"
CONCEPTS = (REVENUE, NET_INCOME, EPS)
STATUSES = ("OK", "PARTIAL", "NO_TTM", "NO_FACTS", "STALE")
# Months of a reported period by its length in days (52 / 53-week fiscal years included).
SPANS = ((3, 75, 105), (6, 160, 200), (9, 250, 290), (12, 340, 380))
QUARTER_GAP = (75, 105)  # days between the ends of consecutive quarters

_NO_FACTS = (
    "no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers "
    "that report outside USD): NO_FACTS"
)
_COLS = tuple(f"{FACTS}.{c}" for c in ("concept", "value", "period_start", "period_end", "filed"))
_WHY_TTM = "; or neither four consecutive quarters nor a fiscal year of this concept are known"

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
        "revenue_fy", "float", "usd", "Revenue of the latest fiscal year reported",
        _NO_FACTS + "; or no annual revenue fact filed", valid_range=(0, None), inputs=_COLS,
    ),
    Feature(
        "revenue_fy_end", "date", "date", "The end of that fiscal year",
        _NO_FACTS + "; or no annual revenue fact filed", inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "ttm_as_of", "date", "date",
        "The oldest period end among the TTMs shown: all of them are current to at least this "
        "date (the last quarter, or the fiscal year end of an annual one)",
        _NO_FACTS, inputs=(f"{FACTS}.period_end",),
    ),
    Feature(
        "ttm_filed", "date", "date",
        "The newest filing date behind the TTMs (when they were public)",
        _NO_FACTS, inputs=(f"{FACTS}.filed",),
    ),
    Feature(
        "ttm_basis", "str", "category",
        "QUARTERS: every TTM is the sum of four quarters; ANNUAL: at least one is the latest "
        "fiscal year",
        _NO_FACTS, "label", categories=("QUARTERS", "ANNUAL"), inputs=(f"{FACTS}.period_start",),
    ),
    Feature(
        "financials_status", "str", "category",
        "OK (all three TTMs); PARTIAL (some); NO_TTM (facts, but no TTM can be formed); "
        "NO_FACTS (none filed); STALE (the oldest TTM ended more than stale_days, 480, "
        "before the session; the values are still shown)",
        "never", "label", categories=STATUSES, inputs=(f"{FACTS}.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class FinancialsParams:
    stale_days: int = 480  # the oldest TTM period ended longer ago: STALE
    history_days: int = 1100  # facts whose period ended earlier than this are not read

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError(f"stale_days must be >= 1, got {self.stale_days}")
        if self.history_days < 800:
            raise ValueError(
                f"history_days must be >= 800 (eight quarters), got {self.history_days}"
            )


def split_lookback(p: FinancialsParams) -> int:
    """Sessions of splits loaded: more than ``history_days`` calendar days."""
    return int(p.history_days * 252 / 365) + 10


type Fact = tuple[int, int, float, int]  # period start, end (epoch days), value, filed
type Total = tuple[float, int, int, bool]  # value, newest period end, newest filed, annual
type Quarters = list[tuple[int, float, int]]  # end, value, filed; ascending by end


def months(start: int, end: int) -> int:
    """3 / 6 / 9 / 12 for a quarter, half year, nine months or year; 0 for any other span."""
    return next((m for m, lo, hi in SPANS if lo <= end - start <= hi), 0)


def discrete_quarters(facts: list[Fact]) -> Quarters:
    """The discrete quarters the periods give: reported three-month facts, else the
    difference of two year-to-date periods of one fiscal year (same start)."""
    ytd = {(s, months(s, e)): (e, v, f) for s, e, v, f in facts}
    out = {e: (v, f) for (s, m), (e, v, f) in ytd.items() if m == 3}
    for (start, m), (end, value, filed) in sorted(ytd.items()):
        before = ytd.get((start, m - 3))
        if m in (6, 9, 12) and end not in out and before is not None:
            out[end] = (value - before[1], max(filed, before[2]))
    return [(e, v, f) for e, (v, f) in sorted(out.items())]


def _four(quarters: Quarters, last: int) -> tuple[float, int] | None:
    """Sum and newest filing date of the four quarters ending at index ``last``, when they
    are consecutive."""
    if last < 3:
        return None
    window = quarters[last - 3 : last + 1]
    gaps = [b[0] - a[0] for a, b in pairwise(window)]
    if not all(QUARTER_GAP[0] <= g <= QUARTER_GAP[1] for g in gaps):
        return None
    return sum(q[1] for q in window), max(q[2] for q in window)


def annual(facts: list[Fact]) -> list[Fact]:
    return sorted((x for x in facts if months(x[0], x[1]) == 12), key=lambda x: x[1])


def trailing(facts: list[Fact]) -> tuple[Total, float | None] | None:
    """``(TTM, year-ago TTM)`` of one concept's periods, or ``None`` when no TTM can be formed.
    ``TTM`` is ``(value, newest period end, newest filing date, annual?)``."""
    quarters = discrete_quarters(facts)
    years = annual(facts)
    last = _four(quarters, len(quarters) - 1)
    if last is not None and (not years or quarters[-1][0] >= years[-1][1]):
        ago = _four(quarters, len(quarters) - 5)
        return (last[0], quarters[-1][0], last[1], False), None if ago is None else ago[0]
    if not years:
        return None
    _, end, value, filed = years[-1]
    before = [x[2] for x in years if 340 <= end - x[1] <= 380]
    return (value, end, filed, True), before[-1] if before else None


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


def _prepare(
    facts: pd.DataFrame | None, splits: pd.DataFrame | None, session: date, p: FinancialsParams
) -> pd.DataFrame:
    """The concepts' facts: epoch-day periods, EPS split-adjusted, only the newest value of
    each period, in (instrument, concept, period) order."""
    columns = ["instrument_id", "concept", "start", "end", "value", "filed"]
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
        }
    )
    out = out[out["end"] >= (session - timedelta(days=p.history_days) - date(1970, 1, 1)).days]
    eps = out["concept"] == EPS
    out.loc[eps, "value"] = split_adjusted(out[eps], splits, session)
    out = out.sort_values(["instrument_id", "concept", "start", "end", "filed"], kind="stable")
    return out.drop_duplicates(["instrument_id", "concept", "start", "end"], keep="last")[columns]


def _row(
    found: dict[str, tuple[Total, float | None]], fiscal: Fact | None, stale_before: int
) -> dict[str, object]:
    totals = [t for t, _ in found.values()]
    as_of = min((t[1] for t in totals), default=None)  # current to at least this date
    if as_of is None:
        status = "NO_TTM"
    elif as_of < stale_before:
        status = "STALE"
    else:
        status = "OK" if len(totals) == len(CONCEPTS) else "PARTIAL"
    revenue = found.get(REVENUE)
    return {
        "revenue_ttm": revenue[0][0] if revenue else None,
        "revenue_ttm_year_ago": revenue[1] if revenue else None,
        "net_income_ttm": found[NET_INCOME][0][0] if NET_INCOME in found else None,
        "eps_diluted_ttm": found[EPS][0][0] if EPS in found else None,
        "revenue_fy": fiscal[2] if fiscal else None,
        "revenue_fy_end": _date(fiscal[1]) if fiscal else None,
        "ttm_as_of": _date(as_of),
        "ttm_filed": _date(max((t[2] for t in totals), default=None)),
        "ttm_basis": None if not totals else "ANNUAL" if any(t[3] for t in totals) else "QUARTERS",
        "financials_status": status,
    }


def compute(inputs: Inputs, session: date, p: FinancialsParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id"]]
    rows = _prepare(inputs.get(FACTS), inputs.get(SPLITS), session, p)
    stale_before = (session - timedelta(days=p.stale_days) - date(1970, 1, 1)).days
    by_instrument: dict[str, dict[str, list[Fact]]] = {}
    for iid, concept, start, end, value, filed in zip(
        *(rows[c].tolist() for c in rows.columns), strict=True
    ):
        by_instrument.setdefault(iid, {}).setdefault(concept, []).append((start, end, value, filed))
    results = {}
    for iid, concepts in by_instrument.items():
        found = {c: t for c, f in concepts.items() if (t := trailing(f)) is not None}
        years = annual(concepts.get(REVENUE, []))
        results[iid] = _row(found, years[-1] if years else None, stale_before)
    ids = sorted(set(today["instrument_id"].astype(str)) | set(results))
    empty = {"financials_status": "NO_FACTS"}
    frame = pd.DataFrame([results.get(i, empty) for i in ids])
    return frame.assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Trailing-twelve-month revenue, net income and diluted EPS and the last fiscal year's "
    "revenue (SEC company facts, point in time by filing date)",
    (
        Input(PRICE_STATS),
        Input(FACTS, required=False),
        Input(SPLITS, lookback=split_lookback, required=False),
    ),
    FEATURES,
    compute,
    FinancialsParams(),
)
