"""The decay of an edge's number with the live bar (ADR 0064 decisions 6 and 9): the verdict's own
decay (the paper's figure, the in-sample and the out-of-sample bar of the basis,
``evaluation/decay.py``) and a fourth bar, the SAME statistic over the edge's settled paper
trades on the basis, as the resolved session knew them (``live.settled_trades``).

The live bar reads each statistic over the signal sessions (the picks of one session share a
market and a window, so a session is the unit, as in the backtest): ``mean_excess`` the mean
over sessions of the session's mean excess return; ``lift_pts`` the pooled win rate minus the
pooled base rate of the series at the same decision sessions (a session the series has no base
rate for is left out). A decile spread cannot be measured live (the paper record keeps the
picks, not the ranked field): ``not_measured_live``. The paper's holding period must be the
basis's (``not_comparable``), a copy's hidden out-of-sample result stays hidden (``oos_hidden``)
and no settled trade is ``not_stored``; never a zero."""

from dataclasses import replace
from datetime import date

from algotrade.quant.edges import paths
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.paper import WON, PaperTrade
from algotrade.services.read.edge_evidence.live import by_signal_session, settled_trades
from algotrade.services.read.edge_evidence.series import BasisSeries
from algotrade.services.read.evaluation import versions
from algotrade.services.read.evaluation.decay import (
    LIVE,
    MEASURED,
    NOT_COMPARABLE,
    NOT_MEASURED_LIVE,
    NOT_STORED,
    OOS_HIDDEN,
    DecayBar,
    EdgeDecay,
)
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.values import Unknown


def _mean_excess(sessions: dict[date, list[PaperTrade]]) -> tuple[float | None, int]:
    means = [
        sum(found) / len(found)
        for trades in sessions.values()
        if (found := [t.excess_return for t in trades if t.excess_return is not None])
    ]
    return (sum(means) / len(means) if means else None), len(means)


def _lift(sessions: dict[date, list[PaperTrade]], series: BasisSeries) -> tuple[float | None, int]:
    bases = {w.row.decision_session: w.row for w in series.windows if w.row.eligible}
    used = [(trades, bases[day]) for day, trades in sessions.items() if day in bases]
    if not used:
        return None, 0
    hits = [float(sum(t.status == WON for t in trades)) for trades, _ in used]
    picks = [float(len(trades)) for trades, _ in used]
    base_hits = [float(row.base_hits or 0) for _, row in used]
    eligible = [float(row.eligible or 0) for _, row in used]
    return paths.pooled_lift(hits, picks, base_hits, eligible), len(used)


def live_bar(
    ctx: ReadContext, edge: Edge, decay: EdgeDecay, series: BasisSeries | Unknown
) -> DecayBar:
    """The live bar of ``decay``'s statistic on the basis ``series``."""
    published = decay.published
    if isinstance(series, Unknown):
        return DecayBar(LIVE, None, None, NOT_STORED)
    if series.hidden:
        return DecayBar(LIVE, None, None, OOS_HIDDEN)
    if published is not None and decay.basis_horizon != published.horizon_sessions:
        return DecayBar(LIVE, None, None, NOT_COMPARABLE)
    if decay.measure == "decile_spread":
        return DecayBar(LIVE, None, None, NOT_MEASURED_LIVE)
    sessions = by_signal_session(settled_trades(ctx, edge, series))
    value, n = _mean_excess(sessions) if decay.measure == "mean_excess" else _lift(sessions, series)
    if value is None:
        return DecayBar(LIVE, None, n or None, NOT_STORED)
    return DecayBar(LIVE, value, n, MEASURED)


def load_decay(ctx: ReadContext, edge: Edge, series: BasisSeries | Unknown) -> EdgeDecay | None:
    """The decay of ``edge``'s verdict with the live bar added; None when the verdict has no
    basis (nothing to compare)."""
    found = versions.load_verdict(ctx, edge).decay
    if found is None:
        return None
    return replace(found, bars=(*found.bars, live_bar(ctx, edge, found, series)))
