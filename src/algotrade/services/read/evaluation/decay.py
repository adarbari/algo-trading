"""How far an edge's number has fallen from the paper's (``EdgeDecay``, ADR 0064 decision 6):
the published figure, the harness's in-sample figure and its out-of-sample figure of the SAME
statistic, each with the count it rests on. Pure over the verdict's basis rows: the statistic
is the document's ``[published]`` ``measure``, read from the stored row, never recomputed.

A bar is ``measured`` or has a state saying why not: ``not_stored`` (an older run, or the
statistic was undefined there), ``not_comparable`` (the verdict's holding period is not the
one the paper reports) or ``oos_hidden`` (a copy's out-of-sample result is withheld).
A document that publishes no figure still has its decay: the published bar is ``not_given``
and the other two read the lift in points. The live bar comes with the stored paper trades
(a later change)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import EdgePublished
from algotrade.services.read.evaluation.runs import EdgeRow

PUBLISHED, IN_SAMPLE, OUT_OF_SAMPLE = "published", "in_sample", "out_of_sample"
MEASURED, NOT_STORED, NOT_COMPARABLE, OOS_HIDDEN, NOT_GIVEN = (
    "measured",
    "not_stored",
    "not_comparable",
    "oos_hidden",
    "not_given",
)
BAR_STATES: Final = (MEASURED, NOT_STORED, NOT_COMPARABLE, OOS_HIDDEN, NOT_GIVEN)
DEFAULT_MEASURE: Final = "lift_pts"  # what the bars show when the document publishes nothing
POINTS, RETURN = "points", "return"  # the unit of a bar's value


@dataclass(frozen=True)
class DecayBar:
    """One bar: ``period`` (``published``, ``in_sample``, ``out_of_sample``), its ``value`` (None
    unless ``measured``) over ``n`` (the trades, or the decile sessions for a decile spread; None
    for the paper's), and the ``state`` that says why a value is missing."""

    period: str
    value: float | None
    n: int | None
    state: str


@dataclass(frozen=True)
class EdgeDecay:
    """The decay of one statistic: ``measure`` (``mean_excess``, ``decile_spread`` or
    ``lift_pts``) in ``unit`` (a return as a fraction, or points), the paper's figure
    (``published``, with its source, sample and holding period; None: the document gives none)
    and the harness's ``bars`` at the verdict's ``basis_horizon``."""

    measure: str
    unit: str
    published: EdgePublished | None
    basis_horizon: int
    bars: tuple[DecayBar, ...]


def _read(measure: str, row: EdgeRow) -> tuple[float | None, int | None]:
    """The stored ``(value, n)`` of ``measure`` on ``row``."""
    reader: dict[str, Callable[[EdgeRow], tuple[float | None, int | None]]] = {
        "mean_excess": lambda r: (r.mean_excess_picks, r.sessions),
        "decile_spread": lambda r: (r.decile_spread, r.decile_sessions),
        "lift_pts": lambda r: (runs.lift_points(r.hit_rate, r.base_rate), r.sessions),
    }
    return reader[measure](row)


def _bar(
    period: str,
    row: EdgeRow | None,
    measure: str,
    published: EdgePublished | None,
    horizon: int,
    hidden: bool,
) -> DecayBar:
    if hidden and period == OUT_OF_SAMPLE:
        return DecayBar(period, None, None, OOS_HIDDEN)
    if published is not None and horizon != published.horizon_sessions:
        return DecayBar(period, None, None, NOT_COMPARABLE)
    value, n = (None, None) if row is None else _read(measure, row)
    if value is None:
        return DecayBar(period, None, n, NOT_STORED)
    return DecayBar(period, value, n, MEASURED)


def decay_of(
    published: EdgePublished | None,
    horizon: int,
    insample: EdgeRow | None,
    oos: EdgeRow | None,
    hidden: bool = False,
) -> EdgeDecay:
    """The decay against the basis rows at ``horizon``: of the edge's ``published`` figure, or
    with none (``not_given``) of the lift in points."""
    measure = DEFAULT_MEASURE if published is None else published.measure
    first = (
        DecayBar(PUBLISHED, None, None, NOT_GIVEN)
        if published is None
        else DecayBar(PUBLISHED, published.value, None, MEASURED)
    )
    return EdgeDecay(
        measure=measure,
        unit=POINTS if measure == "lift_pts" else RETURN,
        published=published,
        basis_horizon=horizon,
        bars=(
            first,
            _bar(IN_SAMPLE, insample, measure, published, horizon, hidden),
            _bar(OUT_OF_SAMPLE, oos, measure, published, horizon, hidden),
        ),
    )
