"""The evidence curve of an edge (ADR 0064, ``EdgeCurve``): what the basis's picks earned, window
by window, added up, against what the field earned, with the live stroke on it.

Additive: ``cumulative`` is the running sum of the windows' weighted values (windows that overlap
are weighted ``min(1, spacing / horizon)``, a portfolio of staggered tranches, so the same days
are not counted ``horizon`` times), each plotted at its
``exit`` session (when the outcome was known, never at the decision), the in-sample and
out-of-sample sides by the harness's own flag (the split is the run's). A return outcome adds the
picks' mean excess return and the base line adds the field's; any other outcome (``cushion``,
``ratio``) has no return, so its curve is ``excess_wins`` (wins above what the base rate predicts)
and the zero axis is the base: no base line. A window that holds no number is NOT a point (a flat
stretch would read as a zero return): the line joins its neighbours and ``gaps`` marks each span
with the public reason (``excluded_coverage``, ``lost_input``, ``no_picks``). Only an admin sees
which table a ``lost_input`` gap lost (``CurveGap.unknown.cause``, ADR 0056). A run with no series
is ``NOT_STORED`` (not zero-filled), a missing run or basis ``NOT_RUN``. ``baselines`` are the
decoys' own curves over the same windows (each baseline the edge declares, built from the same
stored series at the basis's holding period), so the page can toggle them against the picks."""

from dataclasses import dataclass
from datetime import date
from typing import Final

from algotrade.quant.edges import paths
from algotrade.services.read.availability.cause import table_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.edge_evidence.live import EdgeLive, load_live
from algotrade.services.read.edge_evidence.series import BasisSeries, load_baseline_series
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.runs import SeriesRow
from algotrade.services.read.values import Unknown, UnknownCode

CUMULATIVE_EXCESS, EXCESS_WINS = "cumulative_excess", "excess_wins"
CURVE_KINDS: Final = (CUMULATIVE_EXCESS, EXCESS_WINS)
EXCLUDED_COVERAGE, LOST_INPUT, NO_PICKS = "excluded_coverage", "lost_input", "no_picks"
GAP_KINDS: Final = (EXCLUDED_COVERAGE, LOST_INPUT, NO_PICKS)


@dataclass(frozen=True)
class CurvePoint:
    """One window: decided at ``decision``, known at ``exit`` (the x), on ``period``'s side of
    the split, with its ``value`` and the ``cumulative`` curve; ``base_value`` and
    ``base_cumulative`` the field's (None: no base line, or not stored); ``trades`` its picks;
    ``weight`` its share in the sums (below 1 where windows overlap): ``value`` is weighted."""

    decision: date
    exit: date
    period: str
    value: float
    cumulative: float
    base_value: float | None
    base_cumulative: float | None
    trades: int
    weight: float


@dataclass(frozen=True)
class CurveGap:
    """A span of windows that hold no number, ``start`` to ``end`` in the curve's x (exit
    sessions), and why in public words (``kind``). ``unknown`` is set for ``lost_input`` only:
    its admin cause names the table the screen lost."""

    start: date
    end: date
    kind: str
    unknown: Unknown | None = None


@dataclass(frozen=True)
class CurveBaseline:
    """One decoy's curve: the ``baseline`` it is (a screener preset the edge declares) and its
    ``points`` by exit, in the picks' unit, with the same additive rule as the basis's."""

    baseline: str
    points: tuple[CurvePoint, ...]


@dataclass(frozen=True)
class EdgeCurve:
    """The curve of the basis in ``unit`` (``kind`` follows it); ``split_from`` where the
    out-of-sample side starts (None: the run has none); ``hidden``: a copy's out-of-sample result
    is withheld (the series holds its in-sample side only); ``points`` by exit; ``gaps``; the
    ``live`` stroke. ``unknown``: why there is no curve (then everything else is empty)."""

    kind: str | None
    unit: str | None
    split_from: date | None
    hidden: bool
    points: tuple[CurvePoint, ...] = ()
    gaps: tuple[CurveGap, ...] = ()
    live: EdgeLive | None = None
    unknown: Unknown | None = None
    baselines: tuple[CurveBaseline, ...] = ()


