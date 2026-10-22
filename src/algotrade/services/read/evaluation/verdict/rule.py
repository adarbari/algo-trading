"""The verdict judge (ED8): one candidate judged to a verdict, the year rows, the edge facts,
``judge`` and the loader of an edge's verdict from its canonical run."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from algotrade.config.edges.document import MODEL_KIND, PAIR_KIND
from algotrade.config.edges.named import OUT_OF_WINDOW
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.portfolio import benchmark_words as benchword
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores, once_per_request
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.decay import decay_of
from algotrade.services.read.evaluation.edges import Edge, EdgePublished
from algotrade.services.read.evaluation.evidence import (
    COUNT_CRITERIA,
    LEVEL_WORDS,
    AtTarget,
    Projection,
    count_of,
    evidence_of,
    outlook_of,
)
from algotrade.services.read.evaluation.robustness import (
    EdgeHaircut,
    load_haircut,
    load_robustness,
)
from algotrade.services.read.evaluation.runs import Draws, EdgeRow
from algotrade.services.read.evaluation.verdict.basis import (
    UNDECLARED,
    BasisChoice,
    Declared,
    choose_basis,
)
from algotrade.services.read.evaluation.verdict.criteria import (
    _criteria,
    _words,
)
from algotrade.services.read.evaluation.verdict.level import (
    _basis_words,
    _columns,
    _level,
    _next_gap,
)
from algotrade.services.read.evaluation.verdict.model import (
    BOTH,
    DIAGNOSTIC,
    DIAGNOSTIC_SIDE,
    EN_DASH,
    FAIL,
    IN_SAMPLE,
    NOT_WORKING,
    OUT_OF_SAMPLE,
    PROMISING,
    WAITING,
    WORKS,
    EdgeSummary,
    EdgeVerdict,
    VerdictCriterion,
    YearRow,
    _Candidate,
    _candidates,
    _num,
    _pct,
    _ret,
    summary_of,
)


@dataclass(frozen=True)
class EdgeFacts:
    """What the verdict knows about the edge beyond its rows: its ``published`` figure, its
    ``schedule`` (an event schedule's count date cannot be projected), whether the
    out-of-sample result is ``hidden``, ``after`` the last session of the run (the next close is
    the first stored exit after it) and ``measured``: the sessions each (screen, holding
    period) measured with picks, read from the run's series only when called (None: no series
    is stored, as in an older run: the haircut keeps the stored count)."""

    published: EdgePublished | None = None
    schedule: str | None = None
    hidden: bool = False
    after: date | None = None
    measured: Callable[[], Mapping[tuple[str, int], int] | None] | None = None
    wins: bool = False  # the outcome is not a return: the Sharpe ratio is of the excess wins
    portfolio: bool = False  # a portfolio_return book (ADR 0074): read against its benchmark
    benchmark: str = ""  # ... the words of that benchmark ("SPY", "60% SPY and 40% AGG")
    base: str = ""  # the edge's base: ``out_of_window`` words the decile t as a Welch t
    site_trials: Callable[[], int] | None = None  # the variants tried across every site
    # edge, read when the haircut is (None: not counted)
    chain: bool = False  # an option_pnl edge: the basis cannot have been fixed in-sample
    neutral: bool = False  # the outcome is a residual return: market, size, momentum, value gone


def is_factor_neutral(edge: Edge) -> bool:
    """Whether the edge's outcome is a residual return (EB H11): the verdict says so."""
    return edge.settings is not None and edge.settings.factor_neutral


def counts_wins(edge: Edge) -> bool:
    """Whether the edge's trial statistics (Sharpe, deflated Sharpe, PBO, haircut) are of the
    session's excess wins: its outcome is not a return (a cushion or a ratio, not a model P&L;
    ADR 0064 amendment 2026-10-11). An edge with no resolved settings is read as a return."""
    s = edge.settings
    # a model P&L and a pair spread are returns
    return s is not None and not s.cost_applies and s.kind not in (MODEL_KIND, PAIR_KIND)


def is_chain(edge: Edge) -> bool:
    """Whether the edge's outcome is a chain P&L (``option_pnl``): no in-sample history."""
    return edge.settings is not None and edge.settings.kind == "option_pnl"


def projection_of(whole: EdgeRow) -> Projection:
    """What the basis's ``all`` row stores for a projection (ADR 0064 decision 7)."""
    return Projection(
        whole.projected_exits,
        whole.decisions_scheduled,
        whole.decisions_measured,
        whole.decisions_scheduled_oos,
        whole.decisions_measured_oos,
    )


