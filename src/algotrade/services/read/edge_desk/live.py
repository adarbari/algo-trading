"""An edge's live record: its paper trades judged against the backtest's usual range (ADR 0053
amendment 2026-10-09).

The backtest's win rate ``p`` is the edge's official result for the screen and holding period the
paper trades used (a site edge: the canonical run; the user's own: their latest run; its
out-of-sample slice, else the in-sample one while the out-of-sample is hidden, else the whole
history: ``basis`` says which). If ``p`` held, the wins among ``n`` closed trades are binomial;
the live win rate is ``on_track`` inside the ``live_low`` to ``live_high`` quantiles of that
(``quant.edge_statistics.win_rate_band``), ``below`` or ``above`` outside it, ``too_early`` until
``live_min_sessions`` have closed, ``no_backtest`` when the edge has no usable run (a run committed
after the session is none). Open and skipped trades are counted apart: never a loss. The sentences
and the bins of the picture are the server's; the browser derives nothing.

A trial (a new version, ``replaces`` the edge it would supersede) also carries its forward test:
its record beside the replaced edge's over the same sessions from the trial's start, and whether
``forward_sessions`` have passed and it has not done worse (``ForwardTest.can_replace``)."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.core.time.calendar import sessions_to
from algotrade.quant.edge_statistics import win_rate_band, win_rate_pmf
from algotrade.services.read.context import ReadContext
from algotrade.services.read.edge_desk.paper import (
    LOST,
    OPEN,
    SKIPPED,
    WON,
    PaperTrade,
    load_trades,
    with_instruments,
)
from algotrade.services.read.evaluation import runs, versions
from algotrade.services.read.evaluation.edges import Edge, load_edges

MAX_BINS = 20  # the picture's bars: the wins are grouped when there are more closed trades
SLICES = (("frozen", "out-of-sample"), ("split", "out-of-sample"), (runs.IN_SAMPLE, "in-sample"))
ON_TRACK, BELOW, ABOVE = "on_track", "below", "above"
TOO_EARLY, NO_BACKTEST, NO_TRADES = "too_early", "no_backtest", "no_trades"


@dataclass(frozen=True)
class RangeBin:
    """One bar of the picture: the win rates ``start`` to ``end`` and the chance (0 to 1) the live
    win rate falls there if the backtest's held."""

    start: float
    end: float
    chance: float


@dataclass(frozen=True)
class LiveRecord:
    """The record of the closed trades (``closed`` = ``wins`` + losses), the open and skipped
    ones counted apart; ``backtest_rate`` and its ``basis`` (None: no usable run); ``low`` and
    ``high`` the usual range of the live win rate and ``bins`` the picture of its distribution
    (None / empty until ``live_min_sessions`` have closed and a backtest rate exists)."""

    state: str
    closed: int
    wins: int
    open: int
    skipped: int
    win_rate: float | None
    backtest_rate: float | None
    basis: str
    low: float | None
    high: float | None
    bins: tuple[RangeBin, ...]
    headline: str


@dataclass(frozen=True)
class ForwardTest:
    """A trial's forward test: its own record and the replaced edge's, both over the trades
    signalled from the trial's ``since``; ``sessions`` have passed of the ``needed``."""

    replaces: str
    replaces_name: str
    since: date
    sessions: int
    needed: int
    this: LiveRecord
    replaced: LiveRecord
    can_replace: bool
    headline: str


@dataclass(frozen=True)
class EdgePaper:
    """One edge's paper record for the session: the live record, the trades (newest signal
    first) and, for a trial, its forward test."""

    edge_id: str
    record: LiveRecord
    trades: tuple[PaperTrade, ...]
    forward: ForwardTest | None


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def _backtest_rate(
    ctx: ReadContext, edge: Edge, screener: str, horizon: int
) -> tuple[float | None, str]:
    """The official win rate of ``screener`` at ``horizon`` and the words for its basis."""
    run = versions.own_run(ctx, edge) if edge.mine else runs.load_canonical_run(ctx, edge).run
    if run is None or run.after_session:
        return None, ""
    rows = [
        r
        for r in runs.load_run_rows(ctx, run)
        if (r.edge_variant, r.variant, r.role, r.horizon_sessions)
        == (runs.MAIN, screener, "screener", horizon)
    ]
    for kind, words in (*SLICES, ("all", "whole-history")):
        found = [r.hit_rate for r in rows if r.slice_kind == kind and r.hit_rate is not None]
        if found:
            return found[0], f"{words} win rate"
    return None, ""


def _bins(p: float, n: int) -> tuple[RangeBin, ...]:
    pmf = win_rate_pmf(p, n)
    if pmf is None:
        return ()
    step = math.ceil((n + 1) / MAX_BINS)
    return tuple(
        RangeBin(
            max(0.0, (k - 0.5) / n),
            min(1.0, (min(k + step, n + 1) - 0.5) / n),
            float(pmf[k : k + step].sum()),
        )
        for k in range(0, n + 1, step)
    )


