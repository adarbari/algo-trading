"""A candidate's level and columns from its criteria, and the words of its basis (ED8)."""

import statistics
from collections.abc import Sequence

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.verdict.criteria import (
    TAILS,
    _first,
    _words,
)
from algotrade.services.read.evaluation.verdict.model import (
    ALL,
    FAIL,
    IN_SAMPLE,
    NOT_ENOUGH,
    NOT_WORKING,
    OUT_OF_SAMPLE,
    PROMISING,
    WORKS,
    VerdictColumn,
    VerdictCriterion,
    _Candidate,
)


def _level(
    c: _Candidate, crit: Sequence[VerdictCriterion], t: VerdictSettings, profile: str = "return"
) -> tuple[str, str]:
    """The level and its reason from ``crit``. ``profile``: the decile t's slot holds the
    bootstrap t of the return on capital under ``tails`` (``criteria._tails_criteria``), and the
    Not-working floor reads that t, the one the criterion shows."""
    oos, whole = c.oos, c.whole
    slot_t = oos.excess_roc_t if profile == TAILS else oos.decile_t
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
        (slot_t is not None and slot_t < t.not_working_t, "decile_t"),
        (  # a portfolio book's picks-series t, as the decile t is for a ranking
            "promising_picks_t" in by and oos.picks_t is not None and oos.picks_t < t.not_working_t,
            "promising_picks_t",
        ),
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
