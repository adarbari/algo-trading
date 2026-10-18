"""Reading balance sheet instants for ``balance_sheet@v1`` (``instruments/statements``, ADR 0067).

An INSTANT fact is a balance at ``period_end`` (``period_start`` null), not a flow: there is no
TTM and no subtraction. ``books`` turns the rows into one ``Book`` per instrument: for each
us-gaap tag and period end the newest filing filed on or before the session (a restatement
replaces the figure from its filing date; a filing after the session is never read, whatever the
loader passed), with its accession number (the filing).

``pick`` takes one line's latest instant: the greatest period end over the line's tags, then the
first tag of the list that reports THAT end (best first, ``statement_concepts.py``), never a mix
of tags. ``total_debt`` adds the parts of ONE filing (rules a to g, ADR 0067) and
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
# The debt parts the rules of ``_basis`` name (finance leases are inside the lease-inclusive
# forms, operating leases are in none).
LTD, LTD_NONCURRENT, LTD_CURRENT = "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent"
DEBT_CURRENT, SHORT, PAPER = "DebtCurrent", "ShortTermBorrowings", "CommercialPaper"
LEASE_NONCURRENT = "LongTermDebtAndCapitalLeaseObligations"
LEASE_CURRENT = "LongTermDebtAndCapitalLeaseObligationsCurrent"
LEASE_TOTAL = "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"
ALL_DEBT = "DebtLongtermAndShorttermCombinedAmount"
DEBT_TAGS = (
    LTD, LTD_NONCURRENT, LTD_CURRENT, DEBT_CURRENT, SHORT, PAPER,
    LEASE_NONCURRENT, LEASE_CURRENT, LEASE_TOTAL, ALL_DEBT,
)  # fmt: skip
# Rule letter, the anchor parts it needs (all of them, from one filing) and whether it adds the
# short-term part: a part is never added to a total that contains it (``DEBT_CURRENT`` and
# ``ALL_DEBT`` include short-term borrowings; ADR 0067 and its amendment of 2026-10-17).
DEBT_RULES: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("a", (LTD,), True),
    ("b", (LTD_NONCURRENT, LTD_CURRENT), True),
    ("c", (DEBT_CURRENT, LTD_NONCURRENT), False),
    ("d", (LEASE_NONCURRENT, LEASE_CURRENT), True),
    ("e", (LEASE_NONCURRENT, DEBT_CURRENT), False),
    ("f", (LEASE_TOTAL,), True),
    ("g", (ALL_DEBT,), False),
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
    out = out.sort_values(
        ["filed", "accn"], kind="stable"
    )  # the later filing overwrites an earlier one
    found: dict[str, Book] = {}
    cols = (out[c].tolist() for c in ("instrument_id", "tag", "end", "filed", "accn", "value"))
    for iid, tag, end, filed, accn, value in zip(*cols, strict=True):
        found.setdefault(iid, {}).setdefault(tag, {})[end] = (filed, accn, value)
    return found


def pick(book: Book, tags: Sequence[str], end: int | None = None) -> Pick | None:
    """The line's latest instant: the greatest period end over ``tags`` (or exactly ``end``),
    reported by the first tag of the list that has it; ``None`` when no tag has one."""
    ends = {e for t in tags for e in book.get(t, {})} if end is None else {end}
    if not ends:
        return None
    at = max(ends)
    return next(((book[t][at][2], at, t) for t in tags if at in book.get(t, {})), None)


def _basis(parts: dict[str, float]) -> tuple[float, str] | None:
    """The first rule of ``DEBT_RULES`` whose anchor parts are all in one filing; ``None`` when
    none applies. The short-term part (borrowings, else commercial paper: never both) is added
    only by a rule that says so, as the other parts exclude it."""
    short = parts.get(SHORT, parts.get(PAPER, 0.0))
    for letter, anchors, adds_short in DEBT_RULES:
        if all(t in parts for t in anchors):
            return sum(parts[t] for t in anchors) + (short if adds_short else 0.0), letter
    return None


def newest_end(book: Book) -> int:
    """The newest period end any fact of the book reports."""
    return max(e for by_end in book.values() for e in by_end)


def total_debt(book: Book, end: int) -> tuple[float | None, str]:
    """``(debt, basis)`` at the balance sheet date ``end`` only: the parts of ONE filing
    (accession number; the newest filing first) by the first rule that applies, ``a`` to ``g``
    (ADR 0067). No filing reporting that date has a complete rule: ``(None, NOT_TAGGED)``,
    never zero: a filer without the tags and a debt-free filer look the same in the document."""
    filings: dict[str, tuple[int, dict[str, float]]] = {}  # accn -> newest filed, tag -> value
    for tag in DEBT_TAGS:
        hit = book.get(tag, {}).get(end)
        if hit is not None:
            filed, accn, value = hit
            newest, parts = filings.setdefault(accn, (filed, {}))
            filings[accn] = (max(newest, filed), {**parts, tag: value})
    for _, parts in sorted(filings.values(), key=lambda f: -f[0]):
        found = _basis(parts)
        if found is not None:
            return found
    return None, NOT_TAGGED


def total_liabilities(book: Book, end: int) -> tuple[float | None, str]:
    """``(value, basis)`` at the balance sheet date ``end`` only: the reported ``Liabilities``,
    else the liabilities-and-equity total less the equity of the same date (``DERIVED``), else
    ``NONE``. The total includes the noncontrolling interest, so the equity subtracted is the
    one including it when the filer tags it, else the parent-only figure."""
    got = pick(book, LINES["liabilities"], end)
    if got is None:
        return None, "NONE"
    value, _, tag = got
    if tag == LINES["liabilities"][0]:
        return value, "REPORTED"
    equity = pick(book, LINES["equity"][::-1], end)  # including noncontrolling interest first
    if equity is None:
        return None, "NONE"
    return value - equity[0], "DERIVED"
