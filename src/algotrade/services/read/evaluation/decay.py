"""How far an edge's number has fallen from the paper's (``EdgeDecay``, ADR 0064 decision 6):
the published figure, the harness's in-sample figure and its out-of-sample figure of the SAME
statistic, each with the count it rests on. Pure over the verdict's basis rows: the statistic
is the document's ``[published]`` ``measure``, read from the stored row, never recomputed.

A bar is ``measured`` or has a state saying why not: ``not_stored`` (an older run, or the
statistic was undefined there; for the live bar, no settled paper trade yet), ``not_comparable``
(the verdict's holding period is not the one the paper reports), ``oos_hidden`` (a copy's
out-of-sample result is withheld) or ``not_measured_live`` (a decile spread needs the whole
ranked field, which the paper record does not keep).
A document that publishes no figure still has its decay: the published bar is ``not_given``
and the other bars read the lift in points. The live bar is the fourth: it is added by
``services/read/edge_evidence/decay.py`` from the stored paper trades (``live`` period)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import EdgePublished
from algotrade.services.read.evaluation.runs import EdgeRow

PUBLISHED, IN_SAMPLE, OUT_OF_SAMPLE, LIVE = "published", "in_sample", "out_of_sample", "live"
MEASURED, NOT_STORED, NOT_COMPARABLE, OOS_HIDDEN, NOT_GIVEN, NOT_MEASURED_LIVE = (
    "measured",
    "not_stored",
    "not_comparable",
    "oos_hidden",
    "not_given",
    "not_measured_live",
)
BAR_STATES: Final = (
    MEASURED,
    NOT_STORED,
    NOT_COMPARABLE,
    OOS_HIDDEN,
    NOT_GIVEN,
    NOT_MEASURED_LIVE,
)
DEFAULT_MEASURE: Final = "lift_pts"  # what the bars show when the document publishes nothing
POINTS, RETURN = "points", "return"  # the unit of a bar's value


@dataclass(frozen=True)
class DecayBar:
    """One bar: ``period`` (``published``, ``in_sample``, ``out_of_sample``, ``live``), its
    ``value`` (None unless ``measured``) over ``n`` (the trades, or the decile sessions for a
    decile spread; the signal sessions for the live bar; None for the paper's), and the ``state``
    that says why a value is missing."""

    period: str
    value: float | None
    n: int | None
    state: str


@dataclass(frozen=True)
class ExpectedFigure:
    """What to expect of the paper's figure once it is traded (``[published] leg`` and
    ``verdict.toml [published_haircut]``, ADR 0065 amendment 2026-10-17): ``value`` is the
    published figure less the ``haircut`` of its ``leg``, in the decay's unit. ``realised`` is the
    out-of-sample bar's figure and ``share`` its share of ``value`` (None where the bar has no
    value, or ``value`` is zero). Display only: no verdict criterion reads it."""

    leg: str
    haircut: float
    value: float
    realised: float | None
    share: float | None
    summary: str


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
    expected: ExpectedFigure | None = None  # the published figure after its leg's haircut


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


def _shown(value: float, measure: str) -> str:
    return f"{value:g} points" if measure == "lift_pts" else f"{value * 100:.2f}%"


def expected_of(
    published: EdgePublished, measure: str, oos: DecayBar, settings: VerdictSettings
) -> ExpectedFigure:
    """The published figure after its leg's haircut, with the out-of-sample bar against it."""
    cut = settings.published_haircut(published.leg)
    value = published.value * (1.0 - cut)
    realised = oos.value if oos.state == MEASURED else None
    share = None if realised is None or value == 0.0 else realised / value
    leg = published.leg.replace("_", "-")
    text = (
        f"Published {_shown(published.value, measure)}, expect {_shown(value, measure)} "
        f"({cut * 100:.0f}% off for a {leg} figure)."
    )
    if realised is not None and share is not None:
        text += f" Out of sample it is {_shown(realised, measure)}, {share * 100:.0f}% of that."
    return ExpectedFigure(published.leg, cut, value, realised, share, text)


def decay_of(
    published: EdgePublished | None,
    horizon: int,
    insample: EdgeRow | None,
    oos: EdgeRow | None,
    hidden: bool = False,
    settings: VerdictSettings | None = None,
) -> EdgeDecay:
    """The decay against the basis rows at ``horizon``: of the edge's ``published`` figure, or
    with none (``not_given``) of the lift in points. With ``settings`` and a published figure,
    ``expected`` is the figure after the haircut of its leg, set beside the out-of-sample bar."""
    measure = DEFAULT_MEASURE if published is None else published.measure
    first = (
        DecayBar(PUBLISHED, None, None, NOT_GIVEN)
        if published is None
        else DecayBar(PUBLISHED, published.value, None, MEASURED)
    )
    bars = (
        first,
        _bar(IN_SAMPLE, insample, measure, published, horizon, hidden),
        _bar(OUT_OF_SAMPLE, oos, measure, published, horizon, hidden),
    )
    return EdgeDecay(
        measure=measure,
        unit=POINTS if measure == "lift_pts" else RETURN,
        published=published,
        basis_horizon=horizon,
        bars=bars,
        expected=None
        if published is None or settings is None
        else expected_of(published, measure, bars[2], settings),
    )
