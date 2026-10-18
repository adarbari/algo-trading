"""An edge's verdict (``EdgeVerdict``, ED8): Works, Promising, Not working, Not enough data or
Waiting on data, judged on its official result (the canonical run) by one deterministic rule.

The candidates are the main edge variant's implementation rows (role not ``baseline``), each
(screen, holding period) with its out-of-sample (``frozen``) and whole-history (``all``) rows. The
verdict rests on ONE of them, its basis, fixed before the frozen period is read (ADR 0065,
``choose_basis``): the edge document's declared screener and horizon (``Declared``) narrow the
candidates; of those left, the best by the verdict's own ranking (level, then lift) applied to the
in-sample figures alone. No frozen, split, year or whole-history figure takes part, so the best of
several out-of-sample results is never what is tested. The other candidates are not judged for the
headline. First match wins: Waiting on data (no official result, no candidate rows, or no basis);
Not enough data (fewer out-of-sample trades than ``min_oos_trades``, or a criterion that is not
measured); Not working (a hard failure: out-of-sample win rate not above the base rate, t,
overfitting probability, deflated Sharpe, or worse than the median baseline; then any criterion of
Promising missed); Promising; Works (more trades, stricter thresholds, and an out-of-sample lift
above at least ``random_beat_share`` of the random-pick backtest's draws,
``quant.edges.statistics.percentile_of``; a run with no draws is "not measured" and caps the verdict
at Promising). The statistics are the stored rows' (``quant/edges/statistics.py``), never
recomputed; the thresholds are site data (``config/site/verdict.toml``); the sentences are the
server's, the browser words nothing."""

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Final

from algotrade.config.edges.document import MODEL_KIND, PAIR_KIND
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.decay import EdgeDecay, decay_of
from algotrade.services.read.evaluation.edges import Edge, EdgePublished
from algotrade.services.read.evaluation.evidence import (
    COUNT_CRITERIA,
    LEVEL_WORDS,
    AtTarget,
    EvidenceProgress,
    Projection,
    count_of,
    evidence_of,
    outlook_of,
)
from algotrade.services.read.evaluation.robustness import (
    EdgeHaircut,
    Robustness,
    beat_share,
    load_haircut,
    load_robustness,
)
from algotrade.services.read.evaluation.runs import EdgeRow

WORKS: Final = "works"
PROMISING: Final = "promising"
NOT_WORKING: Final = "not_working"
NOT_ENOUGH: Final = "not_enough_data"
WAITING: Final = "waiting_on_data"
DIAGNOSTIC: Final = "diagnostic_only"  # a long-short result: a spread is never a verdict basis
ORDER: Final = (DIAGNOSTIC, WAITING, NOT_ENOUGH, NOT_WORKING, PROMISING, WORKS)  # worst to best
PASS, FAIL, NOT_MEASURED, NOT_APPLICABLE = "pass", "fail", "not_measured", "not_applicable"
CRITERION_STATUSES: Final = (
    PASS,
    FAIL,
    NOT_MEASURED,
    NOT_APPLICABLE,
)  # a criterion's status, each explained in the Guide
IN_SAMPLE, OUT_OF_SAMPLE, BOTH, ALL = "in_sample", "out_of_sample", "both", "all"
NO_DECOYS = "no decoys declared"  # the value of a decoy criterion that does not apply
DIAGNOSTIC_SIDE = (
    "A long-short spread is a diagnostic: no verdict rests on it (a short leg alone can)"
)
EN_DASH = "\u2013"  # between the months of a partial year's label


@dataclass(frozen=True)
class VerdictCriterion:
    """One test of the verdict: what was measured, what it must reach and whether it did
    (``status``: ``pass``, ``fail``, ``not_measured`` or ``not_applicable``: the test has nothing to
    test, as a decoy comparison with no decoys declared; it counts neither for nor against the
    level); ``level``: the verdict it gates."""

    id: str
    label: str
    value: str
    threshold: str
    status: str
    level: str


@dataclass(frozen=True)
class VerdictColumn:
    """The basis's figures over one ``period`` (``in_sample``, ``out_of_sample`` or ``all``);
    ``thin``: the out-of-sample column has fewer trades than the verdict needs. A figure not
    stored (older runs) is None."""

    period: str
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    trades: int | None
    decile_spread: float | None
    decile_t: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    thin: bool
    picks_t: float | None = None  # the t-ratio of ``sharpe`` over the picks series
    reference_rate: float | None = None  # expires_otm only: the risk-neutral rate of the win
    touch_rate: float | None = None  # expires_otm only: picks whose strike was touched