def _counts(trades: Sequence[PaperTrade]) -> tuple[int, int, int, int]:
    won = sum(t.status == WON for t in trades)
    lost = sum(t.status == LOST for t in trades)
    return (
        won + lost,
        won,
        sum(t.status == OPEN for t in trades),
        sum(t.status == SKIPPED for t in trades),
    )


def _judge(
    closed: int,
    wins: int,
    sessions: int,
    counts: str,
    p: float | None,
    basis: str,
    settings: VerdictSettings,
) -> tuple[str, str, tuple[float, float] | None]:
    """The state, the sentence and the usual range of a record with ``closed`` closed trades over
    ``sessions`` signal sessions. The picks of one session are correlated (one market, one
    window), so the independent units of the band are the sessions, never the trades."""
    won = f"{wins} of {closed} closed trades won"
    if sessions < settings.live_min_sessions:
        more = f" {counts.capitalize()}." if counts else ""
        needed = settings.live_min_sessions
        return TOO_EARLY, f"{won}; judged once {needed} signal sessions have closed.{more}", None
    rate = wins / closed
    band = None if p is None else win_rate_band(p, sessions, settings.live_low, settings.live_high)
    if p is None or band is None:
        return (
            NO_BACKTEST,
            f"{won} ({_percent(rate)}); the edge has no backtest to compare with.",
            None,
        )
    state = BELOW if rate < band[0] else ABOVE if rate > band[1] else ON_TRACK
    where = {BELOW: "below", ABOVE: "above", ON_TRACK: "inside"}[state]
    words = (
        f"{won} ({_percent(rate)}) over {sessions} signal sessions, {where} the usual range of "
        f"{_percent(band[0])} to {_percent(band[1])} if the backtest's {basis} of "
        f"{_percent(p)} held."
    )
    return state, words, band


def live_record(
    ctx: ReadContext, edge: Edge, trades: Sequence[PaperTrade], settings: VerdictSettings
) -> LiveRecord:
    """``edge``'s record over ``trades`` (its own), judged by ``settings``."""
    closed, wins, open_, skipped = _counts(trades)
    sessions = len({t.signal_session for t in trades if t.status in (WON, LOST)})
    latest = max(trades, key=lambda t: t.signal_session, default=None)
    screener = latest.screener if latest else (edge.screeners[0] if edge.screeners else "")
    horizon = latest.horizon_sessions if latest else (edge.horizons[0] if edge.horizons else 0)
    p, basis = _backtest_rate(ctx, edge, screener, horizon)
    counts = f"{open_} open, {skipped} skipped" if open_ or skipped else ""
    state, headline, band = (
        (NO_TRADES, "No paper trades yet.", None)
        if not trades
        else _judge(closed, wins, sessions, counts, p, basis, settings)
    )
    bins = _bins(p, sessions) if band is not None and p is not None else ()
    return LiveRecord(
        state=state,
        closed=closed,
        wins=wins,
        open=open_,
        skipped=skipped,
        win_rate=wins / closed if closed else None,
        backtest_rate=p,
        basis=basis,
        low=band[0] if band else None,
        high=band[1] if band else None,
        bins=bins,
        headline=headline,
    )


def _forward(
    ctx: ReadContext,
    edge: Edge,
    mine: LiveRecord,
    settings: VerdictSettings,
    trades: Sequence[PaperTrade],
) -> ForwardTest | None:
    """The trial ``edge``'s forward test against the edge it replaces (None: it replaces none)."""
    old = next((e for e in load_edges(ctx) if e.id == edge.replaces), None)
    if old is None or edge.since is None:
        return None
    start = edge.since
    theirs = live_record(
        ctx,
        old,
        [t for t in trades if t.edge_id == old.id and t.signal_session >= start],
        settings,
    )
    sessions = sessions_to(start, ctx.session.date)
    behind = (
        mine.win_rate is not None
        and theirs.win_rate is not None
        and mine.win_rate < theirs.win_rate
    )
    can = sessions >= settings.forward_sessions and mine.closed > 0 and not behind
    if sessions < settings.forward_sessions:
        words = (
            f"{sessions} of {settings.forward_sessions} sessions of the forward test have passed."
        )
    elif behind:
        words = "Its win rate is behind the edge it would replace."
    else:
        words = "It can replace the edge."
    return ForwardTest(
        old.id, old.name, start, sessions, settings.forward_sessions, mine, theirs, can, words
    )


def load_edge_paper(ctx: ReadContext, edge_id: str) -> EdgePaper | None:
    """The paper record of the edge ``edge_id`` for ``ctx.session``; None: no such edge."""
    edges = {e.id: e for e in load_edges(ctx)}
    edge = edges.get(edge_id)
    if edge is None:
        return None
    trades = load_trades(ctx, {i: e.name for i, e in edges.items()})
    settings = load_verdict(ctx.configs)
    own = [t for t in trades if t.edge_id == edge.id]
    ordered = sorted(own, key=lambda t: (t.signal_session, -t.rank), reverse=True)
    record = live_record(ctx, edge, own, settings)
    forward = _forward(ctx, edge, record, settings, trades) if edge.state == "trial" else None
    return EdgePaper(edge.id, record, with_instruments(ctx, tuple(ordered)), forward)
