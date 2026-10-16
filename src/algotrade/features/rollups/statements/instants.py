"""Reading balance sheet instants for ``balance_sheet@v1`` (``instruments/statements``, ADR 0067).

An INSTANT fact is a balance at ``period_end`` (``period_start`` null), not a flow: there is no
TTM and no subtraction. ``books`` turns the rows into one ``Book`` per instrument: for each
us-gaap tag and period end the newest filing filed on or before the session (a restatement
replaces the figure from its filing date; a filing after the session is never read, whatever the
loader passed), with its accession number (the filing).

``pick`` takes one line's latest instant: the greatest period end over the line's tags, then the
first tag of the list that reports THAT end (best first, ``statement_concepts.py``), never a mix
of tags. ``total_debt`` adds the parts of ONE filing (rules a, b, c, ADR 0067) and
``total_liabilities`` is the reported ``Liabilities`` or the liabilities-and-equity total less
equity. Pure functions over frames and dicts: no storage.
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from algotrade.features.rollups.statements.lines import EPOCH, PREFIX, StatementParams, epoch_days

# Each line's us-gaap tags, best first: a subset of its concept's list in ``statement_concepts.py``
# (a test compares them; a rollup imports no vendor package). ``current`` holds two lines.
LINES: dict[str, tuple[str, ...]] = {
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "sti": ("ShortTermInvestments", "MarketableSecuritiesCurrent"),
    "assets": ("Assets",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "liabilities": ("Liabilities", "LiabilitiesAndStockholdersEquity"),
}
LINE_CONCEPT = {
    "cash": "cash",
    "sti": "sti",
    "assets": "assets",
    "equity": "equity",
    "current_assets": "current",
    "current_liabilities": "current",
    "liabilities": "liabilities",
}
DEBT_TAGS = (
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "LongTermDebtCurrent",
    "DebtCurrent",
    "ShortTermBorrowings",
    "CommercialPaper",
)
ALL_TAGS = frozenset(t for tags in (*LINES.values(), DEBT_TAGS) for t in tags)
NOT_TAGGED = "NOT_TAGGED"

type Book = dict[str, dict[int, tuple[int, str, float]]]  # tag -> end -> (filed, accn, value)
type Pick = tuple[float, int, str]  # value, period end (epoch days), tag


def books(facts: pd.DataFrame | None, session: date, p: StatementParams) -> dict[str, Book]:
    """The balance sheet facts of every instrument, filed on or before ``session`` and ended
    within ``history_days``: the newest filing of each (tag, period end)."""
    if facts is None or facts.empty or "value" not in facts.columns:
        return {}
    rows = facts[facts["tag"].isin({f"{PREFIX}{t}" for t in ALL_TAGS}) & facts["value"].notna()]
    rows = rows[rows["period_start"].isna() & rows[["period_end", "filed"]].notna().all(axis=1)]
    today = (session - EPOCH).days
    out = pd.DataFrame(
        {
            "instrument_id": rows["instrument_id"].astype(str),
            "tag": rows["tag"].astype(str).str.removeprefix(PREFIX),
            "end": epoch_days(rows["period_end"]),
            "filed": epoch_days(rows["filed"]),
            "accn": rows["accn"].astype(str),
            "value": rows["value"].astype(float),
        }
    )
    out = out[(out["filed"] <= today) & (out["end"] >= today - p.history_days)]
    out = out.sort_values("filed", kind="stable")  # a later filing overwrites an earlier one
    found: dict[str, Book] = {}
    cols = (out[c].tolist() for c in ("instrument_id", "tag", "end", "filed", "accn", "value"))
    for iid, tag, end, filed, accn, value in zip(*cols, strict=True):
        found.setdefault(iid, {}).setdefault(tag, {})[end] = (filed, accn, value)
    return found


def pick(book: Book, tags: Sequence[str], end: int | None = None) -> Pick | None:
    """The line's latest instant: the greatest period end over ``tags`` (or exactly ``end``),
    reported by the first tag of the list that has it; ``None`` when no tag has one."""
    ends = {e for t in tags for e in book.get(t, {})} if end is None else {end}
    if end is None and not ends:
        return None
    at = max(ends)
    return next(((book[t][at][2], at, t) for t in tags if at in book.get(t, {})), None)


def _basis(parts: dict[str, float]) -> tuple[float, str] | None:
    """Rule a, b or c over the parts of one filing; ``None`` when none applies."""
    short = parts.get("ShortTermBorrowings", parts.get("CommercialPaper", 0.0))  # never both
    if "LongTermDebt" in parts:
        return parts["LongTermDebt"] + short, "a"
    if "LongTermDebtNoncurrent" in parts and "LongTermDebtCurrent" in parts:
        return parts["LongTermDebtNoncurrent"] + parts["LongTermDebtCurrent"] + short, "b"
    if "DebtCurrent" in parts and "LongTermDebtNoncurrent" in parts:
        return parts["DebtCurrent"] + parts["LongTermDebtNoncurrent"], "c"
    return None


def debt_end(book: Book) -> int | None:
    """The newest period end any debt tag reports."""
    ends = {e for t in DEBT_TAGS for e in book.get(t, {})}
    return max(ends) if ends else None


def total_debt(book: Book) -> tuple[float | None, str]:
    """``(debt, basis)`` at the newest debt period end: the parts of ONE filing (accession
    number; the newest filing first) by the first rule that applies, ``a`` / ``b`` / ``c``
    (ADR 0067). No filing at that date has a complete rule: ``(None, NOT_TAGGED)``, never
    zero: a filer without the tags and a debt-free filer look the same in the document."""
    end = debt_end(book)
    filings: dict[str, tuple[int, dict[str, float]]] = {}  # accn -> newest filed, tag -> value
    for tag in DEBT_TAGS:
        hit = book.get(tag, {}).get(end) if end is not None else None
        if hit is not None:
            filed, accn, value = hit
            newest, parts = filings.setdefault(accn, (filed, {}))
            filings[accn] = (max(newest, filed), {**parts, tag: value})
    for _, parts in sorted(filings.values(), key=lambda f: -f[0]):
        found = _basis(parts)
        if found is not None:
            return found
    return None, NOT_TAGGED


def total_liabilities(book: Book) -> tuple[float | None, str, int | None]:
    """``(value, basis, period end)``: the reported ``Liabilities`` of the newest period, else
    that period's liabilities-and-equity total less its equity (``DERIVED``), else ``NONE``.
    The total and the equity must end on the same day: never mixed across dates."""
    got = pick(book, LINES["liabilities"])
    if got is None:
        return None, "NONE", None
    value, end, tag = got
    if tag == LINES["liabilities"][0]:
        return value, "REPORTED", end
    equity = pick(book, LINES["equity"], end)
    if equity is None:
        return None, "NONE", end  # the total still dates a balance sheet
    return value - equity[0], "DERIVED", end
