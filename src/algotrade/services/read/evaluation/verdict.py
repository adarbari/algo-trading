"""An edge's verdict (``EdgeVerdict``, ED8): Works, Promising, Not working, Not enough data or
Waiting on data, judged on its official result (the canonical run) by one deterministic rule.

The candidates are the main edge variant's implementation rows (role not ``baseline``), each
(screen, holding period) with its out-of-sample (``frozen``) and whole-history (``all``) rows;
the edge's verdict is its best candidate's, and names the screen and holding period it rests on.
First match wins: Waiting on data (no official result, or no candidate rows); Not enough data
(fewer out-of-sample trades than ``min_oos_trades``, or a criterion that is not measured);
Not working (a hard failure: out-of-sample win rate not above the base rate, t, overfitting
probability, deflated Sharpe, or worse than the median baseline; then any criterion of
Promising missed); Promising;
Works (more trades, stricter thresholds, and an out-of-sample lift above at least
``random_beat_share`` of the random-pick backtest's draws, ``quant.edge_statistics.percentile_of``;
a run with no draws is "not measured" and caps the verdict at Promising). The statistics are
the stored rows' (``quant/edge_statistics.py``), never recomputed; the thresholds are site data
(``config/site/verdict.toml``); the sentences are the server's, the browser words nothing."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Final

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import load_verdict
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.robustness import Robustness, beat_share, load_robustness
from algotrade.services.read.evaluation.runs import EdgeRow

WORKS: Final = "works"
PROMISING: Final = "promising"
NOT_WORKING: Final = "not_working"
NOT_ENOUGH: Final = "not_enough_data"
WAITING: Final = "waiting_on_data"
ORDER: Final = (WAITING, NOT_ENOUGH, NOT_WORKING, PROMISING, WORKS)  # worst to best
PASS, FAIL, NOT_MEASURED = "pass", "fail", "not_measured"
IN_SAMPLE, OUT_OF_SAMPLE, BOTH = "in_sample", "out_of_sample", "both"


@dataclass(frozen=True)
class VerdictCriterion:
    """One test of the verdict: what was measured, what it must reach and whether it did
    (``status``: ``pass``, ``fail`` or ``not_measured``); ``level``: the verdict it gates."""

    id: str
    label: str
    value: str
    threshold: str
    status: str
    level: str


@dataclass(frozen=True)
class YearRow:
    """One calendar year of the basis (screen, holding period); ``period``: ``in_sample``,
    ``out_of_sample`` or ``both`` (the split falls inside the year)."""

    year: str
    period: str
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


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _num(x: float | None, digits: int = 2) -> str:
    return "not stored" if x is None else f"{x:.{digits}f}"


def _crit(
    id: str, label: str, value: str, threshold: str, ok: bool | None, level: str
) -> VerdictCriterion:
    status = NOT_MEASURED if ok is None else PASS if ok else FAIL
    return VerdictCriterion(id, label, value, threshold, status, level)


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
        found.append(
            _Candidate(
                variant,
                horizon,
                oos[0],
                whole[0],
                before[0] if len(before) == 1 else None,
                base,
                years,
            )
        )
    return found


def _first(crit: Sequence[VerdictCriterion], level: str) -> VerdictCriterion | None:
    return next((x for x in crit if x.level == level and x.status != PASS), None)


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


def _criteria(
    c: _Candidate, t: VerdictSettings, draws: Sequence[EdgeRow], decoys: bool
) -> tuple[VerdictCriterion, ...]:
    oos, whole = c.oos, c.whole
    trades = whole.sessions
    oos_pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    in_pts = runs.lift_points(c.insample.hit_rate, c.insample.base_rate) if c.insample else None
    pbo = whole.pbo if whole.pbo is not None else oos.pbo
    dsr = whole.deflated_sharpe if whole.deflated_sharpe is not None else oos.deflated_sharpe
    lifts = [b.lift for b in c.baselines if b.lift is not None]
    spreads = [b.decile_spread for b in c.baselines if b.decile_spread is not None]
    beats_all = (
        True if not decoys else None if oos.lift is None or not lifts else oos.lift > max(lifts)
    )
    beats_spread = (
        True
        if not decoys
        else None
        if oos.decile_spread is None or not spreads
        else oos.decile_spread > max(spreads)
    )
    keeps = None if oos_pts is None or in_pts is None else oos_pts >= t.oos_lift_share * in_pts
    win_ok = None if oos_pts is None else oos_pts > 0
    enough = (
        None
        if trades is None or oos.sessions is None
        else trades >= t.works_trades and oos.sessions >= t.works_oos_trades
    )
    versus = f"{_pct(oos.hit_rate)} against {_pct(oos.base_rate)}"
    random_value, random_beaten = _random(c, t, draws)
    best = (
        "no decoys declared"
        if not decoys
        else f"{_num(oos.lift)} vs best {_num(max(lifts))}"
        if lifts
        else "not stored"
    )
    return (
        _crit("trades", "Out-of-sample trades", str(oos.sessions), f"at least {t.min_oos_trades}",
              None if oos.sessions is None else oos.sessions >= t.min_oos_trades, PROMISING),
        _crit("win_rate", "Out-of-sample win rate above the base rate", versus,
              "above the base rate", win_ok, PROMISING),
        _crit("decile_t", "Top vs bottom decile t", _num(oos.decile_t),
              f"at least {t.promising_t:g}", _at_least(oos.decile_t, t.promising_t), PROMISING),
        _crit("pbo", "Chance the result is overfitting", _num(pbo),
              f"at most {t.max_pbo:g}", _at_most(pbo, t.max_pbo), PROMISING),
        _crit("dsr", "Deflated Sharpe", _num(dsr), f"at least {t.promising_dsr:g}",
              _at_least(dsr, t.promising_dsr), PROMISING),
        _crit("baselines", "Lift against every baseline", best,
              "beats every baseline", beats_all, PROMISING),
        _crit("oos_lift", "Out-of-sample lift keeps its size",
              f"{_num(oos_pts, 1)} pts vs {_num(in_pts, 1)} pts in-sample",
              f"at least {t.oos_lift_share:g} of the in-sample lift", keeps, PROMISING),
        _crit("works_trades", "Trades, and out-of-sample trades", f"{trades} and {oos.sessions}",
              f"at least {t.works_trades} and {t.works_oos_trades}", enough, WORKS),
        _crit("works_t", "Top vs bottom decile t", _num(oos.decile_t),
              f"at least {t.works_t:g}", _at_least(oos.decile_t, t.works_t), WORKS),
        _crit("works_dsr", "Deflated Sharpe", _num(dsr), f"at least {t.works_dsr:g}",
              _at_least(dsr, t.works_dsr), WORKS),
        _crit("works_pbo", "Chance the result is overfitting", _num(pbo),
              f"at most {t.works_max_pbo:g}", _at_most(pbo, t.works_max_pbo), WORKS),
        _crit("works_spread", "Decile spread against every baseline",
              _num(oos.decile_spread, 3),
              "no decoys declared" if not decoys else "beats every baseline",
              beats_spread, WORKS),
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


def _judge_one(
    c: _Candidate, t: VerdictSettings, draws: Sequence[EdgeRow], decoys: bool
) -> EdgeVerdict:
    crit = _criteria(c, t, draws, decoys)
    level, reason = _level(c, crit, t)
    oos, whole = c.oos, c.whole
    pts = runs.lift_points(oos.hit_rate, oos.base_rate)
    basis = f"{c.variant}, {c.horizon} trading days"
    body = (
        f"Out-of-sample, {basis}: win rate {_pct(oos.hit_rate)} against a base rate of "
        f"{_pct(oos.base_rate)} ({_num(pts, 0)} pts)."
    )
    shown = level in (WORKS, PROMISING, NOT_WORKING)
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
        trades=whole.sessions,
        oos_trades=oos.sessions,
        win_rate=oos.hit_rate,
        base_rate=oos.base_rate,
        lift_pts=pts,
        lift=oos.lift,
        decile_spread=oos.decile_spread,
        decile_t=oos.decile_t,
        sharpe=whole.sharpe,
        deflated_sharpe=whole.deflated_sharpe
        if whole.deflated_sharpe is not None
        else oos.deflated_sharpe,
        pbo=whole.pbo if whole.pbo is not None else oos.pbo,
        trials=whole.trials,
        deciles=c.insample.decile_means if c.insample else (),
        robustness=load_robustness(oos.lift, draws, c.horizon, c.variant, whole.trials),
    )


def _period(year: str, split: date | None) -> str:
    if split is None or not year.isdigit():
        return IN_SAMPLE
    first, last = date(int(year), 1, 1), date(int(year), 12, 31)
    return IN_SAMPLE if last < split else OUT_OF_SAMPLE if first >= split else BOTH


def _years(c: _Candidate, split: date | None) -> tuple[YearRow, ...]:
    return tuple(
        YearRow(
            r.slice_value, _period(r.slice_value, split), r.hit_rate, r.base_rate,
            runs.lift_points(r.hit_rate, r.base_rate), r.decile_spread, r.sessions,
        )
        for r in c.years
    )  # fmt: skip


def _waiting(edge_id: str, reason: str) -> EdgeVerdict:
    return EdgeVerdict(edge_id, WAITING, reason, reason, reason)


def _rank(lift_pts: float | None) -> float:
    return float("-inf") if lift_pts is None else lift_pts


def _judge_candidate(
    c: _Candidate,
    t: VerdictSettings,
    draws: Sequence[EdgeRow],
    decoys: bool,
    lost_inputs: Sequence[str],
) -> EdgeVerdict:
    """A candidate that lost inputs (its own screen could not read a table on some decision
    sessions) is Waiting on data even when it has rows: the figures are not the whole test."""
    lost = [x for x in lost_inputs if x.startswith(f"{runs.MAIN}/{c.variant}:")]
    if lost:
        reason = f"The result lost inputs for {c.variant}: {'; '.join(lost)}"
        return replace(_waiting("", reason), basis=f"{c.variant}, {c.horizon} trading days")
    return _judge_one(c, t, draws, decoys)


def judge(
    edge_id: str,
    rows: Sequence[EdgeRow] | None,
    split: date | None,
    t: VerdictSettings,
    lost_inputs: Sequence[str] = (),
    draws: Sequence[EdgeRow] = (),
    decoys: bool = True,
) -> EdgeVerdict:
    """The verdict of ``edge_id`` from its official result's ``rows`` (None: it has no official
    result); ``split``: the out-of-sample start; ``draws``: the run's random-pick draws (none:
    not measured, which caps the verdict at Promising)."""
    if rows is None:
        return _waiting(edge_id, "No official result yet")
    found = _candidates(rows)
    if not found:
        lost = f": {'; '.join(lost_inputs)}" if lost_inputs else ""
        return _waiting(edge_id, f"The official result has no out-of-sample figures{lost}")
    judged = [(c, _judge_candidate(c, t, draws, decoys, lost_inputs)) for c in found]
    best_c, best = max(judged, key=lambda p: (ORDER.index(p[1].verdict), _rank(p[1].lift_pts)))
    return replace(best, edge_id=edge_id, years=_years(best_c, split))


def load_edge_verdict(ctx: Stores, edge: Edge) -> EdgeVerdict:
    """The verdict of ``edge`` from its canonical run's stored rows. Like ``canonicalRun`` it
    ignores ``after_session`` (ADR 0036: runs are read by run, not by session)."""
    settings = load_verdict(ctx.configs)
    found = runs.load_canonical_run(ctx, edge)
    if found.run is None:
        return judge(edge.id, None, edge.frozen_from, settings)
    rows = runs.load_run_rows(ctx, found.run)
    return judge(
        edge.id,
        rows,
        edge.frozen_from,
        settings,
        found.run.lost_inputs,
        draws=runs.load_run_draws(ctx, found.run),
        decoys=bool(edge.baselines),
    )
