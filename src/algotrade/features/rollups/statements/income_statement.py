"""``income_statement@v1``: trailing-twelve-month income statement lines from the SEC statements.

Inputs: ``instruments/statements`` rows of the concepts ``cost_of_revenue``, ``gross_profit``,
``operating_income``, ``da``, ``interest_expense``, ``pretax_income`` and ``income_tax`` (every
fact FILED on or before the session: a restatement filed later never moves a session, ADR 0067),
the session's ``price_stats@v2`` (it sets which instruments get a row) and
``instruments/company`` (the SIC code).

Each line's TTM is formed as ``financials@v2``'s are (``ttm.trailing``): the last four
consecutive discrete quarters (a reported three-month fact, else the difference of two
year-to-date facts of one fiscal year and one tag filed close together), else the latest fiscal
year. A period takes the first tag of its concept's list that reports it (``statement_concepts``,
best first); a quarter is never derived across tags. A line the filer does not tag is null, never
zero; gross profit is not derived from revenue less cost of revenue.

Banks, brokers and insurers (SIC 6000 to 6411) get ``is_status`` FINANCIAL and null EBIT, D&A
and interest expense: their operating income, interest and debt are not those of an operating
company (owner decision; ADR 0067). Pretax income, tax, gross profit and cost of revenue are
kept as reported.

    gross_profit_ttm, cost_of_revenue_ttm   the TTMs (USD)
    ebit_ttm                                operating income (OperatingIncomeLoss)
    da_ttm, interest_expense_ttm            depreciation and amortisation, interest expense
    pretax_income_ttm, income_tax_ttm       income before tax and the tax charge
    is_ttm_as_of                            the period end of the first TTM present
    is_status                               OK / PARTIAL / NO_FACTS / STALE / FINANCIAL
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.lines import (
    COMPANY,
    FIELDS,
    PRICE_STATS,
    STATEMENTS,
    StatementParams,
    day_date,
    financial_ids,
    lines,
    stale_before,
    tag_ranks,
    totals,
)
from algotrade.features.rollups.statements.ttm import Total

NAME = "income_statement"
VERSION = 1
STATUSES = ("OK", "PARTIAL", "NO_FACTS", "STALE", "FINANCIAL")
# Each concept's us-gaap tags, best first (the same lists as ``statement_concepts.py``, which a
# test compares: a rollup imports no vendor package).
CONCEPT_TAGS = {
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax": ("IncomeTaxExpenseBenefit",),
    "interest_expense": ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
    "da": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ),
}
RANKS = tag_ranks(CONCEPT_TAGS)
COLUMN_OF = {  # concept -> the TTM column, in the order the as-of date looks for one
    "operating_income": "ebit_ttm",
    "pretax_income": "pretax_income_ttm",
    "income_tax": "income_tax_ttm",
    "gross_profit": "gross_profit_ttm",
    "cost_of_revenue": "cost_of_revenue_ttm",
    "da": "da_ttm",
    "interest_expense": "interest_expense_ttm",
}
EBIT_FAMILY = ("operating_income", "da", "interest_expense")  # null for a financial company
CORE = ("operating_income", "pretax_income", "income_tax")  # OK needs all three
NON_NEGATIVE = ("cost_of_revenue",)  # a derived quarter below zero is a restatement mismatch

_WHY = (
    "no income statement line filed by the session (ETFs, funds, no CIK, issuers that report "
    "outside USD), or no TTM can be formed (neither four consecutive quarters nor a fiscal year "
    "of this line): NO_FACTS"
)
_UNTAGGED = "; or the filer does not report this line under any of its tags (never zero)"
_FIN = "; or the issuer is a bank, broker or insurer (SIC 6000 to 6411): FINANCIAL"


def _ttm(name: str, description: str, low: float | None = None, fin: bool = False) -> Feature:
    return Feature(
        name, "float", "usd", description, _WHY + _UNTAGGED + (_FIN if fin else ""),
        valid_range=(low, None), inputs=FIELDS,
    )  # fmt: skip


FEATURES = (
    _ttm(
        "gross_profit_ttm",
        "Gross profit (GrossProfit as the filer reports it, never revenue less cost) over the "
        "trailing twelve months",
    ),
    _ttm(
        "cost_of_revenue_ttm",
        "Cost of revenue (CostOfRevenue, else CostOfGoodsAndServicesSold, else CostOfGoodsSold) "
        "over the trailing twelve months",
        low=0,
    ),
    _ttm(
        "ebit_ttm",
        "Operating income (OperatingIncomeLoss) over the trailing twelve months, the EBIT of "
        "every ratio built on it; negative for an operating loss",
        fin=True,
    ),
    _ttm(
        "da_ttm",
        "Depreciation and amortisation (DepreciationDepletionAndAmortization, else "
        "DepreciationAndAmortization, else DepreciationAmortizationAndAccretionNet) over the "
        "trailing twelve months: EBITDA is ebit_ttm plus this",
        fin=True,
    ),
    _ttm(
        "interest_expense_ttm",
        "Interest expense (InterestExpense, else InterestExpenseNonoperating, else "
        "InterestExpenseDebt) over the trailing twelve months, a positive cost",
        fin=True,
    ),
    _ttm(
        "pretax_income_ttm",
        "Income from continuing operations before income taxes over the trailing twelve months; "
        "negative for a loss",
    ),
    _ttm(
        "income_tax_ttm",
        "Income tax expense (IncomeTaxExpenseBenefit) over the trailing twelve months; negative "
        "for a net benefit",
    ),
    Feature(
        "is_ttm_as_of", "date", "date",
        "The period end of the first TTM present (operating income, else pretax income, tax, "
        "gross profit, cost of revenue, D&A, interest): the last quarter, or the fiscal year end "
        "of an annual one",
        _WHY, inputs=("instruments/statements.period_end",),
    ),
    Feature(
        "is_status", "str", "category",
        "OK (operating income, pretax income and tax all have a TTM); PARTIAL (some line has a "
        "TTM, not all three); NO_FACTS (no line has one); STALE (the first TTM present ended more "
        "than stale_days, 480, before the session; values still shown); FINANCIAL (SIC 6000 to "
        "6411: the EBIT family is null)",
        "never", "label", categories=STATUSES, inputs=("instruments/statements.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _row(found: dict[str, Total], financial: bool, before: int) -> dict[str, object]:
    if not found:
        return {"is_status": "NO_FACTS"}
    if financial:
        found = {c: t for c, t in found.items() if c not in EBIT_FAMILY}
    first = next((found[c] for c in COLUMN_OF if c in found), None)
    if financial:
        status = "FINANCIAL"
    elif first is not None and first[1] < before:
        status = "STALE"
    else:
        status = "OK" if all(c in found for c in CORE) else "PARTIAL"
    row: dict[str, object] = {COLUMN_OF[c]: t[0] for c, t in found.items()}
    return {**row, "is_ttm_as_of": day_date(first[1]) if first else None, "is_status": status}


def compute(inputs: Inputs, session: date, p: StatementParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session]["instrument_id"].astype(str)
    by_instrument = lines(inputs.get(STATEMENTS), RANKS, session, p)
    financial = financial_ids(inputs.get(COMPANY))
    before = stale_before(session, p)
    ids = sorted(set(today) | set(by_instrument))
    rows = [
        _row(totals(by_instrument.get(i, {}), NON_NEGATIVE), i in financial, before) for i in ids
    ]
    return pd.DataFrame(rows).assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Trailing-twelve-month income statement lines (gross profit, cost of revenue, EBIT, D&A, "
    "interest expense, pretax income, income tax) from the SEC statements, point in time by "
    "filing date; the EBIT family is null for banks and insurers",
    (
        Input(PRICE_STATS),
        Input(STATEMENTS, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    StatementParams(),
)
