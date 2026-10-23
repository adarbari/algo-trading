"""The verdict's criteria: each test of Promising and Works over one candidate, with its measured
value and bound (ED8)."""

from collections.abc import Sequence
from dataclasses import replace

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.robustness import (
    beat_share,
)
from algotrade.services.read.evaluation.runs import Draws
from algotrade.services.read.evaluation.verdict.model import (
    NO_DECOYS,
    NOT_APPLICABLE,
    NOT_MEASURED,
    PASS,
    PROMISING,
    WORKS,
    VerdictCriterion,
    _at_least,
    _at_most,
    _Candidate,
    _crit,
    _not_applicable,
    _num,
    _pct,
)


def _first(crit: Sequence[VerdictCriterion], level: str) -> VerdictCriterion | None:
    return next(
        (x for x in crit if x.level == level and x.status not in (PASS, NOT_APPLICABLE)), None
    )


def _words(x: VerdictCriterion) -> str:
    if x.status == NOT_MEASURED:
        return f"{x.label} is not measured yet"
    return f"{x.label} is {x.value}; it needs {x.threshold}"


def _random(c: _Candidate, t: VerdictSettings, draws: Draws) -> tuple[str, bool | None]:
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


NO_INSAMPLE = "no in-sample history: chains are stored from 2026-10-02"


PORTFOLIO_BASE = "a book is read against its benchmark, not a base rate"  # a criterion's value
NO_NAMES = "needs about 20 ranked names"  # the value of a decile criterion with no deciles


def _portfolio_criteria(
    crit: Sequence[VerdictCriterion], c: _Candidate, t: VerdictSettings
) -> tuple[VerdictCriterion, ...]:
    """The criteria of a ``portfolio_return`` edge (ADR 0074): the value is the book's excess return
    over a blended benchmark, so the win rate, the lift and the random picks (a base rate over
    names, a name drawn at random) do not apply, the decoys are compared on the mean excess return
    of their own books, and the picks-series t is Promising's test as well as Works's. The decile
    criteria stand when the screen ranked enough names (about 20) to have deciles, else they do not
    apply (served N/A): then the picks-series t is the one t Works needs."""
    oos = c.oos
    others = [b.mean_excess_picks for b in c.baselines if b.mean_excess_picks is not None]
    beats = _beats(oos.mean_excess_picks, others, len(c.baselines))
    none = oos.decile_t is None
    out = []
    for x in crit:
        if x.id in ("win_rate", "oos_lift", "random") or (none and x.id.endswith("decile_t")):
            value = NO_NAMES if x.id.endswith("decile_t") else PORTFOLIO_BASE
            out.append(replace(x, value=value, status=NOT_APPLICABLE))
        elif x.id in ("works_t", "works_spread") and none:
            out.append(replace(x, value=NO_NAMES, status=NOT_APPLICABLE))
        elif x.id == "baselines" and x.status != NOT_APPLICABLE:
            best = (
                f"{_pct(oos.mean_excess_picks)} vs best {_pct(max(others))}"
                if others
                else ("not stored")
            )
            out.append(
                _crit("baselines", "Mean excess return against every baseline", best,
                      "beats every baseline", beats, PROMISING)
            )  # fmt: skip
        else:
            out.append(x)
    at = out.index(next(x for x in out if x.id == "dsr"))
    out.insert(
        at,
        _crit("promising_picks_t", "Picks-series t (Sharpe ratio's t-ratio)", _num(oos.picks_t),
              f"at least {t.promising_t:g}", _at_least(oos.picks_t, t.promising_t), PROMISING),
    )  # fmt: skip
    return tuple(out)


def _criteria(
    c: _Candidate,
    t: VerdictSettings,
    draws: Draws,
    decoys: bool,
    portfolio: bool = False,
) -> tuple[VerdictCriterion, ...]:
    found = _all_criteria(c, t, draws, decoys)
    return _portfolio_criteria(found, c, t) if portfolio else found


def _all_criteria(
    c: _Candidate, t: VerdictSettings, draws: Draws, decoys: bool
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
    lift_label = "Out-of-sample lift keeps its size"
    lift_need = f"at least {t.oos_lift_share:g} of the in-sample lift"
    lift_crit = (
        _not_applicable("oos_lift", lift_label, NO_INSAMPLE, lift_need, PROMISING)
        if c.chain  # no in-sample lift exists to keep: Promising stays reachable
        else _crit("oos_lift", lift_label,
                   f"{_num(oos_pts, 1)} pts vs {_num(in_pts, 1)} pts in-sample",
                   lift_need, keeps, PROMISING)
    )  # fmt: skip
    win_ok = None if oos_pts is None else oos_pts > 0
    enough = (
        None
        if trades is None or oos.sessions is None
        else trades >= t.works_trades and oos.sessions >= t.works_oos_trades
    )
    t_label = "In-window minus out-of-window t (Welch)" if c.timed else "Top vs bottom decile t"
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
        _crit("decile_t", t_label, _num(oos.decile_t),
              f"at least {t.promising_t:g}", _at_least(oos.decile_t, t.promising_t), PROMISING),
        _overfit("pbo", pbo, t.max_pbo, PROMISING, alone),
        _crit("dsr", "Deflated Sharpe", _num(dsr), f"at least {t.promising_dsr:g}",
              _at_least(dsr, t.promising_dsr), PROMISING),
        against_all,
        lift_crit,
        _crit("works_trades", "Trades, and out-of-sample trades", f"{trades} and {oos.sessions}",
              f"at least {t.works_trades} and {t.works_oos_trades}", enough, WORKS),
        _crit("works_t", t_label, _num(oos.decile_t),
              f"at least {t.works_t:g}", _at_least(oos.decile_t, t.works_t), WORKS),
        _crit("works_picks_t", "Picks-series t (Sharpe ratio's t-ratio)", _num(oos.picks_t),
              f"at least {t.works_picks_t:g}", _at_least(oos.picks_t, t.works_picks_t), WORKS),
        _crit("works_dsr", "Deflated Sharpe", _num(dsr), f"at least {t.works_dsr:g}",
              _at_least(dsr, t.works_dsr), WORKS),
        _overfit("works_pbo", pbo, t.works_max_pbo, WORKS, alone),
        spread_all,
        _crit("random", "Beats random picks", random_value,
              f"beats at least {_pct(t.random_beat_share)} of them", random_beaten, WORKS),
        # a chain edge's basis was declared at filing: this Works criterion stays unmet (ADR 0065)
        *([_crit("basis_in_sample", "Basis fixed on an in-sample period",
                 "declared at filing: no in-sample period exists",
                 "an in-sample period before the frozen split", False, WORKS)] * c.chain),
    )  # fmt: skip
