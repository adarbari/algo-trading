"""``mispricing@v1``: the Stambaugh-Yuan anomaly inputs, a QMJ-like quality score and the
cross-sectional composite rank, from the stored SEC statement groups.

Inputs: ``balance_sheet@v2``, ``income_statement@v2``, ``cash_flow@v2``, ``financials@v3`` and
``fundamentals@v4`` rows of the session (each already point in time by when its filing was public,
ADR 0067: a figure enters a session at its filing's acceptance, never at its period end), the SEC
INSTANT facts of ``instruments/statements_accepted`` (only for the total assets a year before the
balance sheet date) and the session's ``price_stats@v2`` (it sets which instruments get a row). A
value whose statement group is STALE is null, as in the expression features over the same groups;
a balance-sheet measure also needs ``bs_status`` OK (PARTIAL keeps a line at an older date), and
net income with operating cash flow need ``ttm_as_of`` equal to ``cf_as_of``.

A rank needs the whole cross-section, so the anomalies live here with their ranks (an expression
feature is one row at a time); the ratios mirror the TOML features ``roe``, ``roa``,
``gross_margin``, ``net_margin`` and ``debt_to_equity`` (balance sheet ones stricter: OK only).

    total_assets_1y_ago       Assets at the balance sheet a year before bs_as_of (+/- tolerance)
    asset_growth              total_assets / total_assets_1y_ago - 1
    accruals                  (net_income_ttm - ocf_ttm) / total_assets
    gross_profit_to_assets    gross_profit_ttm / total_assets
    net_operating_assets      (total_debt + equity - cash) / total_assets
    ohlson_o                  the simplified Ohlson O-score (terms omitted: see the feature)
    quality_score             the mean percentile rank of six quality measures, 0 to 1
    composite_rank            the mean percentile rank of seven anomalies, 0 to 1
    composite_inputs          how many anomalies composite_rank averaged

Missing never passes: an anomaly or quality measure that cannot be formed is left out of its
average, and a score with fewer than ``min_quality_inputs`` / ``min_anomalies`` measures, or a
cross-section with fewer than ``min_members`` known values of a measure, is null (UNKNOWN).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.instants import LINES, Book, books
from algotrade.features.rollups.statements.lines import (
    EPOCH,
    FIELDS,
    PRICE_STATS,
    STATEMENTS,
)
from algotrade.features.rollups.statements.ttm import TtmParams

NAME = "mispricing"
VERSION = 1
BALANCE = "rollups/instrument/balance_sheet@v2"
INCOME = "rollups/instrument/income_statement@v2"
CASH_FLOW = "rollups/instrument/cash_flow@v2"
FINANCIALS = "rollups/instrument/financials@v3"
FUNDAMENTALS = "rollups/instrument/fundamentals@v4"
ASSETS_TAG = LINES["assets"][0]
YEAR_DAYS = 365
# Overpriced when HIGH: the first five; the last two are underpriced when high (inverted).
OVER_HIGH = ("net_issuance", "accruals", "net_operating_assets", "asset_growth", "ohlson_o")
OVER_LOW = ("gross_profit_to_assets", "roa")
RAW_COLUMNS = (
    "total_assets_1y_ago", "asset_growth", "accruals", "gross_profit_to_assets",
    "net_operating_assets", "ohlson_o",
)  # fmt: skip


@dataclass(frozen=True)
class MispricingParams(TtmParams):
    """``TtmParams`` plus how the ranks are formed."""

    ago_tolerance_days: int = 40  # the balance sheet a year back ends within this of the date
    min_members: int = 100  # instruments with a known value a percentile rank needs
    min_quality_inputs: int = 4  # of the six quality measures
    min_anomalies: int = 5  # of the seven composite anomalies

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.ago_tolerance_days < 1:
            raise ValueError(f"ago_tolerance_days must be >= 1, got {self.ago_tolerance_days}")
        if self.min_members < 2:
            raise ValueError(f"min_members must be >= 2, got {self.min_members}")
        if not 1 <= self.min_quality_inputs <= 6:
            raise ValueError(f"min_quality_inputs must be in [1, 6], got {self.min_quality_inputs}")
        if not 1 <= self.min_anomalies <= len(OVER_HIGH) + len(OVER_LOW):
            raise ValueError(f"min_anomalies must be in [1, 7], got {self.min_anomalies}")


_STATEMENT = (
    "no balance sheet, income statement, cash flow or net income of the session (ETFs, funds, no "
    "CIK, issuers that report outside USD), or one of them is STALE (its newest period ended "
    "more than stale_days, 480, before the session), or the balance sheet is PARTIAL (a core line "
    "at an older date than bs_as_of), or net income and operating cash flow end on different "
    "quarters (ttm_as_of differs from cf_as_of)"
)
_RANKED = (
    "; or fewer than min_members (100) instruments have a known value of this measure that "
    "session (the cross-section is too thin to rank)"
)
_BS_INPUTS = (
    "balance_sheet.total_assets@v2",
    "balance_sheet.bs_status@v2",
)

FEATURES = (
    Feature(
        "total_assets_1y_ago", "float", "usd",
        "Total assets (Assets) at the balance sheet a year before the latest one (bs_as_of): "
        "the newest balance sheet date in the facts public by the session that lies within "
        "ago_tolerance_days (40) of bs_as_of minus 365 days; a restatement public by the session "
        "replaces the original figure",
        "no balance sheet of the session, or it is STALE, or no Assets fact of a balance sheet "
        "a year back (a company reporting for less than a year, or a gap) or it is not positive",
        valid_range=(0, None), inputs=(*_BS_INPUTS, *FIELDS),
    ),
    Feature(
        "asset_growth", "float", "decimal",
        "Total asset growth over the year to the latest balance sheet: total_assets / "
        "total_assets_1y_ago - 1 (0.10 is +10%); the Cooper-Gulen-Schill investment anomaly, "
        "high growth tends to be followed by low returns",
        "total_assets or total_assets_1y_ago is null (see each)",
        valid_range=(-1, None), inputs=(*_BS_INPUTS, *FIELDS),
    ),
    Feature(
        "accruals", "float", "decimal",
        "Accruals: (net income over the trailing twelve months - operating cash flow over the "
        "same window) / total assets at the latest balance sheet (Sloan's balance-sheet "
        "scaling uses the average of two years; this uses the latest only); positive means "
        "earnings above cash, negative cash above earnings",
        _STATEMENT + "; or the issuer is a bank, broker or insurer (cash flows differ)",
        valid_range=(None, None),
        inputs=(
            *_BS_INPUTS,
            "financials.net_income_ttm@v3",
            "cash_flow.ocf_ttm@v2",
        ),
    ),
    Feature(
        "gross_profit_to_assets", "float", "decimal",
        "Gross profitability (Novy-Marx): gross profit over the trailing twelve months / total "
        "assets at the latest balance sheet; 0.30 is 30 cents of gross profit a year on each "
        "dollar of assets",
        _STATEMENT + "; or the filer does not tag GrossProfit (many do not); or the issuer is a "
        "bank, broker or insurer",
        valid_range=(None, None),
        inputs=(*_BS_INPUTS, "income_statement.gross_profit_ttm@v2"),
    ),
    Feature(
        "net_operating_assets", "float", "decimal",
        "Net operating assets (Hirshleifer-Hou-Teoh-Zhang): (total debt + stockholders' equity "
        "- cash) / total assets at the latest balance sheet, that is operating assets (assets "
        "less cash) minus operating liabilities (assets less debt and equity). Short-term "
        "investments, minority interest and preferred stock are not separated (treated as "
        "operating); scaled by the latest assets, not the year-ago ones",
        _STATEMENT + "; or total_debt is null (untagged debt is null, never zero); or the "
        "issuer is a bank, broker or insurer",
        valid_range=(None, None),
        inputs=(
            *_BS_INPUTS,
            "balance_sheet.total_debt@v2",
            "balance_sheet.stockholders_equity@v2",
            "balance_sheet.cash@v2",
        ),
    ),
    Feature(
        "ohlson_o", "float", "ratio",
        "A simplified Ohlson O-score (bankruptcy risk, higher is riskier): -1.32 - 0.407 ln(TA) "
        "+ 6.03 TL/TA - 1.43 (CA - CL)/TA + 0.0757 CL/CA - 1.72 [TL > TA] - 2.37 NI/TA - 1.83 "
        "FFO/TL, with TA total assets in dollars, TL total liabilities, CA and CL current "
        "assets and liabilities, NI net income and FFO operating cash flow (ocf_ttm), both over "
        "the trailing twelve months. OMITTED: the two terms that need last year's net income "
        "(INTWO, a loss in both of the last two years, and CHIN, the change in net income), "
        "which no group stores, and the GNP price-index deflator of the size term (a constant "
        "within a session, so cross-sectional ranks are unaffected, but levels are not "
        "comparable with the paper's or across sessions). It is a rank input, not a probability",
        _STATEMENT + "; or current assets, current liabilities, total liabilities or ocf_ttm is "
        "null (not tagged), a current asset or liability total is not positive, or the issuer is "
        "a bank, broker or insurer",
        inputs=(
            *_BS_INPUTS,
            "balance_sheet.total_liabilities@v2",
            "balance_sheet.current_assets@v2",
            "balance_sheet.current_liabilities@v2",
            "financials.net_income_ttm@v3",
            "cash_flow.ocf_ttm@v2",
        ),
    ),
    Feature(
        "quality_score", "float32", "decimal",
        "A QMJ-like quality score: the mean of the percentile ranks (0 lowest, 1 highest, among "
        "instruments with a value that session) of return on equity, return on assets, gross "
        "margin, net margin, operating cash flow / total assets and low debt to equity; 0.8 is "
        "better than about 80% of the cross-section on the average measure. It OMITS "
        "Asness-Frazzini-Pedersen's growth (five-year changes), payout (buybacks, dividends, "
        "accruals) and low-beta / low-volatility parts, uses one year of data (no five-year "
        "stability), ranks across all instruments rather than within an industry, and weights "
        "the six measures equally",
        "fewer than min_quality_inputs (4) of the six measures can be formed (each follows its "
        "own TOML feature: roe, roa, gross_margin, net_margin, debt_to_equity; the cash flow one "
        "needs ocf_ttm and total_assets)" + _RANKED,
        valid_range=(0, 1), kind="cross_section",
        inputs=(
            *_BS_INPUTS,
            "financials.net_income_ttm@v3",
            "financials.revenue_ttm@v3",
            "income_statement.gross_profit_ttm@v2",
            "cash_flow.ocf_ttm@v2",
        ),
    ),
    Feature(
        "composite_rank", "float32", "decimal",
        "The Stambaugh-Yuan style composite mispricing rank: the mean of the percentile ranks "
        "(among instruments with a value that session) of seven anomalies oriented so that "
        "high is overpriced: net issuance (shares_outstanding / a year earlier - 1), accruals, "
        "net_operating_assets, asset_growth, ohlson_o, and, inverted, gross_profit_to_assets "
        "and return on assets. 1 is the most overpriced (the short leg), 0 the most "
        "underpriced. OMITS four of their eleven: composite equity issuance and "
        "investment-to-assets (need cash flow detail not stored), financial distress "
        "(Campbell, needs returns and volatility) and momentum (price based, another group); "
        "it uses the simplified ohlson_o. An anomaly that cannot be formed is left out of the "
        "mean (see composite_inputs)",
        "fewer than min_anomalies (5) of the seven anomalies can be formed for the instrument"
        + _RANKED,
        valid_range=(0, 1), kind="cross_section",
        inputs=(
            *_BS_INPUTS,
            "fundamentals.shares_outstanding@v4",
            "fundamentals.shares_outstanding_year_ago@v4",
        ),
    ),
    Feature(
        "composite_inputs", "int", "count",
        "How many of the seven anomalies composite_rank averaged for the instrument (5 to 7 "
        "when composite_rank is known): a rank on five is less reliable than one on seven",
        "composite_rank is null", valid_range=(5, 7), kind="cross_section",
        inputs=(*_BS_INPUTS,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _table(inputs: Inputs, key: str, session: date, cols: tuple[str, ...]) -> pd.DataFrame:
    """The session's rows of one group by instrument, with every column in ``cols`` (NaN
    when the table or the column is missing)."""
    frame = inputs.get(key)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(cols))
    if "session_date" in frame.columns:
        frame = frame[pd.to_datetime(frame["session_date"]).dt.date == session]
    frame = frame.assign(instrument_id=frame["instrument_id"].astype(str)).set_index(
        "instrument_id"
    )
    return frame.reindex(columns=list(cols))


def _column(frame: pd.DataFrame, column: str, ids: pd.Index) -> pd.Series:
    return pd.to_numeric(frame[column].reindex(ids), errors="coerce").astype(float)


def _fresh(frame: pd.DataFrame, ids: pd.Index) -> pd.Series:
    """A status that exists and is not STALE."""
    status = frame["status"].reindex(ids)
    return status.notna() & (status != "STALE")


def _ratio(num: pd.Series, den: pd.Series, ok: pd.Series) -> pd.Series:
    """``num / den`` where ``den > 0`` and ``ok``; NaN elsewhere."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    return out.where((den > 0) & ok & np.isfinite(out))


