"""The same windows seen from other starts and by calendar month (ADR 0064): ``EdgeRollingStarts``
(the lift from the start of each year forward, so a lucky or unlucky start date shows) and
``EdgeMonthly`` (what the curve gained in each calendar month, by the month the outcomes were
known: its heat map).

Both are pooled from the basis's windows (``series.py``), never recomputed from anything else.
The lift is the pooled win rate of the picks minus the pooled base rate, in points, over the
windows decided from the start on (a window missing a count is left out of it). A month is the
sum of the values of the windows that CLOSED in it: the curve's own increments, so the map adds
up to the curve; in ``excess_wins`` for an outcome with no return. A month holding both sides of
the split says ``both``."""

from dataclasses import dataclass
from datetime import date

from algotrade.quant.edges import paths
from algotrade.services.read.edge_evidence.series import BasisSeries, Window
from algotrade.services.read.evaluation.verdict import BOTH
from algotrade.services.read.values import Unknown


@dataclass(frozen=True)
class RollingStart:
    """The windows decided from ``start`` (a January 1st) to the end: how many (``trades``), their
    pooled lift in points and, for a return outcome, their mean ``mean_excess`` (None: not
    measurable)."""

    start: date
    trades: int
    lift_pts: float | None
    mean_excess: float | None


@dataclass(frozen=True)
class EdgeRollingStarts:
    """The ``starts``, one per calendar year with a window, earliest first; ``unknown``: why
    there are none."""

    unit: str | None
    starts: tuple[RollingStart, ...] = ()
    unknown: Unknown | None = None


@dataclass(frozen=True)
class MonthRow:
    """One calendar ``month`` (its first day): the sum of the ``value`` of the ``trades``
    (windows) that closed in it, on ``period``'s side of the split (``both`` when it holds both)."""

    month: date
    value: float
    trades: int
    period: str


@dataclass(frozen=True)
class EdgeMonthly:
    """The ``months`` the curve gained or lost, earliest first, in ``unit``."""

    unit: str | None
    months: tuple[MonthRow, ...] = ()
    unknown: Unknown | None = None


def _counts(w: Window) -> tuple[float, float, float, float] | None:
    """The window's ``(pick_hits, picks, base_hits, eligible)``; None when one is not stored."""
    r = w.row
    if r.pick_hits is None or r.picks is None or r.base_hits is None or r.eligible is None:
        return None
    return float(r.pick_hits), float(r.picks), float(r.base_hits), float(r.eligible)


def load_rolling_starts(series: BasisSeries | Unknown) -> EdgeRollingStarts:
    """The lift from each year's start forward over the basis ``series``."""
    if isinstance(series, Unknown):
        return EdgeRollingStarts(None, unknown=series)
    counted = [(w, c) for w in series.windows if (c := _counts(w)) is not None]
    if not series.windows:
        return EdgeRollingStarts(series.unit)
    years = [w.row.decision_session.year for w in series.windows]
    starts: list[RollingStart] = []
    for year in range(min(years), max(years) + 1):
        start = date(year, 1, 1)
        kept = [(w, c) for w, c in counted if w.row.decision_session >= start]
        if not kept:
            continue
        hits, picks, base_hits, eligible = (
            [x * w.weight for x, (w, _) in zip(col, kept, strict=True)]
            for col in zip(*(c for _, c in kept), strict=True)
        )
        mean = sum(w.value for w, _ in kept) / len(kept) if series.is_return else None
        lift = paths.pooled_lift(hits, picks, base_hits, eligible)
        starts.append(RollingStart(start, len(kept), lift, mean))
    return EdgeRollingStarts(series.unit, tuple(starts))


def load_monthly(series: BasisSeries | Unknown) -> EdgeMonthly:
    """What the curve gained in each calendar month of the basis ``series``."""
    if isinstance(series, Unknown):
        return EdgeMonthly(None, unknown=series)
    windows = series.windows
    if not windows:
        return EdgeMonthly(series.unit)
    keys = [w.exit.year * 12 + w.exit.month - 1 for w in windows]
    found, sums, counts = paths.sum_by_key(keys, [w.weighted for w in windows])
    sides = {k: {w.period for w, key in zip(windows, keys, strict=True) if key == k} for k in found}
    months = tuple(
        MonthRow(
            date(k // 12, k % 12 + 1, 1),
            float(total),
            n,
            next(iter(sides[k])) if len(sides[k]) == 1 else BOTH,
        )
        for k, total, n in zip(found, sums, counts, strict=True)
    )
    return EdgeMonthly(series.unit, months)
