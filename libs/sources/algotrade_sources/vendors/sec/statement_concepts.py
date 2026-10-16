"""Which us-gaap tags fill each statement concept of ``instruments/statements`` (ADR 0067).

A concept is what a rollup reads (``cost_of_revenue``, ``cash``, ``debt``); its tags are the
ways filers report it, best first. Every tag found is stored (the ``tag`` column) and the
choice between them is made later, per instrument and date, by the rollup that needs the
concept: the parser never picks one tag over another and never adds or subtracts across tags.
The order is a preference for concepts whose tags are alternatives of one figure
(``cost_of_revenue``, ``cash``, ``equity``); for the concepts whose tags are parts or related
figures it only fixes the output order:

- ``debt``: the parts a rollup adds up from ONE filing (long-term debt, its noncurrent and
  current portions, short-term borrowings, commercial paper); which parts, in which order, is
  the rollup's rule (ADR 0067), and a filer with none of them has no debt tag, which is not
  zero debt.
- ``liabilities``: ``Liabilities``, plus ``LiabilitiesAndStockholdersEquity`` stored so a
  rollup can derive liabilities as that total less equity for filers that do not tag them.
- ``current``: ``AssetsCurrent`` and ``LiabilitiesCurrent``.

A DURATION concept is a flow over a period (a quarter, half year, nine months or a year, cash
flow figures cumulative from the start of the fiscal year); an INSTANT concept is a balance at
a date. Only USD facts are kept: a figure in another currency is not summed with dollars.
"""

INSTANT = "INSTANT"
DURATION = "DURATION"
UNIT_KEY = "USD"  # the unit key in the document
UNIT = "usd"  # ours

STATEMENT_CONCEPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    # concept -> (period type, us-gaap tags best first)
    "cost_of_revenue": (
        DURATION,
        ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    ),
    "gross_profit": (DURATION, ("GrossProfit",)),
    "operating_income": (DURATION, ("OperatingIncomeLoss",)),
    "pretax_income": (
        DURATION,
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
    ),
    "income_tax": (DURATION, ("IncomeTaxExpenseBenefit",)),
    "interest_expense": (
        DURATION,
        ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
    ),
    "da": (
        DURATION,
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
        ),
    ),
    "ocf": (
        DURATION,
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
    ),
    "capex": (
        DURATION,
        ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    ),
    "cash": (
        INSTANT,
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
    ),
    "sti": (INSTANT, ("ShortTermInvestments", "MarketableSecuritiesCurrent")),
    "debt": (
        INSTANT,
        (
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "LongTermDebtCurrent",
            "DebtCurrent",
            "ShortTermBorrowings",
            "CommercialPaper",
        ),
    ),
    "assets": (INSTANT, ("Assets",)),
    "liabilities": (INSTANT, ("Liabilities", "LiabilitiesAndStockholdersEquity")),
    "equity": (
        INSTANT,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
    ),
    "current": (INSTANT, ("AssetsCurrent", "LiabilitiesCurrent")),
}