def _haircut(c: _Candidate, facts: EdgeFacts) -> EdgeHaircut | None:
    """The basis's haircut Sharpe ratio over the sessions the run's series measured with picks
    (``measured``); the stored count when the run has no series."""
    whole = c.whole
    site = facts.site_trials() if facts.site_trials is not None and whole.sharpe else None
    if whole.sharpe is None or facts.measured is None:
        return load_haircut(whole.sharpe, whole.sessions, whole.trials, facts.wins, site)
    counted = facts.measured()
    n = whole.sessions if counted is None else counted.get((c.variant, c.horizon), 0)
    return load_haircut(whole.sharpe, n, whole.trials, facts.wins, site)


def _at_target(
    c: _Candidate,
    t: VerdictSettings,
    draws: Draws,
    decoys: bool,
    gap: VerdictCriterion | None,
    facts: EdgeFacts,
) -> AtTarget | None:
    """The verdict as it would stand once ``gap``'s count is reached, on today's stored figures
    (the count gates met, nothing else changed); None: the gap is not a count, or a copy's
    out-of-sample result is withheld."""
    if gap is None or gap.id not in COUNT_CRITERIA or facts.hidden:
        return None
    oos, whole = c.oos, c.whole
    _, needed, _ = count_of(gap.id, oos.sessions or 0, whole.sessions or 0, t)
    if gap.id == "trades":
        met = replace(oos, sessions=max(oos.sessions or 0, t.min_oos_trades))
        there = replace(c, oos=met)
    else:
        met = replace(oos, sessions=max(oos.sessions or 0, t.works_oos_trades))
        there = replace(
            c, oos=met, whole=replace(whole, sessions=max(whole.sessions or 0, t.works_trades))
        )
    crit = _criteria(there, t, draws, decoys)
    level, _ = _level(there, crit, t)
    failing = [_words(x) for x in crit if x.level == PROMISING and x.status == FAIL]
    next_gap = _next_gap(crit)
    reasons = tuple(failing or ([_words(next_gap)] if next_gap and level != WORKS else []))
    sentence = f"At {needed}, on today's figures: {LEVEL_WORDS[level]}"
    sentence += f". {' · '.join(reasons)}." if reasons else "."
    return AtTarget(needed, level, reasons, sentence)


def _judge_one(
    c: _Candidate,
    t: VerdictSettings,
    draws: Draws,
    decoys: bool,
    facts: EdgeFacts,
    headline: bool = False,
) -> EdgeVerdict:
    """``headline``: only what the label, result and figures need. The level and reason come
    from ``_criteria`` and ``_level`` alone (the haircut, decay, robustness, columns, evidence
    and outlook are pieces the verdict carries beside them, never inputs to them), so they are
    the same as the full verdict's."""
    c = replace(c, timed=facts.base == OUT_OF_WINDOW)
    crit = _criteria(c, t, draws, decoys, facts.portfolio)
    level, reason = _level(c, crit, t)
    gap = _next_gap(crit)
    outlook = (
        None
        if headline
        else outlook_of(
            gap,
            _words(gap) if gap else "",
            c.oos.sessions,
            c.whole.sessions,
            t,
            facts.schedule,
            facts.hidden,
            projection_of(c.whole),
            facts.after,
            _at_target(c, t, draws, decoys, gap, facts),
        )
    )
    oos, whole = c.oos, c.whole
    pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    basis = _basis_words((c.variant, c.horizon))
    tags = ["short leg"] if oos.side == "short" else []
    if facts.neutral:  # the figure is the return left after the ETF factor loadings
        tags.append("factor-neutral: market, size, momentum and value taken off")
    held = f" ({', '.join(tags)})" if tags else ""
    body = (
        f"Out-of-sample, {basis}: the book beat {facts.benchmark} in {_pct(oos.hit_rate)} of "
        f"sessions, a mean excess return of {_ret(oos.mean_excess_picks)}."
        if facts.portfolio
        else f"Out-of-sample, {basis}{held}: win rate {_pct(oos.hit_rate)} against a base rate of "
        f"{_pct(oos.base_rate)} ({_num(pts, 0)} pts)."
    )
    shown = level in (WORKS, PROMISING, NOT_WORKING)
    deflated = whole.deflated_sharpe if whole.deflated_sharpe is not None else oos.deflated_sharpe
    pbo = whole.pbo if whole.pbo is not None else oos.pbo
    return EdgeVerdict(
        edge_id="",
        verdict=level,
        rationale=reason,
        headline=f"{body} {reason}." if reason else body,
        result=(
            f"Beat the benchmark in {_pct(oos.hit_rate)} of sessions"
            if facts.portfolio
            else f"Win rate {_pct(oos.hit_rate)} · base rate {_pct(oos.base_rate)}"
        )
        if shown
        else reason,
        criteria=crit,
        basis=basis,
        side=oos.side,
        trades=whole.sessions,
        oos_trades=oos.sessions,
        win_rate=oos.hit_rate,
        base_rate=oos.base_rate,
        lift_pts=pts,
        lift=oos.lift,
        decile_spread=oos.decile_spread,
        decile_t=oos.decile_t,
        sharpe=whole.sharpe,
        deflated_sharpe=deflated,
        pbo=pbo,
        trials=whole.trials,
        deciles=c.insample.decile_means if c.insample else (),
        robustness=None
        if headline
        else load_robustness(oos.lift, draws, c.horizon, c.variant, whole.trials),
        columns=() if headline else _columns(c, t),
        evidence=None if headline else evidence_of(oos.sessions, whole.sessions, crit, t, outlook),
        haircut=None if headline else _haircut(c, facts),
        decay=None
        if headline
        else decay_of(facts.published, c.horizon, c.insample, oos, facts.hidden, t),
    )


