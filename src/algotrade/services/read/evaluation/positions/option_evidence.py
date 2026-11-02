"""What an option setup's own history says, on the cash it sets aside (ADR 0088 decision 20,
design 2.6; plan O1): ``OptionEvidence`` and ``load_option_evidence``.

Read from the canonical run's stored ledger of the verdict basis (the screen and holding period
its verdict rests on, never chosen here) through ``runs.load_run_trades`` only, each trade by its
``return_on_capital`` at the document's cost (a share of the collateral, ``capital_basis`` on
collateral), never recomputed:

- the *typical trade*: the median return on capital and its interquartile range (p25 to p75);
- the *bad trade*: the mean of the worst 5% of trades (``tails.cvar``) and how many trades that
  is (``bad_trades``, of ``trades``);
- *kept the premium*: the trades whose return on capital is above zero at the document's cost
  (a tie at zero did not keep it), of ``trades``;
- the cost of trading at the *middle price, worse side and full spread*: the stored cost levels
  of the basis (``edge_evidence.costs``), reused as they are;
- *by year*: the same typical trade and kept count per year of the decision session;
- *stress*: the worst trade in each reference stress episode the session knows (peak to trough,
  ``regime.episodes``) that was open in it (entry on or before the trough, exit on or after the
  peak); a window with no such trade has ``trades`` 0 and no worst, which is not a gap.

Fail closed, never a zero and never a subset: a canonical run missing or ending after the session,
no verdict basis, no ledger (``PRUNED`` / ``NOT_STORED``), a ledger under a licence the viewer
lacks, any counted trade without a return on capital, or no trade at all is one ``unknown`` and
every figure is None. Point in time: the canonical run is the latest committed on or before the
session, and only trades that exited by it count (as the exit rule reads them). No verdict is
made here: the basis is the one the stored (else live) judge fixed, and a setup with none has no
evidence; the judge's own rule holds an option verdict back until its unseen holdout."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import isfinite

from algotrade.quant.edges.statistics import count_above, quartiles
from algotrade.quant.edges.tails import cvar, worst
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_evidence.basis import OfficialBasis
from algotrade.services.read.edge_evidence.costs import EdgeCosts, load_edge_costs
from algotrade.services.read.edge_evidence.series import COLLATERAL
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.positions.exit_rule import basis_trades
from algotrade.services.read.evaluation.verdict import load_edge_summary, load_stored_summary
from algotrade.services.read.regime.episodes import load_regime_episodes
from algotrade.services.read.values import Unknown, UnknownCode

BAD_TAIL = 0.05  # the bad trade: the mean of the worst 5% of trades


@dataclass(frozen=True)
class OptionYear:
    """One year of decision sessions: its ``trades``, the ``typical`` return on capital (median)
    and how many ``kept`` the premium."""

    year: int
    trades: int
    typical: float | None
    kept: int


@dataclass(frozen=True)
class StressWindow:
    """One reference stress episode (``key``, ``name``) from its ``start`` (the peak) to its
    ``end`` (the trough): the ``trades`` that were open in it and the ``worst`` of their returns
    on capital (None, with ``trades`` 0: none was open)."""

    key: str
    name: str
    start: date
    end: date
    trades: int
    worst: float | None


@dataclass(frozen=True)
class OptionEvidence:
    """The evidence section. Every figure is None with ``unknown`` (the whole section). Returns
    are fractions of the collateral at the document's cost. ``typical`` the median and
    ``typical_lo`` / ``typical_hi`` its quartiles; ``bad_mean`` the mean of the worst
    ``bad_trades`` of ``trades``; ``kept`` of ``trades`` returned above zero. ``costs``: the stored
    cost levels (its own ``state`` says when not stored); ``stress`` the windows of the session
    (empty with the reason ``stress_unknown`` when the episodes are not available);
    ``in_sample_only``: the run hides its out-of-sample trades, so only in-sample ones are read."""

    unknown: Unknown | None = None
    basis_screener: str | None = None
    basis_horizon: int | None = None
    trades: int = 0
    typical: float | None = None
    typical_lo: float | None = None
    typical_hi: float | None = None
    bad_mean: float | None = None
    bad_trades: int = 0
    kept: int = 0
    costs: EdgeCosts | None = None
    by_year: tuple[OptionYear, ...] = ()
    stress: tuple[StressWindow, ...] = ()
    stress_unknown: Unknown | None = None
    in_sample_only: bool = False


def _unknown(edge: Edge, code: UnknownCode, why: str) -> Unknown:
    return Unknown(code, run_cause(edge.id, why))


def _years(counted: Sequence[runs.TradeRow], returns: Sequence[float]) -> tuple[OptionYear, ...]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for t, r in zip(counted, returns, strict=True):
        grouped[t.decision_session.year].append(r)
    out = []
    for year in sorted(grouped):
        _, mid, _, n = quartiles(grouped[year])
        out.append(OptionYear(year, n, mid, count_above(grouped[year])[0]))
    return tuple(out)


def _stress(
    ctx: ReadContext, edge: Edge, counted: Sequence[runs.TradeRow], returns: Sequence[float]
) -> tuple[tuple[StressWindow, ...], Unknown | None]:
    """The worst trade open in each episode the session knows (the episodes' own point in time)."""
    episodes = load_regime_episodes(ctx).episodes
    if not episodes:
        why = f"no stress episode is known at {ctx.session.date}"
        return (), _unknown(edge, UnknownCode.NO_ROW, why)
    out = []
    for e in episodes:
        open_in = [
            r
            for t, r in zip(counted, returns, strict=True)
            if (t.entry_session or t.decision_session) <= e.trough
            and (t.exit_session or t.decision_session) >= e.peak
        ]
        out.append(StressWindow(e.key, e.name, e.peak, e.trough, len(open_in), worst(open_in)))
    return tuple(out), None


def _returns(
    edge: Edge, run: runs.EdgeRun, rows: Sequence[runs.TradeRow]
) -> tuple[list[runs.TradeRow], list[float]] | Unknown:
    """The counted trades (won or lost, excluded ones left out) and their returns on capital, or
    why they cannot all be read: a licensed value, one not stored, a basis not on collateral, or
    no trade at all."""
    counted = [t for t in rows if t.status in ("won", "lost")]
    returns: list[float] = []
    for t in counted:
        cell = t.return_on_capital
        if cell.unknown is not None:
            return cell.unknown
        if cell.value is None or not isfinite(cell.value) or t.capital_basis not in COLLATERAL:
            why = f"run {run.run_id} stores no return on capital for a trade: re-run the backtest"
            return _unknown(edge, UnknownCode.NOT_STORED, why)
        returns.append(float(cell.value))
    if not counted:
        return _unknown(edge, UnknownCode.NO_ROW, f"{edge.id} has no trade of its basis yet")
    return counted, returns


def load_option_evidence(ctx: ReadContext, edge: Edge) -> OptionEvidence:
    """The evidence of ``edge`` (an option setup) at ``ctx.session``, or the one ``unknown``."""
    canonical = runs.load_canonical_run(ctx, edge, True)
    run = canonical.run
    if run is None:
        return OptionEvidence(unknown=canonical.not_run)
    day = ctx.session.date
    if run.range_to > day:  # its verdict, basis and ledger are not known then
        why = f"the canonical run ends {run.range_to}, after the session {day}"
        return OptionEvidence(unknown=_unknown(edge, UnknownCode.NOT_RUN, why))
    summary = load_stored_summary(ctx, edge, bounded=True)
    if summary is None:  # the live judge reads the unbounded canonical run: only if it is ours
        latest = runs.load_canonical_run(ctx, edge).run
        if latest is None or latest.run_id != run.run_id:
            why = f"the live verdict rests on a newer run than {run.run_id} (not bounded)"
            return OptionEvidence(unknown=_unknown(edge, UnknownCode.NOT_RUN, why))
        summary = load_edge_summary(ctx, edge)
    if summary.basis_screener is None or summary.basis_horizon is None:
        why = f"{edge.id} has no verdict basis ({summary.result})"
        return OptionEvidence(unknown=_unknown(edge, UnknownCode.NOT_RUN, why))
    screener, horizon = summary.basis_screener, summary.basis_horizon
    rows, unknown = basis_trades(ctx, edge, run, summary)
    found = unknown or _returns(edge, run, rows)
    if isinstance(found, Unknown):
        return OptionEvidence(unknown=found, basis_screener=screener, basis_horizon=horizon)
    counted, returns = found
    lo, mid, hi, n = quartiles(returns)
    bad, bad_n = cvar(returns, BAD_TAIL)
    basis = OfficialBasis(
        edge, run, (screener, horizon), run.split_from or edge.frozen_from, run.oos_hidden
    )
    stress, stress_unknown = _stress(ctx, edge, counted, returns)
    return OptionEvidence(
        None, screener, horizon, n, mid, lo, hi, bad, bad_n, count_above(returns)[0],
        load_edge_costs(ctx, edge, basis), _years(counted, returns), stress, stress_unknown,
        run.oos_hidden,
    )  # fmt: skip