def curve_points(series: BasisSeries) -> tuple[CurvePoint, ...]:
    """The windows of ``series`` as a running sum of their weighted values, in the order their
    outcomes became known. A window with no base value leaves ``base_cumulative`` None at that
    point (never the previous total); the base line sums the windows that have one."""
    windows = series.windows
    if not windows:
        return ()
    running = paths.cumulative([w.weighted for w in windows])
    base_sum = 0.0
    points: list[CurvePoint] = []
    for w, total in zip(windows, running, strict=True):
        has_base = series.is_return and w.base_value is not None
        if has_base and w.base_value is not None:
            base_sum += w.base_value * w.weight
        points.append(
            CurvePoint(
                decision=w.row.decision_session,
                exit=w.exit,
                period=w.period,
                value=w.weighted,
                cumulative=float(total),
                base_value=w.base_value * w.weight
                if has_base and w.base_value is not None
                else None,
                base_cumulative=base_sum if has_base else None,
                trades=w.row.picks or 0,
                weight=w.weight,
            )
        )
    return tuple(points)


def _gap(row: SeriesRow) -> CurveGap:
    kind = row.status if row.status in GAP_KINDS else NO_PICKS
    lost = (
        Unknown(
            UnknownCode.NO_PARTITION,
            table_cause(row.lost_table, f"the screen lost {row.lost_table} on this window"),
        )
        if kind == LOST_INPUT and row.lost_table
        else None
    )
    at = row.exit_session or row.decision_session  # the curve's x: when the window would be known
    return CurveGap(at, at, kind, lost)


def curve_gaps(series: BasisSeries) -> tuple[CurveGap, ...]:
    """The rows that hold no number as spans in the curve's x (exit sessions): the gaps of one
    kind (and lost table) with no point of the curve between them are joined. A lost input keeps
    each lost table apart: its cause."""
    exits = sorted(w.exit for w in series.windows)
    found: list[CurveGap] = []
    for g in sorted(
        (_gap(r) for r in series.gaps), key=lambda g: (g.kind, _table(g) or "", g.start)
    ):
        last = found[-1] if found else None
        same = last is not None and last.kind == g.kind and _table(last) == _table(g)
        between = last is not None and any(last.end < e < g.start for e in exits)
        if last is not None and same and not between:
            found[-1] = CurveGap(last.start, max(last.end, g.end), last.kind, last.unknown)
        else:
            found.append(g)
    return tuple(sorted(found, key=lambda g: (g.start, g.kind)))


def _table(gap: CurveGap) -> str | None:
    return gap.unknown.cause.leaf.subject if gap.unknown is not None else None


@dataclass(frozen=True)
class Anchor:
    """The curve's cumulative value on a day: the last point known by it, else zero (the sum of
    no windows)."""

    points: tuple[CurvePoint, ...]

    def __call__(self, day: date) -> float:
        known = [p.cumulative for p in self.points if p.exit <= day]
        return known[-1] if known else 0.0


def load_curve(
    ctx: ReadContext, edge: Edge, basis: OfficialBasis, series: BasisSeries | Unknown
) -> EdgeCurve:
    """The evidence curve of ``edge``'s basis from its ``series`` (``load_basis_series``), with
    its live stroke (the session is ``ctx``'s)."""
    if isinstance(series, Unknown):
        return EdgeCurve(None, None, basis.split_from, basis.hidden, unknown=series)
    points = curve_points(series)
    decoys = tuple(
        CurveBaseline(b.key[0], pts)
        for b in load_baseline_series(ctx, basis)
        if (pts := curve_points(b))
    )
    return EdgeCurve(
        kind=CUMULATIVE_EXCESS if series.is_return else EXCESS_WINS,
        unit=series.unit,
        split_from=series.split_from,
        hidden=series.hidden,
        points=points,
        gaps=curve_gaps(series),
        live=load_live(ctx, edge, series, Anchor(points)),
        baselines=decoys,
    )