@dataclass(frozen=True)
class YearRow:
    """One calendar year of the basis (screen, holding period), or the part of it on one side
    of the split (``partial``: a year the split falls in is two rows, in-sample then
    out-of-sample); ``period``: ``in_sample``, ``out_of_sample`` or ``both`` (a run from before
    the parts); ``label``: the row's name ("2026 Jan-Mar", en dash), from ``from_date``
    to ``to_date``."""

    year: str
    period: str
    label: str
    from_date: date
    to_date: date
    partial: bool
    win_rate: float | None
    base_rate: float | None
    lift_pts: float | None
    decile_spread: float | None
    trades: int | None


@dataclass(frozen=True)
class EdgeVerdict:
    """The verdict of one edge. ``basis``: the screen and holding period it rests on (None:
    none); the figures are the basis's out-of-sample ones (``trades``: the whole run's);
    ``result``: the one-line out-of-sample result for the list; ``headline``: the sentence for
    the page; ``rationale``: the first failing criterion in words."""

    edge_id: str
    verdict: str
    rationale: str
    headline: str
    result: str
    criteria: tuple[VerdictCriterion, ...] = ()
    basis: str | None = None
    trades: int | None = None
    oos_trades: int | None = None
    win_rate: float | None = None
    base_rate: float | None = None
    lift_pts: float | None = None
    lift: float | None = None
    decile_spread: float | None = None
    decile_t: float | None = None
    sharpe: float | None = None
    deflated_sharpe: float | None = None
    pbo: float | None = None
    years: tuple[YearRow, ...] = ()
    trials: int | None = None  # the variants tried on the edge (the whole result's count)
    deciles: tuple[float | None, ...] = ()  # in-sample mean outcome per tenth, best-ranked first
    robustness: Robustness | None = None  # the lift among the random-pick backtests
    columns: tuple[VerdictColumn, ...] = ()  # in-sample, out-of-sample, all (empty: waiting)
    evidence: EvidenceProgress | None = None  # the trades against what the verdict needs
    haircut: EdgeHaircut | None = None  # the basis's Sharpe ratio after the variants tried
    decay: EdgeDecay | None = None  # the paper's figure against the in- and out-of-sample ones
    basis_why: str = ""  # a basis chosen among several: the in-sample lifts it was chosen on
    side: str = "long"  # the basis's outcome side: long | short | long_short (ADR 0053 amendment)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _num(x: float | None, digits: int = 2) -> str:
    return "not stored" if x is None else f"{x:.{digits}f}"


def _crit(
    id: str, label: str, value: str, threshold: str, ok: bool | None, level: str
) -> VerdictCriterion:
    status = NOT_MEASURED if ok is None else PASS if ok else FAIL
    return VerdictCriterion(id, label, value, threshold, status, level)


def _not_applicable(
    id: str, label: str, value: str, threshold: str, level: str
) -> VerdictCriterion:
    return VerdictCriterion(id, label, value, threshold, NOT_APPLICABLE, level)


def _at_least(x: float | None, bound: float) -> bool | None:
    return None if x is None else x >= bound


def _at_most(x: float | None, bound: float) -> bool | None:
    return None if x is None else x <= bound


@dataclass(frozen=True)
class _Candidate:
    variant: str
    horizon: int
    oos: EdgeRow
    whole: EdgeRow
    insample: EdgeRow | None
    baselines: tuple[EdgeRow, ...]
    years: tuple[EdgeRow, ...]
    year_parts: tuple[EdgeRow, ...] = ()  # a year cut by the split, as ``<year>:<side>`` rows
    lone: bool = False  # the only screener of the run at its holding period: no PBO peers


def _by_year(row: EdgeRow) -> str:
    return row.slice_value


