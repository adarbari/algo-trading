"""``balance_sheet@v1``: the latest balance sheet lines from the SEC statements.

Inputs: ``instruments/statements`` INSTANT rows of the concepts ``cash``, ``sti``, ``debt``,
``assets``, ``liabilities``, ``equity`` and ``current`` (every fact FILED on or before the
session: a restatement filed later never moves a session, ADR 0067), the session's
``price_stats@v2`` (it sets which instruments get a row) and ``instruments/company`` (the SIC
code).

A balance sheet line is a balance at a date, not a flow: no TTM, no subtraction. Each line takes
its latest instant (``instants.pick``): the greatest period end, then the first tag of the line's
list that reports that end, never a mix of tags. ``bs_as_of`` is the newest period end of any
line; the status is OK only when the core lines (cash, total assets, equity) all end on it.

    cash, sti                 cash and equivalents; short-term investments (one tag, never summed)
    total_debt, debt_basis    the parts of ONE filing by rule a / b / c; NOT_TAGGED is null, never 0
    total_assets, equity      Assets; StockholdersEquity, else with the noncontrolling interest
    total_liabilities         Liabilities (REPORTED), else total less equity (DERIVED), else NONE
    current_assets, current_liabilities   AssetsCurrent, LiabilitiesCurrent
    bs_as_of, is_financial    the newest balance sheet date; SIC 6000 to 6411
    bs_status                 OK / PARTIAL / NO_FACTS / STALE

Banks keep their balance sheet (``is_financial`` only flags them): only the EBIT family of
``income_statement@v1`` is null for them.
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.statements.instants import (
    LINES,
    Book,
    Pick,
    books,
    debt_end,
    pick,
    total_debt,
    total_liabilities,
)
from algotrade.features.rollups.statements.lines import (
    COMPANY,
    FIELDS,
    PRICE_STATS,
    STATEMENTS,
    StatementParams,
    day_date,
    financial_ids,
    stale_before,
)

NAME = "balance_sheet"
VERSION = 1
STATUSES = ("OK", "PARTIAL", "NO_FACTS", "STALE")
DEBT_BASES = ("a", "b", "c", "NOT_TAGGED")
LIABILITIES_BASES = ("REPORTED", "DERIVED", "NONE")
COLUMN_OF = {  # line -> its column
    "cash": "cash",
    "sti": "sti",
    "assets": "total_assets",
    "equity": "equity",
    "current_assets": "current_assets",
    "current_liabilities": "current_liabilities",
}
CORE = ("cash", "assets", "equity")  # OK needs all three on the newest balance sheet date
INPUTS = (*FIELDS, f"{STATEMENTS}.accn")  # accn: the filing a debt part comes from

_WHY = (
    "no balance sheet line filed by the session (ETFs, funds, no CIK, issuers that report "
    "outside USD): NO_FACTS"
)
_UNTAGGED = "; or the filer does not report this line under any of its tags (never zero)"


def _line(name: str, description: str, low: float | None = 0) -> Feature:
    return Feature(
        name, "float", "usd", description, _WHY + _UNTAGGED,
        valid_range=(low, None), inputs=INPUTS,
    )  # fmt: skip


FEATURES = (
    _line(
        "cash",
        "Cash and cash equivalents (CashAndCashEquivalentsAtCarryingValue, else the figure "
        "that includes restricted cash) at the latest balance sheet date",
    ),
    _line(
        "sti",
        "Short-term investments (ShortTermInvestments, else MarketableSecuritiesCurrent, never "
        "both added) at the latest balance sheet date",
    ),
    Feature(
        "total_debt", "float", "usd",
        "Debt at the latest balance sheet date, added up from the parts of ONE filing by the "
        "first rule that applies (debt_basis): a) LongTermDebt plus short-term borrowings, else "
        "commercial paper; b) LongTermDebtNoncurrent plus LongTermDebtCurrent plus short-term "
        "borrowings, else commercial paper; c) DebtCurrent plus LongTermDebtNoncurrent",
        _WHY + "; or no filing has a complete set of debt parts (debt_basis NOT_TAGGED): a "
        "filer without the tags looks like a debt-free one, so the value is null, never zero",
        valid_range=(0, None), inputs=INPUTS,
    ),
    Feature(
        "debt_basis", "str", "category",
        "Which rule built total_debt: a, b or c, or NOT_TAGGED when no filing has a complete "
        "set of parts (total_debt is null)",
        "never when a balance sheet is filed; null with NO_FACTS", "label",
        categories=DEBT_BASES, inputs=INPUTS,
    ),
    _line("total_assets", "Total assets (Assets) at the latest balance sheet date"),
    _line(
        "total_liabilities",
        "Total liabilities: the reported Liabilities, else liabilities and stockholders' equity "
        "less equity of the same date (liabilities_basis says which)",
        low=None,
    ),
    Feature(
        "liabilities_basis", "str", "category",
        "REPORTED (the filer tags Liabilities); DERIVED (total liabilities and equity less "
        "equity, same date); NONE (neither can be formed)",
        "never when a balance sheet is filed; null with NO_FACTS", "label",
        categories=LIABILITIES_BASES, inputs=INPUTS,
    ),
    _line(
        "equity",
        "Stockholders' equity (StockholdersEquity, else the figure including the portion "
        "attributable to noncontrolling interests) at the latest balance sheet date; negative "
        "after accumulated losses or buybacks",
        low=None,
    ),
    _line("current_assets", "Current assets (AssetsCurrent) at the latest balance sheet date"),
    _line(
        "current_liabilities",
        "Current liabilities (LiabilitiesCurrent) at the latest balance sheet date",
    ),
    Feature(
        "bs_as_of", "date", "date",
        "The newest balance sheet date of any line: the period end of the quarter or fiscal "
        "year the lines are read at",
        _WHY, inputs=("instruments/statements.period_end",),
    ),
    Feature(
        "bs_filed", "date", "date",
        "The filing date of the newest balance sheet fact: the day the figures became public",
        _WHY, inputs=("instruments/statements.filed",),
    ),
    Feature(
        "is_financial", "bool", "flag",
        "The issuer is a bank, broker or insurer (SIC 6000 to 6411, instruments/company): its "
        "balance sheet is kept, only the EBIT family of income_statement@v1 is null",
        "never (false without an instruments/company snapshot)",
        inputs=("instruments/company.sic",),
    ),
    Feature(
        "bs_status", "str", "category",
        "OK (cash, total assets and equity all at the newest balance sheet date); PARTIAL (a "
        "core line missing or ending on an older date); NO_FACTS (no fact filed); STALE (the "
        "newest balance sheet date is more than stale_days, 480, before the session; values "
        "still shown, checked first)",
        "never", "label", categories=STATUSES, inputs=("instruments/statements.concept",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _filed(book: Book, end: int) -> int:
    """The newest filing date among the facts that end on ``end``."""
    return max(f for by_end in book.values() for e, (f, _, _) in by_end.items() if e == end)


def _row(book: Book, financial: bool, before: int) -> dict[str, object]:
    if not book:
        return {"bs_status": "NO_FACTS", "is_financial": financial}
    got: dict[str, Pick] = {c: p for c in COLUMN_OF if (p := pick(book, LINES[c])) is not None}
    liabilities, liab_basis, liab_end = total_liabilities(book)
    debt, debt_basis = total_debt(book)
    ends = [p[1] for p in got.values()] + [e for e in (liab_end, debt_end(book)) if e is not None]
    as_of = max(ends)
    core = all(c in got and got[c][1] == as_of for c in CORE)
    status = "STALE" if as_of < before else ("OK" if core else "PARTIAL")
    row: dict[str, object] = {COLUMN_OF[c]: p[0] for c, p in got.items()}
    return {
        **row,
        "total_debt": debt,
        "debt_basis": debt_basis,
        "total_liabilities": liabilities,
        "liabilities_basis": liab_basis,
        "bs_as_of": day_date(as_of),
        "bs_filed": day_date(_filed(book, as_of)),
        "is_financial": financial,
        "bs_status": status,
    }


def compute(inputs: Inputs, session: date, p: StatementParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session]["instrument_id"].astype(str)
    by_instrument = books(inputs.get(STATEMENTS), session, p)
    financial = financial_ids(inputs.get(COMPANY))
    before = stale_before(session, p)
    ids = sorted(set(today) | set(by_instrument))
    rows = [_row(by_instrument.get(i, {}), i in financial, before) for i in ids]
    return pd.DataFrame(rows).assign(instrument_id=ids)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The latest balance sheet lines (cash, short-term investments, debt, assets, liabilities, "
    "equity, current assets and liabilities) from the SEC statements, point in time by filing "
    "date; debt is added up from one filing and null when untagged, never zero",
    (
        Input(PRICE_STATS),
        Input(STATEMENTS, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    StatementParams(),
)