def _assets_a_year_ago(
    book_by_id: dict[str, Book], as_of: pd.Series, ids: pd.Index, p: MispricingParams
) -> pd.Series:
    """Per instrument the Assets instant ending nearest to ``as_of`` minus a year, within the
    tolerance (NaN when none): the facts are already limited to filings accepted by the
    session, so a restatement accepted later is never read."""
    out = pd.Series(np.nan, index=ids, dtype=float)
    for iid in ids:
        end = as_of.get(iid)
        by_end = book_by_id.get(iid, {}).get(ASSETS_TAG)
        if not by_end or pd.isna(end):
            continue
        target = (pd.Timestamp(end).date() - EPOCH).days - YEAR_DAYS
        nearest = min(by_end, key=lambda e: abs(e - target))
        if abs(nearest - target) <= p.ago_tolerance_days:
            out[iid] = by_end[nearest][2]
    return out


def percentile(values: pd.Series, p: MispricingParams) -> pd.Series:
    """The percentile rank (0 lowest, 1 highest, ties share the average) of each known value
    among the known ones; all NaN when fewer than ``min_members`` are known."""
    known = values.notna()
    if known.sum() < p.min_members:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (values.rank(method="average") - 1) / (known.sum() - 1)


def _mean_rank(ranks: pd.DataFrame, minimum: int) -> tuple[pd.Series, pd.Series]:
    """The row mean of the known ranks and how many there were; NaN under ``minimum``."""
    count = ranks.notna().sum(axis=1)
    mean = ranks.mean(axis=1).where(count >= minimum)
    return mean, count.where(count >= minimum)