def _candidates(rows: Sequence[EdgeRow]) -> list[_Candidate]:
    main = [r for r in rows if r.edge_variant == runs.MAIN and not r.exploratory]
    found = []
    for variant, horizon in sorted(
        {(r.variant, r.horizon_sessions) for r in main if r.role != "baseline"}
    ):
        mine = [r for r in main if r.variant == variant and r.horizon_sessions == horizon]
        oos = [r for r in mine if r.slice_kind == "frozen"]
        whole = [r for r in mine if r.slice_kind == "all"]
        before = [r for r in mine if r.slice_kind == "in_sample"]  # absent in older runs
        if len(oos) != 1 or len(whole) != 1:
            continue
        base = tuple(
            r
            for r in main
            if r.role == "baseline" and r.horizon_sessions == horizon and r.slice_kind == "frozen"
        )
        years = tuple(sorted((r for r in mine if r.slice_kind == "year"), key=_by_year))
        parts = tuple(sorted((r for r in mine if r.slice_kind == "year_part"), key=_by_year))
        trials = {
            (r.edge_variant, r.variant)
            for r in rows
            if r.role not in (runs.BASELINE, runs.RANDOM)
            and r.slice_kind == "all"
            and r.horizon_sessions == horizon
            and not r.exploratory
        }
        found.append(
            _Candidate(
                variant,
                horizon,
                oos[0],
                whole[0],
                before[0] if len(before) == 1 else None,
                base,
                years,
                parts,
                len(trials) == 1,
            )
        )
    return found


def _first(crit: Sequence[VerdictCriterion], level: str) -> VerdictCriterion | None:
    return next(
        (x for x in crit if x.level == level and x.status not in (PASS, NOT_APPLICABLE)), None
    )


def _words(x: VerdictCriterion) -> str:
    if x.status == NOT_MEASURED:
        return f"{x.label} is not measured yet"
    return f"{x.label} is {x.value}; it needs {x.threshold}"


def _random(c: _Candidate, t: VerdictSettings, draws: Sequence[EdgeRow]) -> tuple[str, bool | None]:
    """What the out-of-sample lift beats of the random-pick draws at the candidate's holding
    period, in words, and whether that reaches ``random_beat_share`` (None: not measured)."""
    share, n = beat_share(c.oos.lift, draws, c.horizon, c.variant)
    if share is None:
        return "not measured yet", None
    return f"beats {_pct(share)} of {n} random picks", share >= t.random_beat_share


ONE_TRIAL = "one variant tried"  # the value of a PBO criterion that does not apply


def _overfit(id: str, pbo: float | None, bound: float, level: str, alone: bool) -> VerdictCriterion:
    """A PBO criterion: not applicable for a lone trial (ADR 0064 amendment 2026-10-11: PBO
    compares the edge's alternatives, never its baselines), else at most ``bound``."""
    label, threshold = "Chance the result is overfitting", f"at most {bound:g}"
    if alone:
        return _not_applicable(id, label, ONE_TRIAL, threshold, level)
    return _crit(id, label, _num(pbo), threshold, _at_most(pbo, bound), level)


def _beats(own: float | None, others: Sequence[float], declared: int) -> bool | None:
    """Whether ``own`` beats every one of ``declared`` baselines whose figures are ``others``:
    None (not measured) without a figure of its own or of any baseline, or when it beats the
    measured ones but some baseline has no figure; False as soon as a measured one beats it."""
    if own is None or not others:
        return None
    if own <= max(others):
        return False
    return True if len(others) == declared else None


def _measured(found: int, declared: int) -> str:
    """`` (n of m measured)`` when a declared baseline has no figure, else nothing."""
    return f" ({found} of {declared} measured)" if declared and found < declared else ""


