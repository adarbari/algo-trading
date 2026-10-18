"""Trailing-twelve-month arithmetic over one concept's reported periods, shared by the
statement rollups (``financials@v2``, ``income_statement@v1``, ``cash_flow@v1``).

A fact is ``(start, end, value, filed, tag rank)`` with dates as epoch days. A discrete quarter
is a reported three-month fact, else the difference of two year-to-date facts of one fiscal
year and one tag filed within ``DERIVE_GAP`` days of each other (a quarter is never derived
across tags); a TTM is the last four consecutive discrete quarters, else the latest fiscal year.
Pure functions: no I/O, no pandas.
"""

from dataclasses import dataclass
from itertools import pairwise

# Months of a reported period by its length in days (52 / 53-week fiscal years included).
SPANS = ((3, 75, 105), (6, 160, 200), (9, 250, 290), (12, 340, 380))
QUARTER_GAP = (75, 105)  # days between the ends of consecutive quarters
YEAR_GAP = (340, 380)  # days between a period end and the same period a year earlier
DERIVE_GAP = 150  # days apart two year-to-date facts may be filed to be subtracted
AGO_TOLERANCE = 40  # days a TTM end may be off its target of N years before the newest TTM


@dataclass(frozen=True)
class TtmParams:
    """How far back statement facts are read and when a trailing figure is stale; shared by
    ``financials@v2`` and the statement groups so the two never drift apart."""

    stale_days: int = 480  # a TTM whose period ended longer ago is STALE (still shown)
    history_days: int = 1100  # facts whose period ended earlier than this are not read

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError(f"stale_days must be >= 1, got {self.stale_days}")
        if self.history_days < 800:
            raise ValueError(
                f"history_days must be >= 800 (eight quarters), got {self.history_days}"
            )


type Fact = tuple[int, int, float, int, int]  # start, end (epoch days), value, filed, tag rank
type Total = tuple[float, int, int, bool]  # value, newest period end, newest filed, annual
type Quarters = list[tuple[int, float, int]]  # end, value, filed; ascending by end


def months(start: int, end: int) -> int:
    """3 / 6 / 9 / 12 for a quarter, half year, nine months or year; 0 for any other span."""
    return next((m for m, lo, hi in SPANS if lo <= end - start <= hi), 0)


def discrete_quarters(facts: list[Fact], non_negative: bool = False) -> Quarters:
    """The discrete quarters the periods give: reported three-month facts (best tag first),
    else the difference of two year-to-date periods of one fiscal year and one tag filed within
    ``DERIVE_GAP`` days of each other. ``non_negative``: a derived quarter below zero is
    dropped (revenue)."""
    by_tag: dict[int, dict[tuple[int, int], tuple[int, float, int]]] = {}
    for start, end, value, filed, rank in facts:
        if m := months(start, end):
            by_tag.setdefault(rank, {})[(start, m)] = (end, value, filed)
    best: dict[
        int, tuple[tuple[bool, int], float, int]
    ] = {}  # end -> (derived, rank), value, filed
    for rank, ytd in by_tag.items():
        for (start, m), (end, value, filed) in ytd.items():
            if m == 3:
                found = ((False, rank), value, filed)
            else:
                before = ytd.get((start, m - 3))
                if before is None or abs(filed - before[2]) > DERIVE_GAP:
                    continue
                gap = value - before[1]
                if non_negative and gap < 0:
                    continue
                found = ((True, rank), gap, max(filed, before[2]))
            if end not in best or found[0] < best[end][0]:
                best[end] = found
    return [(end, v, f) for end, (_, v, f) in sorted(best.items())]


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
    """The annual facts, one per period end (the best tag), oldest first."""
    best: dict[int, Fact] = {}
    for fact in facts:
        if months(fact[0], fact[1]) == 12 and (fact[1] not in best or fact[4] < best[fact[1]][4]):
            best[fact[1]] = fact
    return [best[end] for end in sorted(best)]


def trailing(facts: list[Fact], non_negative: bool = False) -> tuple[Total, float | None] | None:
    """``(TTM, year-ago TTM)`` of one concept's periods, or ``None`` when no TTM can be formed.
    ``TTM`` is ``(value, newest period end, newest filing date, annual?)``. The year-ago TTM is
    null unless it ends 340 to 380 days before the TTM."""
    quarters = discrete_quarters(facts, non_negative)
    years = annual(facts)
    last = _four(quarters, len(quarters) - 1)
    if last is not None and (not years or quarters[-1][0] >= years[-1][1]):
        end = quarters[-1][0]
        before = [i for i, q in enumerate(quarters) if YEAR_GAP[0] <= end - q[0] <= YEAR_GAP[1]]
        ago = _four(quarters, before[-1]) if before else None
        return (last[0], end, last[1], False), None if ago is None else ago[0]
    if not years:
        return None
    _, end, value, filed, _ = years[-1]
    before_year = [x[2] for x in years if YEAR_GAP[0] <= end - x[1] <= YEAR_GAP[1]]
    return (value, end, filed, True), before_year[-1] if before_year else None


def trailing_ago(
    facts: list[Fact], end: int, years: int, non_negative: bool = False
) -> float | None:
    """The TTM ending about ``years`` years before ``end`` (the newest TTM's period end), or
    ``None``: the four consecutive quarters whose last ends within ``AGO_TOLERANCE`` days of
    ``end`` minus ``years`` x 365.25 days (the nearest first), else the fiscal year ending that
    close to it. A hole in that history (a missing quarter and no such fiscal year) is ``None``,
    never a shorter sum."""
    target = end - round(365.25 * years)
    quarters = discrete_quarters(facts, non_negative)
    near = sorted(
        (i for i, q in enumerate(quarters) if abs(q[0] - target) <= AGO_TOLERANCE),
        key=lambda i: abs(quarters[i][0] - target),
    )
    for i in near:
        if (four := _four(quarters, i)) is not None:
            return four[0]
    close = [f for f in annual(facts) if abs(f[1] - target) <= AGO_TOLERANCE]
    return min(close, key=lambda f: abs(f[1] - target))[2] if close else None


def latest_quarter(
    facts: list[Fact], non_negative: bool = False
) -> tuple[tuple[int, float, int], float | None] | None:
    """``(newest discrete quarter, the value of the quarter a year earlier)`` of one concept's
    periods. The quarter is ``(period end, value, filing date)``; the year-ago one is the
    discrete quarter ending 340 to 380 days before it (the latest such), or ``None``. The result
    is ``None`` when there is no quarter, or the annual figure is newer than the newest quarter
    (a fourth quarter that cannot be derived: an older quarter would not be the latest)."""
    quarters = discrete_quarters(facts, non_negative)
    if not quarters:
        return None
    years = annual(facts)
    last = quarters[-1]
    if (years and years[-1][1] > last[0]) or (non_negative and last[1] < 0):
        return None
    ago = [q[1] for q in quarters if YEAR_GAP[0] <= last[0] - q[0] <= YEAR_GAP[1]]
    return last, ago[-1] if ago and not (non_negative and ago[-1] < 0) else None