def _period(year: str, split: date | None) -> str:
    if split is None or not year.isdigit():
        return IN_SAMPLE
    first, last = date(int(year), 1, 1), date(int(year), 12, 31)
    return IN_SAMPLE if last < split else OUT_OF_SAMPLE if first >= split else BOTH


def _row_of(r: EdgeRow, year: str, period: str, first: date, last: date, part: bool) -> YearRow:
    label = f"{year} {first:%b}{EN_DASH}{last:%b}" if part else year
    return YearRow(
        year, period, label, first, last, part, r.hit_rate, r.base_rate,
        runs.lift_points(r.hit_rate, r.base_rate), r.decile_spread, r.sessions,
    )  # fmt: skip


def _live_years(years: tuple[EdgeRow, ...]) -> tuple[EdgeRow, ...]:
    """``years`` from the first to the last that has sessions: the years the baselines cover
    before (or after) the screen's inputs exist are not rows (a year with no sessions says
    nothing about the screen)."""
    live = [i for i, r in enumerate(years) if r.sessions]
    return years[live[0] : live[-1] + 1] if live else ()


def _years(c: _Candidate, split: date | None, range_to: date | None = None) -> tuple[YearRow, ...]:
    """The year rows from the screen's first year with sessions to its last; a year the split
    falls in is its in-sample then its out-of-sample part, the latter up to the run's last
    session ``range_to`` (a run from before the parts keeps the one ``both`` row)."""
    parts = {r.slice_value: r for r in c.year_parts}
    out: list[YearRow] = []
    for r in _live_years(c.years):
        year = r.slice_value
        mine = [(side, parts.get(f"{year}:{side}")) for side in (IN_SAMPLE, OUT_OF_SAMPLE)]
        cut = split is not None and year.isdigit() and split.year == int(year)
        if cut and split is not None and all(p for _, p in mine):
            first, last = date(int(year), 1, 1), date(int(year), 12, 31)
            bounds = {
                IN_SAMPLE: (first, split - timedelta(days=1)),
                OUT_OF_SAMPLE: (split, min(last, range_to) if range_to else last),
            }
            out += [
                _row_of(p, year, side, *bounds[side], True) for side, p in mine if p is not None
            ]
        else:
            first = date(int(year), 1, 1) if year.isdigit() else date.min
            last = date(int(year), 12, 31) if year.isdigit() else date.min
            period = BOTH if any(p for _, p in mine) and not cut else _period(year, split)
            out.append(_row_of(r, year, period, first, last, False))
    return tuple(out)


def _waiting(edge_id: str, reason: str, side: str = "long") -> EdgeVerdict:
    return EdgeVerdict(edge_id, WAITING, reason, reason, reason, side=side)


def _diagnostic(edge_id: str) -> EdgeVerdict:
    reason = DIAGNOSTIC_SIDE
    return EdgeVerdict(edge_id, DIAGNOSTIC, reason, reason, reason, side="long_short")


def _judge_candidate(
    c: _Candidate,
    t: VerdictSettings,
    draws: Draws,
    decoys: bool,
    lost_inputs: Sequence[str],
    facts: EdgeFacts,
    headline: bool = False,
) -> EdgeVerdict:
    """A candidate that lost inputs (its own screen could not read a table on some decision
    sessions) is Waiting on data even when it has rows: the figures are not the whole test."""
    lost = [x for x in lost_inputs if x.startswith(f"{runs.MAIN}/{c.variant}:")]
    if lost:
        reason = f"The result lost inputs for {c.variant}: {'; '.join(lost)}"
        return replace(_waiting("", reason), basis=_basis_words((c.variant, c.horizon)))
    return _judge_one(c, t, draws, decoys, facts, headline)


