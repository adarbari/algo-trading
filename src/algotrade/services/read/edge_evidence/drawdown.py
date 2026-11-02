"""How far an edge's curve fell and how much it moves (ADR 0064, ``EdgeDrawdown``): the underwater
series of the evidence curve (its distance below its running high), its three deepest episodes
with dates, the deepest drop on each side of the split and the annualised volatility of the
windows, in-sample and out-of-sample apart.

The curve adds each window at its weight (windows that overlap are weighted so the same days are
not counted again, see ``evidence_curve``). A drop is measured on the per-window curve, so it
understates a dip INSIDE a window (the Guide says so). The out-of-sample side is its own curve
from its first window (zero), so an out-of-sample drop is never a fall from an in-sample high.
Volatility is the standard deviation of
the windows' values times the root of the independent windows a year: the windows the run
observed a year, never more than the sessions a year allow a window of the holding period (the
windows of an every-session schedule overlap, and counting each as independent would overstate
it). Only a return outcome has a drawdown or a volatility: for ``cushion`` and ``ratio`` its
``state`` is ``not_a_return`` (there is no return to fall: a state with a Guide term, not a data
gap, so no cause chain); with no series at all it is ``not_stored`` and ``unknown`` says why.

An option setup's episodes (its series on collateral, unit ``return_on_capital``; E11) carry
three more facts (``with_option_extras``): the market episodes (``regime/episodes.toml``, the
twelve bear markets and the vol shocks of 2015, 2018 and 2024) whose peak-to-trough overlaps
the drop and that the session already knows (``known_from``); the move of the Cboe strategy index
the setup ``tracks`` over the same dates, its level at each as the series knew it on the session,
under the index's licence (``LICENCE`` to a viewer without it); and whether the Reg-T margin of
the positions exceeded their collateral, UNKNOWN while ``regt_margin`` is not stored."""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Final

from algotrade.config.edges.portfolio import TRACKED_LICENCE
from algotrade.config.site.regime.episodes import Episode, load_episodes
from algotrade.core.model.instruments import index_id
from algotrade.core.time.calendar import sessions_between
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.data.macro.series import series_as_of
from algotrade.quant.edges import paths
from algotrade.quant.realized_vol import TRADING_DAYS
from algotrade.services.read.availability.cause import table_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_evidence.series import ROC, BasisSeries, Window
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.verdict import IN_SAMPLE, OUT_OF_SAMPLE
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.tables.schemas import STRUCTURE_PNL  # where ``regt_margin`` is stored

MEASURED, NOT_STORED, NOT_A_RETURN = "measured", "not_stored", "not_a_return"
DRAWDOWN_STATES: Final = (MEASURED, NOT_STORED, NOT_A_RETURN)
EPISODES = 3
DAYS_PER_YEAR = 365.25
LEVEL_REACH = timedelta(days=7)  # an index level is read on the date, else the last before it


@dataclass(frozen=True)
class UnderwaterPoint:
    """The curve's distance below its running high at ``exit``: ``depth`` is 0 or negative."""

    exit: date
    depth: float


@dataclass(frozen=True)
class DrawdownEpisode:
    """One drop: from the high at ``peak`` (the curve's first decision for a drop from its
    start) down ``depth`` (positive) to ``trough`` and back to ``recovered`` (None: not yet)."""

    peak: date
    trough: date
    recovered: date | None
    depth: float
    # An option setup's only (E11; empty / None for every other): the market episodes the drop
    # overlaps, the tracked index's move over it (or why not), the Reg-T flag (or why not)
    market: tuple[str, ...] = ()
    index: str | None = None
    index_change: float | None = None
    index_unknown: Unknown | None = None
    regt_exceeded: bool | None = None
    regt_unknown: Unknown | None = None


@dataclass(frozen=True)
class EdgeDrawdown:
    """The underwater ``points`` and the deepest ``episodes`` of the whole curve; ``max_in_sample``
    and ``max_out_of_sample`` the deepest drop of each side (positive; None: that side has no
    window, or the run has no split); ``vol_in_sample`` and ``vol_out_of_sample`` the annualised
    volatility of the windows (None: fewer than two windows). ``state``: measured,
    not_a_return (the outcome has no return) or not_stored (no series: ``unknown`` says why)."""

    unit: str | None
    points: tuple[UnderwaterPoint, ...] = ()
    episodes: tuple[DrawdownEpisode, ...] = ()
    max_in_sample: float | None = None
    max_out_of_sample: float | None = None
    vol_in_sample: float | None = None
    vol_out_of_sample: float | None = None
    unknown: Unknown | None = None
    state: str = MEASURED


def _vol(windows: list[Window], horizon: int) -> float | None:
    """Annualised volatility of ``windows`` (one side), by the independent windows a year."""
    if len(windows) < 2:
        return None
    days = (windows[-1].row.decision_session - windows[0].row.decision_session).days
    years = days / DAYS_PER_YEAR
    if years <= 0.0:
        return None
    observed = (len(windows) - 1) / years  # intervals, not windows, span the years
    independent = min(observed, TRADING_DAYS / max(horizon, 1))
    return paths.annualised_vol([w.value for w in windows], len(windows) / independent)