def _criteria(
    c: _Candidate, t: VerdictSettings, draws: Sequence[EdgeRow], decoys: bool
) -> tuple[VerdictCriterion, ...]:
    oos, whole = c.oos, c.whole
    trades = whole.sessions
    oos_pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    in_pts = runs.lift_points(c.insample.hit_rate, c.insample.base_rate) if c.insample else None
    pbo = whole.pbo if whole.pbo is not None else oos.pbo
    alone = c.lone and pbo is None  # a lone trial has nothing to overfit among: not applicable
    dsr = whole.deflated_sharpe if whole.deflated_sharpe is not None else oos.deflated_sharpe
    lifts = [b.lift for b in c.baselines if b.lift is not None]
    spreads = [b.decile_spread for b in c.baselines if b.decile_spread is not None]
    # a baseline with no figure is not measured, never left out: a pass over some of the decoys
    # is "not measured" (a fail over those measured stays a fail)
    beats_all = _beats(oos.lift, lifts, len(c.baselines))
    beats_spread = _beats(oos.decile_spread, spreads, len(c.baselines))
    keeps = None if oos_pts is None or in_pts is None else oos_pts >= t.oos_lift_share * in_pts
    win_ok = None if oos_pts is None else oos_pts > 0
    enough = (
        None
        if trades is None or oos.sessions is None
        else trades >= t.works_trades and oos.sessions >= t.works_oos_trades
    )
    versus = f"{_pct(oos.hit_rate)} against {_pct(oos.base_rate)}"
    random_value, random_beaten = _random(c, t, draws)
    best = f"{_num(oos.lift)} vs best {_num(max(lifts))}" if lifts else "not stored"
    best += _measured(len(lifts), len(c.baselines))
    spread_value = _num(oos.decile_spread, 3) + _measured(len(spreads), len(c.baselines))
    # no decoys declared: nothing was tested, so the two decoy criteria do not apply (not a pass)
    against_all = (
        _crit(
            "baselines",
            "Lift against every baseline",
            best,
            "beats every baseline",
            beats_all,
            PROMISING,
        )
        if decoys
        else _not_applicable(
            "baselines", "Lift against every baseline", NO_DECOYS, "beats every baseline", PROMISING
        )
    )
    spread_all = (
        _crit(
            "works_spread",
            "Decile spread against every baseline",
            spread_value,
            "beats every baseline",
            beats_spread,
            WORKS,
        )
        if decoys
        else _not_applicable(
            "works_spread",
            "Decile spread against every baseline",
            NO_DECOYS,
            "beats every baseline",
            WORKS,
        )
    )
    return (
        _crit("trades", "Out-of-sample trades", str(oos.sessions), f"at least {t.min_oos_trades}",
              None if oos.sessions is None else oos.sessions >= t.min_oos_trades, PROMISING),
        _crit("win_rate", "Out-of-sample win rate above the base rate", versus,
              "above the base rate", win_ok, PROMISING),
        _crit("decile_t", "Top vs bottom decile t", _num(oos.decile_t),
              f"at least {t.promising_t:g}", _at_least(oos.decile_t, t.promising_t), PROMISING),
        _overfit("pbo", pbo, t.max_pbo, PROMISING, alone),
        _crit("dsr", "Deflated Sharpe", _num(dsr), f"at least {t.promising_dsr:g}",
              _at_least(dsr, t.promising_dsr), PROMISING),
        against_all,
        _crit("oos_lift", "Out-of-sample lift keeps its size",
              f"{_num(oos_pts, 1)} pts vs {_num(in_pts, 1)} pts in-sample",
              f"at least {t.oos_lift_share:g} of the in-sample lift", keeps, PROMISING),
        _crit("works_trades", "Trades, and out-of-sample trades", f"{trades} and {oos.sessions}",
              f"at least {t.works_trades} and {t.works_oos_trades}", enough, WORKS),
        _crit("works_t", "Top vs bottom decile t", _num(oos.decile_t),
              f"at least {t.works_t:g}", _at_least(oos.decile_t, t.works_t), WORKS),
        _crit("works_picks_t", "Picks-series t (Sharpe ratio's t-ratio)", _num(oos.picks_t),
              f"at least {t.works_picks_t:g}", _at_least(oos.picks_t, t.works_picks_t), WORKS),
        _crit("works_dsr", "Deflated Sharpe", _num(dsr), f"at least {t.works_dsr:g}",
              _at_least(dsr, t.works_dsr), WORKS),
        _overfit("works_pbo", pbo, t.works_max_pbo, WORKS, alone),
        spread_all,
        _crit("random", "Beats random picks", random_value,
              f"beats at least {_pct(t.random_beat_share)} of them", random_beaten, WORKS),
    )  # fmt: skip