def judge(
    edge_id: str,
    rows: Sequence[EdgeRow] | None,
    split: date | None,
    t: VerdictSettings,
    lost_inputs: Sequence[str] = (),
    draws: Draws = (),
    decoys: bool = True,
    declared: Declared = UNDECLARED,
    basis: BasisChoice | None = None,
    facts: EdgeFacts | None = None,
    range_to: date | None = None,
    headline: bool = False,
) -> EdgeVerdict:
    """The verdict of ``edge_id`` from its official result's ``rows`` (None: it has no official
    result); ``split``: the out-of-sample start; ``draws``: the run's random-pick draws (none:
    not measured, which caps the verdict at Promising); ``declared``: the document's basis;
    ``basis``: one already chosen (a hidden copy's, from rows the verdict does not see), else
    ``choose_basis`` over ``rows``; ``facts``: the edge's
    published figure, schedule and whether its out-of-sample result is hidden; ``range_to``: the
    run's last session (the out-of-sample year part ends there); ``headline``: the label, result
    and figures only (no years, columns, evidence, haircut, decay or robustness), the same
    ``verdict`` and ``result`` as without."""
    if rows is None:
        return _waiting(edge_id, "No official result yet")
    found = _candidates(rows)
    if found and all(c.oos.side == "long_short" for c in found):
        return _diagnostic(edge_id)  # never a verdict basis
    choice = (
        basis
        if basis is not None
        else choose_basis(rows, t, declared, decoys, facts.portfolio if facts else False)
    )
    if choice.key is None:
        lost = f": {'; '.join(lost_inputs)}" if lost_inputs and not found else ""
        return _waiting(edge_id, f"{choice.reason}{lost}")
    on = _basis_words(choice.key)
    c = next((x for x in found if (x.variant, x.horizon) == choice.key), None)
    if c is None:
        lost = f": {'; '.join(lost_inputs)}" if lost_inputs else ""
        reason = f"The official result has no out-of-sample figures for {on}{lost}"
        return replace(_waiting(edge_id, reason), basis=on)
    facts = facts or EdgeFacts()
    judged = _judge_candidate(
        replace(c, chain=facts.chain), t, draws, decoys, lost_inputs, facts, headline
    )
    years = () if headline else _years(c, split, range_to)
    return replace(judged, edge_id=edge_id, years=years, basis_why=choice.why)


def _inputs(ctx: Stores, run: runs.EdgeRun) -> tuple[tuple[EdgeRow, ...], Draws]:
    """``run``'s rows and random-pick draws, read once per request however many summaries ask."""
    return once_per_request(
        ctx,
        ("edge-run-inputs", run.run_id, run.oos_hidden),
        lambda: (runs.load_run_rows(ctx, run), runs.load_run_draws(ctx, run)),
    )


def load_edge_verdict(ctx: Stores, edge: Edge, headline: bool = False) -> EdgeVerdict:
    """The verdict of ``edge`` from its canonical run's stored rows. Like ``canonicalRun`` it
    ignores ``after_session`` (ADR 0036: runs are read by run, not by session). ``headline``:
    the label, result and figures only, without the haircut (so no read of the run's series or
    of the site's trials), decay, robustness, years, columns or outlook."""
    settings = load_verdict(ctx.configs)
    run = runs.load_canonical_run(ctx, edge).run
    if run is None:
        return judge(edge.id, None, edge.frozen_from, settings)
    rows, draws = _inputs(ctx, run)  # memoised: a page asking `summary` and `verdict` reads once
    return judge(
        edge.id,
        rows,
        run.split_from or edge.frozen_from,  # the split its year parts were cut at
        settings,
        run.lost_inputs,
        draws=draws,
        decoys=bool(edge.baselines),
        declared=Declared(edge.promoted, edge.basis_horizon),
        facts=EdgeFacts(
            edge.published,
            edge.schedule,
            after=run.range_to,
            measured=None if headline else lambda: runs.load_measured_sessions(ctx, run),
            wins=counts_wins(edge),
            chain=is_chain(edge),
            portfolio=edge.settings is not None and edge.settings.kind == PORTFOLIO_KIND,
            benchmark=benchword(edge.settings.benchmark) if edge.settings is not None else "",
            neutral=is_factor_neutral(edge),
            base=edge.base,
            site_trials=None if edge.mine or headline else lambda: runs.load_site_trials(ctx),
        ),
        range_to=run.range_to,
        headline=headline,
    )


def load_edge_summary(ctx: Stores, edge: Edge) -> EdgeSummary:
    """The headline of a site edge's verdict (what the edges list shows): the same judge on the
    same canonical run, without the pieces the list never reads."""
    return summary_of(load_edge_verdict(ctx, edge, headline=True))