def _max_depth(windows: list[Window]) -> float | None:
    """The deepest drop of the curve of ``windows`` alone, from zero at its first window."""
    if not windows:
        return None
    return float(-paths.underwater(paths.cumulative([w.weighted for w in windows])).min())


def load_drawdown(series: BasisSeries | Unknown) -> EdgeDrawdown:
    """The drawdown and volatility of the basis ``series``."""
    if isinstance(series, Unknown):
        return EdgeDrawdown(None, unknown=series, state=NOT_STORED)
    if not series.is_return:
        return EdgeDrawdown(series.unit, state=NOT_A_RETURN)
    windows = list(series.windows)
    if not windows:
        return EdgeDrawdown(series.unit)
    curve = paths.cumulative([w.weighted for w in windows])
    depth = paths.underwater(curve)
    start = windows[0].row.decision_session

    def day(i: int) -> date:
        return start if i == paths.START else windows[i].exit

    episodes = tuple(
        DrawdownEpisode(
            day(e.peak),
            windows[e.trough].exit,
            None if e.recovered is None else windows[e.recovered].exit,
            e.depth,
        )
        for e in paths.top_episodes(curve, EPISODES)
    )
    sides = {side: [w for w in windows if w.period == side] for side in (IN_SAMPLE, OUT_OF_SAMPLE)}
    deepest_before = [
        -float(d) for d, w in zip(depth, windows, strict=True) if w.period == IN_SAMPLE
    ]
    return EdgeDrawdown(
        unit=series.unit,
        points=tuple(
            UnderwaterPoint(w.exit, float(d)) for w, d in zip(windows, depth, strict=True)
        ),
        episodes=episodes,
        max_in_sample=max(deepest_before) if deepest_before else None,
        max_out_of_sample=_max_depth(sides[OUT_OF_SAMPLE]),
        vol_in_sample=_vol(sides[IN_SAMPLE], series.horizon),
        vol_out_of_sample=_vol(sides[OUT_OF_SAMPLE], series.horizon),
    )


def _overlapping(
    episodes: tuple[Episode, ...], e: DrawdownEpisode, session: date
) -> tuple[str, ...]:
    """The keys of the market episodes known by ``session`` whose peak-to-trough overlaps the
    drop's, in the file's order."""
    return tuple(
        m.key
        for m in episodes
        if m.known_from <= session and m.peak <= e.trough and e.peak <= m.trough
    )


def _level(levels: dict[date, float], day: date) -> float | None:
    """The level on ``day``, else the last one within ``LEVEL_REACH`` before it."""
    found = [d for d in levels if day - LEVEL_REACH <= d <= day]
    return levels[max(found)] if found else None


def _index_move(
    levels: dict[date, float], key: str, e: DrawdownEpisode, session: date
) -> tuple[float | None, Unknown | None]:
    start, end = _level(levels, e.peak), _level(levels, e.trough)
    if start is None or end is None or not start > 0:
        why = f"{index_id(key)} has no level near {e.peak.isoformat()} or {e.trough.isoformat()}"
        return None, Unknown(UnknownCode.NO_ROW, table_cause(MACRO_SERIES, why, "NO_ROW", session))
    return end / start - 1.0, None


def with_option_extras(ctx: ReadContext, edge: Edge, found: EdgeDrawdown) -> EdgeDrawdown:
    """``found`` with an option setup's episode facts (the module); any other unchanged."""
    if found.unit != ROC or not found.episodes:
        return found
    session = ctx.session.date
    market = load_episodes(ctx.configs).episodes
    key = edge.settings.tracks if edge.settings is not None else None
    held = TRACKED_LICENCE in ctx.licences
    levels: dict[date, float] = {}
    if key is not None and held:
        first = min(e.peak for e in found.episodes) - LEVEL_REACH
        frame = series_as_of(
            ctx.reader, [index_id(key)], session, len(sessions_between(first, session))
        )
        levels = {d: float(v) for d, v in zip(frame["obs_date"], frame["value"], strict=True)}
    regt = Unknown(
        UnknownCode.NOT_STORED,
        table_cause(STRUCTURE_PNL, "regt_margin is not stored yet", "NOT_STORED", session),
    )
    out = []
    for e in found.episodes:
        change, why = None, None
        if key is not None and not held:
            why = Unknown(
                UnknownCode.LICENCE,
                table_cause(MACRO_SERIES, f"{index_id(key)} is {TRACKED_LICENCE}", "LICENCE"),
            )
        elif key is not None:
            change, why = _index_move(levels, key, e, session)
        out.append(
            replace(
                e, market=_overlapping(market, e, session), index=key, index_change=change,
                index_unknown=why, regt_unknown=regt,
            )
        )  # fmt: skip
    return replace(found, episodes=tuple(out))