def _level(c: _Candidate, crit: Sequence[VerdictCriterion], t: VerdictSettings) -> tuple[str, str]:
    oos, whole = c.oos, c.whole
    by = {x.id: x for x in crit}
    trades = oos.sessions
    if trades is None or trades < t.min_oos_trades:
        return (
            NOT_ENOUGH,
            f"Only {trades or 0} out-of-sample trades; {t.min_oos_trades} are needed",
        )
    pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    pbo = whole.pbo if whole.pbo is not None else oos.pbo
    dsr = whole.deflated_sharpe if whole.deflated_sharpe is not None else oos.deflated_sharpe
    lifts = [b.lift for b in c.baselines if b.lift is not None]
    below_median = oos.lift is not None and bool(lifts) and oos.lift < statistics.median(lifts)
    hard = [
        (pts is not None and pts <= 0, "win_rate"),
        (oos.decile_t is not None and oos.decile_t < t.not_working_t, "decile_t"),
        (pbo is not None and pbo > t.max_pbo, "pbo"),
        (dsr is not None and dsr < t.not_working_dsr, "dsr"),
        (below_median, "baselines"),
    ]
    failed = next((i for bad, i in hard if bad), None)
    if failed:
        return NOT_WORKING, _words(by[failed])
    missed = _first(crit, PROMISING)
    if missed is not None:
        failing = next((x for x in crit if x.level == PROMISING and x.status == FAIL), None)
        if failing is not None:
            return NOT_WORKING, _words(failing)
        return NOT_ENOUGH, _words(missed)
    gap = _first(crit, WORKS)
    return (WORKS, "") if gap is None else (PROMISING, _words(gap))


def _column(
    period: str, r: EdgeRow | None, deflated: float | None, pbo: float | None, thin: bool = False
) -> VerdictColumn:
    if r is None:  # an older run has no in-sample row
        return VerdictColumn(period, None, None, None, None, None, None, None, None, None, thin)
    return VerdictColumn(
        period, r.hit_rate, r.base_rate, runs.lift_points(r.hit_rate, r.base_rate), r.sessions,
        r.decile_spread, r.decile_t, r.sharpe, deflated, pbo, thin, r.picks_t,
        r.reference_rate, r.touch_rate,
    )  # fmt: skip


def _columns(c: _Candidate, t: VerdictSettings) -> tuple[VerdictColumn, ...]:
    """The in-sample, out-of-sample and all columns, each with its own row's deflated Sharpe and
    overfitting probability (stored on ``all`` only; a side's is normally not: missing, never
    another column's)."""
    ins, oos = c.insample, c.oos
    thin = oos.sessions is None or oos.sessions < t.min_oos_trades
    return (
        _column(IN_SAMPLE, ins, ins.deflated_sharpe if ins else None, ins.pbo if ins else None),
        _column(OUT_OF_SAMPLE, oos, oos.deflated_sharpe, oos.pbo, thin),
        _column(ALL, c.whole, c.whole.deflated_sharpe, c.whole.pbo),
    )


def _basis_words(key: tuple[str, int]) -> str:
    return f"{key[0]}, {key[1]} trading days"


def _next_gap(crit: Sequence[VerdictCriterion]) -> VerdictCriterion | None:
    """The first test not passed: Promising's in order, then Works's (None: all pass)."""
    return _first(crit, PROMISING) or _first(crit, WORKS)


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
    site_trials: Callable[[], int] | None = None  # the variants tried across every site
    # edge, read when the haircut is (None: not counted)