def measures(inputs: Inputs, session: date, p: MispricingParams) -> pd.DataFrame:
    """Every raw measure per instrument (ids: the session's, plus any with statement rows)."""
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    bs = _table(
        inputs, BALANCE, session,
        ("total_assets", "total_debt", "stockholders_equity", "cash", "total_liabilities",
         "current_assets", "current_liabilities", "bs_as_of", "is_financial", "bs_status"),
    )  # fmt: skip
    inc = _table(inputs, INCOME, session, ("gross_profit_ttm", "is_ttm_as_of", "is_status"))
    cf = _table(inputs, CASH_FLOW, session, ("ocf_ttm", "cf_as_of", "cf_status"))
    fin = _table(
        inputs, FINANCIALS, session,
        ("net_income_ttm", "revenue_ttm", "ttm_as_of", "financials_status"),
    )  # fmt: skip
    fun = _table(
        inputs, FUNDAMENTALS, session,
        ("shares_outstanding", "shares_outstanding_year_ago", "market_cap_status"),
    )  # fmt: skip
    today = stats[stats["session_date"] == session]["instrument_id"].astype(str)
    ids = pd.Index(sorted(set(today) | set(bs.index)), name="instrument_id")
    status = {
        # OK only: PARTIAL keeps a core line at an older date than bs_as_of, so a measure
        # mixing lines would mix balance sheet dates
        "bs": bs["bs_status"].reindex(ids) == "OK",
        "inc": _fresh(inc.rename(columns={"is_status": "status"}), ids),
        "cf": _fresh(cf.rename(columns={"cf_status": "status"}), ids),
        "fin": _fresh(fin.rename(columns={"financials_status": "status"}), ids),
        "fun": _fresh(fun.rename(columns={"market_cap_status": "status"}), ids),
    }
    bank = bs["is_financial"].reindex(ids).fillna(False).astype(bool)
    ta = _column(bs, "total_assets", ids)
    equity = _column(bs, "stockholders_equity", ids)
    debt = _column(bs, "total_debt", ids)
    liabilities = _column(bs, "total_liabilities", ids)
    ca, cl = _column(bs, "current_assets", ids), _column(bs, "current_liabilities", ids)
    ni, ocf = _column(fin, "net_income_ttm", ids), _column(cf, "ocf_ttm", ids)
    gp, revenue = _column(inc, "gross_profit_ttm", ids), _column(fin, "revenue_ttm", ids)
    bs_ok, fin_ok = status["bs"], status["fin"]
    ago = _assets_a_year_ago(
        books(inputs.get(STATEMENTS), session, p), bs["bs_as_of"].reindex(ids), ids, p
    ).where(bs_ok)
    ago = ago.where(ago > 0)
    ta_ok = ta.where(bs_ok & (ta > 0))
    cash_aligned = (
        (  # net income and operating cash flow end on the same quarter
            pd.to_datetime(fin["ttm_as_of"].reindex(ids))
            == pd.to_datetime(cf["cf_as_of"].reindex(ids))
        )
        & status["cf"]
        & fin_ok
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        ohlson = (
            -1.32 - 0.407 * np.log(ta_ok) + 6.03 * liabilities / ta_ok
            - 1.43 * (ca - cl) / ta_ok + 0.0757 * cl / ca - 1.72 * (liabilities > ta_ok)
            - 2.37 * ni / ta_ok - 1.83 * ocf / liabilities
        )  # fmt: skip
    ohlson_ok = (
        bs_ok & cash_aligned & ~bank & (ca > 0) & (cl > 0) & (liabilities > 0)
    ) & np.isfinite(ohlson)
    same_end = pd.to_datetime(inc["is_ttm_as_of"].reindex(ids)) == pd.to_datetime(
        fin["ttm_as_of"].reindex(ids)
    )  # NaT never equals NaT: an unknown end is not aligned
    aligned = same_end & status["inc"] & fin_ok
    out = pd.DataFrame(index=ids)
    out["total_assets_1y_ago"] = ago
    out["asset_growth"] = (ta_ok / ago - 1).where(ago.notna())
    out["accruals"] = _ratio(ni - ocf, ta, bs_ok & cash_aligned & ~bank)
    out["gross_profit_to_assets"] = _ratio(gp, ta, bs_ok & status["inc"] & ~bank)
    out["net_operating_assets"] = _ratio(
        debt + equity - _column(bs, "cash", ids), ta, bs_ok & ~bank
    )
    out["ohlson_o"] = ohlson.where(ohlson_ok)
    out["net_issuance"] = _ratio(
        _column(fun, "shares_outstanding", ids), _column(fun, "shares_outstanding_year_ago", ids),
        status["fun"],
    ) - 1  # fmt: skip
    out["roa"] = _ratio(ni, ta, bs_ok & fin_ok)
    out["roe"] = _ratio(ni, equity, bs_ok & fin_ok)
    out["gross_margin"] = _ratio(gp, revenue, aligned)
    out["net_margin"] = _ratio(ni, revenue, fin_ok)
    out["ocf_to_assets"] = _ratio(ocf, ta, bs_ok & status["cf"])
    out["debt_to_equity"] = _ratio(debt, equity, bs_ok)
    return out


def compute(inputs: Inputs, session: date, p: MispricingParams) -> pd.DataFrame:
    raw = measures(inputs, session, p)
    quality_ranks = pd.DataFrame(
        {
            "roe": percentile(raw["roe"], p),
            "roa": percentile(raw["roa"], p),
            "gross_margin": percentile(raw["gross_margin"], p),
            "net_margin": percentile(raw["net_margin"], p),
            "ocf_to_assets": percentile(raw["ocf_to_assets"], p),
            "low_debt": percentile(-raw["debt_to_equity"], p),
        }
    )
    anomaly_ranks = pd.DataFrame(
        {
            **{c: percentile(raw[c], p) for c in OVER_HIGH},
            **{c: 1 - percentile(raw[c], p) for c in OVER_LOW},
        }
    )
    quality, _ = _mean_rank(quality_ranks, p.min_quality_inputs)
    composite, used = _mean_rank(anomaly_ranks, p.min_anomalies)
    out = raw[list(RAW_COLUMNS)].copy()
    out["quality_score"] = quality
    out["composite_rank"] = composite
    out["composite_inputs"] = used.astype("Int64")
    return out.reset_index()


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The Stambaugh-Yuan anomaly inputs (asset growth, accruals, gross profitability, net "
    "operating assets, a simplified Ohlson O-score), a QMJ-like quality score and the "
    "cross-sectional composite mispricing rank, from the stored SEC statement groups, point in "
    "time by filing acceptance; missing inputs are left out of a rank and too few make it null",
    (
        Input(PRICE_STATS),
        Input(BALANCE, required=False),
        Input(INCOME, required=False),
        Input(CASH_FLOW, required=False),
        Input(FINANCIALS, required=False),
        Input(FUNDAMENTALS, required=False),
        Input(STATEMENTS, required=False),
    ),
    FEATURES,
    compute,
    MispricingParams(),
)