def counts_wins(edge: Edge) -> bool:
    """Whether the edge's trial statistics (Sharpe, deflated Sharpe, PBO, haircut) are of the
    session's excess wins: its outcome is not a return (a cushion or a ratio, not a model P&L;
    ADR 0064 amendment 2026-10-11). An edge with no resolved settings is read as a return."""
    s = edge.settings
    # a model P&L and a pair spread are returns
    return s is not None and not s.cost_applies and s.kind not in (MODEL_KIND, PAIR_KIND)


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
    draws: Sequence[EdgeRow],
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
    c: _Candidate, t: VerdictSettings, draws: Sequence[EdgeRow], decoys: bool, facts: EdgeFacts
) -> EdgeVerdict:
    crit = _criteria(c, t, draws, decoys)
    level, reason = _level(c, crit, t)
    gap = _next_gap(crit)
    outlook = outlook_of(
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
    oos, whole = c.oos, c.whole
    pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    basis = _basis_words((c.variant, c.horizon))
    held = " (short leg)" if oos.side == "short" else ""
    body = (
        f"Out-of-sample, {basis}{held}: win rate {_pct(oos.hit_rate)} against a base rate of "
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
        result=f"Win rate {_pct(oos.hit_rate)} · base rate {_pct(oos.base_rate)}"
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
        robustness=load_robustness(oos.lift, draws, c.horizon, c.variant, whole.trials),
        columns=_columns(c, t),
        evidence=evidence_of(oos.sessions, whole.sessions, crit, t, outlook),
        haircut=_haircut(c, facts),
        decay=decay_of(facts.published, c.horizon, c.insample, oos, facts.hidden, t),
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


def _rank(lift_pts: float | None) -> float:
    return float("-inf") if lift_pts is None else lift_pts


@dataclass(frozen=True)
class Declared:
    """The basis an edge document fixes (ADR 0065): ``[implementation] promoted`` (the screen)
    and ``[implementation] horizon`` (the holding period); None: not declared."""

    screener: str | None = None
    horizon: int | None = None


UNDECLARED: Final = Declared()


@dataclass(frozen=True)
class BasisChoice:
    """The basis ``(screen, holding period)`` the verdict rests on, or None with the ``reason``
    no basis can be fixed (the verdict is then Waiting on data); ``why``: for a basis chosen
    among several, the in-sample lifts it was chosen on, in words (empty: it was the only
    candidate or the document declared it)."""

    key: tuple[str, int] | None
    reason: str = ""
    why: str = ""


def _why(ranked: Sequence[tuple[tuple[str, int], tuple[int, float]]]) -> str:
    """The candidates' in-sample lifts, best ranked first: "chosen on in-sample lift: 15 d +3.1
    pts, 31 d +2.7 pts" (a candidate with no lift is left out)."""
    parts = [
        f"{k[1]} d {lift:+.1f} pts"
        for k, (_, lift) in sorted(ranked, key=lambda p: p[1], reverse=True)
        if lift != float("-inf")
    ]
    return f"chosen on in-sample lift: {', '.join(parts)}" if parts else ""


def _in_sample_rank(
    key: tuple[str, int], ins: EdgeRow, main: Sequence[EdgeRow], t: VerdictSettings, decoys: bool
) -> tuple[int, float]:
    """The verdict's ranking (level, then lift points) over the in-sample figures alone: the
    in-sample row stands for every period and the baselines are their in-sample rows; no
    random draws (they are out-of-sample), so the level is at most Promising for every one."""
    base = tuple(
        r
        for r in main
        if r.role == "baseline" and r.horizon_sessions == key[1] and r.slice_kind == runs.IN_SAMPLE
    )
    c = _Candidate(key[0], key[1], ins, ins, ins, base, ())
    level, _ = _level(c, _criteria(c, t, (), decoys), t)
    return ORDER.index(level), _rank(runs.lift_points(ins.hit_rate, ins.base_rate))


def choose_basis(
    rows: Sequence[EdgeRow],
    t: VerdictSettings,
    declared: Declared = UNDECLARED,
    decoys: bool = True,
) -> BasisChoice:
    """The basis of a result's ``rows`` (ADR 0065), read from the in-sample rows only (the
    candidates are named by their ``in_sample`` and ``all`` rows, whose figures are not read):
    the declared screen and horizon narrow the candidates; one left is the basis; of several,
    the best in-sample (ties: the first by screen, then horizon). A run from before the
    in-sample slice cannot rank several: no basis, Waiting on data. A model screener's in-sample
    row is its training fit and is never ranked."""
    main = [r for r in rows if r.edge_variant == runs.MAIN and not r.exploratory]
    named = {
        (r.variant, r.horizon_sessions)
        for r in main
        if r.role != "baseline" and r.slice_kind in (runs.IN_SAMPLE, ALL)
    }
    keys = sorted(
        k for k in named if declared.screener in (None, k[0]) and declared.horizon in (None, k[1])
    )
    if not keys:
        if declared.screener is None and declared.horizon is None:
            return BasisChoice(None, "The official result has no figures to rest a verdict on")
        wanted = f"{declared.screener or 'any screen'}, {declared.horizon or 'any'} trading days"
        return BasisChoice(
            None, f"The official result has no figures for the declared basis {wanted}"
        )
    if len(keys) == 1:
        return BasisChoice(keys[0])
    ins = {
        (r.variant, r.horizon_sessions): r
        for r in main
        if r.role != "baseline" and r.slice_kind == runs.IN_SAMPLE
    }
    # a model screener's in-sample row is its training fit (``in_sample``): never ranked, so a
    # model is the basis only when it is the one candidate left (``promoted``)
    fair = {k: r for k, r in ins.items() if not r.in_sample}
    ranked = [(k, _in_sample_rank(k, fair[k], main, t, decoys)) for k in keys if k in fair]
    if not ranked:
        if any(k in ins for k in keys):
            return BasisChoice(
                None, "Only a model screener's training fit is in-sample; it needs promoting"
            )
        return BasisChoice(
            None,
            "The official result predates the in-sample figures its basis is chosen on; "
            "it needs a new run",
        )
    best = max(ranked, key=lambda p: p[1])  # max keeps the first of equals: keys are sorted
    return BasisChoice(best[0], why=_why(ranked))


def _judge_candidate(
    c: _Candidate,
    t: VerdictSettings,
    draws: Sequence[EdgeRow],
    decoys: bool,
    lost_inputs: Sequence[str],
    facts: EdgeFacts,
) -> EdgeVerdict:
    """A candidate that lost inputs (its own screen could not read a table on some decision
    sessions) is Waiting on data even when it has rows: the figures are not the whole test."""
    lost = [x for x in lost_inputs if x.startswith(f"{runs.MAIN}/{c.variant}:")]
    if lost:
        reason = f"The result lost inputs for {c.variant}: {'; '.join(lost)}"
        return replace(_waiting("", reason), basis=_basis_words((c.variant, c.horizon)))
    return _judge_one(c, t, draws, decoys, facts)


def judge(
    edge_id: str,
    rows: Sequence[EdgeRow] | None,
    split: date | None,
    t: VerdictSettings,
    lost_inputs: Sequence[str] = (),
    draws: Sequence[EdgeRow] = (),
    decoys: bool = True,
    declared: Declared = UNDECLARED,
    basis: BasisChoice | None = None,
    facts: EdgeFacts | None = None,
    range_to: date | None = None,
) -> EdgeVerdict:
    """The verdict of ``edge_id`` from its official result's ``rows`` (None: it has no official
    result); ``split``: the out-of-sample start; ``draws``: the run's random-pick draws (none:
    not measured, which caps the verdict at Promising); ``declared``: the document's basis;
    ``basis``: one already chosen (a hidden copy's, from rows the verdict does not see), else
    ``choose_basis`` over ``rows``; ``facts``: the edge's
    published figure, schedule and whether its out-of-sample result is hidden; ``range_to``: the
    run's last session (the out-of-sample year part ends there)."""
    if rows is None:
        return _waiting(edge_id, "No official result yet")
    found = _candidates(rows)
    if found and all(c.oos.side == "long_short" for c in found):
        return _diagnostic(edge_id)  # never a verdict basis
    choice = basis if basis is not None else choose_basis(rows, t, declared, decoys)
    if choice.key is None:
        lost = f": {'; '.join(lost_inputs)}" if lost_inputs and not found else ""
        return _waiting(edge_id, f"{choice.reason}{lost}")
    on = _basis_words(choice.key)
    c = next((x for x in found if (x.variant, x.horizon) == choice.key), None)
    if c is None:
        lost = f": {'; '.join(lost_inputs)}" if lost_inputs else ""
        reason = f"The official result has no out-of-sample figures for {on}{lost}"
        return replace(_waiting(edge_id, reason), basis=on)
    judged = _judge_candidate(c, t, draws, decoys, lost_inputs, facts or EdgeFacts())
    return replace(judged, edge_id=edge_id, years=_years(c, split, range_to), basis_why=choice.why)


def load_edge_verdict(ctx: Stores, edge: Edge) -> EdgeVerdict:
    """The verdict of ``edge`` from its canonical run's stored rows. Like ``canonicalRun`` it
    ignores ``after_session`` (ADR 0036: runs are read by run, not by session)."""
    settings = load_verdict(ctx.configs)
    run = runs.load_canonical_run(ctx, edge).run
    if run is None:
        return judge(edge.id, None, edge.frozen_from, settings)
    rows = runs.load_run_rows(ctx, run)
    return judge(
        edge.id,
        rows,
        run.split_from or edge.frozen_from,  # the split its year parts were cut at
        settings,
        run.lost_inputs,
        draws=runs.load_run_draws(ctx, run),
        decoys=bool(edge.baselines),
        declared=Declared(edge.promoted, edge.basis_horizon),
        facts=EdgeFacts(
            edge.published,
            edge.schedule,
            after=run.range_to,
            measured=lambda: runs.load_measured_sessions(ctx, run),
            wins=counts_wins(edge),
            site_trials=None if edge.mine else lambda: runs.load_site_trials(ctx),
        ),
        range_to=run.range_to,
    )
