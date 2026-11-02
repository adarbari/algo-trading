"""The verdict profile (ADR 0088, design 2.6, risk 16): ``return`` is the criteria of every edge
today and no stored figure of the new evidence columns can move it; ``tails`` swaps the decile t's
slot for the bootstrap t of the return on capital and adds the PSR and the CVaR ratio."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from algotrade.config.edges.verdict import TailsVerdict, VerdictSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.verdict import (
    NOT_ENOUGH,
    NOT_WORKING,
    PROMISING,
    WORKS,
    EdgeFacts,
    EdgeVerdict,
    choose_basis,
    judge,
)
from tests.unit.services.read.evaluation.verdict.test_rule import (
    BOOK,
    SPLIT,
    T,
    book_result,
    draws,
    grid,
    result,
)

STRONG_OOS = {"decile_t": 3.0, "decile_spread": 0.9}
STRONG_WHOLE = {"sessions": 100, "deflated_sharpe": 0.95, "pbo": 0.2}
EXTREME = {
    "excess_roc_t": 99.0,
    "psr": 0.9999,
    "cvar_5": -0.5,
    "cvar_5_n": 500,
    "base_cvar_5": -0.001,
}
NOWHERE = {
    "excess_roc_t": -9.0,
    "psr": 0.0001,
    "cvar_5": -0.9,
    "cvar_5_n": 500,
    "base_cvar_5": -0.001,
}

SCENARIOS: dict[str, Callable[[], tuple[list[EdgeRow], dict[str, object]]]] = {
    "works": lambda: (result(oos=STRONG_OOS, whole=STRONG_WHOLE), {"draws": draws(100)}),
    "capped by missing draws": lambda: (result(oos=STRONG_OOS, whole=STRONG_WHOLE), {}),
    "promising": lambda: (result(), {}),
    "not enough": lambda: (result(oos={"sessions": 39}), {}),
    "weak t": lambda: (result(oos={"decile_t": 0.5}), {}),
    "weak dsr": lambda: (result(whole={"deflated_sharpe": 0.3}), {}),
    "no decoys": lambda: (result(baselines=()), {"decoys": False}),
    "a book": lambda: (book_result(oos={"picks_t": 3.2}), {"facts": BOOK}),
}


def _with(rows: list[EdgeRow], **columns: object) -> list[EdgeRow]:
    return [replace(r, **columns) for r in rows]  # type: ignore[arg-type]


def _judge(rows: list[EdgeRow], profile: str | None, **kw: object) -> EdgeVerdict:
    facts = kw.pop("facts", EdgeFacts())
    if profile is not None:
        facts = replace(facts, profile=profile)  # type: ignore[type-var]
    return judge("e", rows, SPLIT, T, facts=facts, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_return_profile_is_the_default_judge_whole_verdict(name: str) -> None:
    rows, kw = SCENARIOS[name]()
    assert _judge(rows, "return", **kw) == _judge(rows, None, **kw)


@pytest.mark.parametrize("columns", [EXTREME, NOWHERE])
@pytest.mark.parametrize("name", SCENARIOS)
def test_no_evidence_column_can_move_a_return_verdict(
    name: str, columns: dict[str, object]
) -> None:
    """The new columns are read by ``tails`` only: filling them with extreme figures changes no
    label, no result line and no criterion of a ``return`` judge (the whole verdict is equal)."""
    rows, kw = SCENARIOS[name]()
    assert _judge(_with(rows, **columns), "return", **kw) == _judge(rows, "return", **kw)


def _tails(rows: list[EdgeRow], **kw: object) -> EdgeVerdict:
    return _judge(rows, "tails", **kw)


def _crit(v: EdgeVerdict, id: str):  # type: ignore[no-untyped-def]
    return next(c for c in v.criteria if c.id == id)


GOOD = {"excess_roc_t": 3.2, "psr": 0.97, "cvar_5": -0.10, "cvar_5_n": 8, "base_cvar_5": -0.10}


def _strong(**oos: object) -> list[EdgeRow]:
    return result(oos={**STRONG_OOS, **GOOD, **oos}, whole=STRONG_WHOLE)


def test_tails_reads_the_bootstrap_t_in_the_decile_ts_slot() -> None:
    rows = _strong(decile_t=-5.0)  # a decile t that would fail the return profile outright
    assert _judge(rows, "return", draws=draws(100)).verdict == NOT_WORKING
    v = _tails(rows, draws=draws(100))
    assert v.verdict == WORKS
    for id, bound in (("decile_t", "2"), ("works_t", "3")):
        crit = _crit(v, id)
        assert crit.label == "Return on capital vs base, block bootstrap t"
        assert (crit.value, crit.threshold, crit.status) == ("3.20", f"at least {bound}", "pass")
    assert _crit(_judge(rows, "return"), "decile_t").label == "Top vs bottom decile t"


@pytest.mark.parametrize(
    ("t", "verdict"),
    [(2.0, PROMISING), (1.99, NOT_WORKING), (0.9, NOT_WORKING), (None, NOT_ENOUGH)],
)
def test_the_bootstrap_t_has_the_decile_ts_bounds_and_its_not_working_floor(
    t: float | None, verdict: str
) -> None:
    v = _tails(_strong(excess_roc_t=t))
    assert v.verdict == verdict
    if t is None:
        assert _crit(v, "decile_t").status == "not_measured"  # not measured: never a pass


def test_psr_has_a_promising_and_a_works_bound_and_none_is_not_measured() -> None:
    p = lambda psr: _tails(_strong(psr=psr), draws=draws(100))  # noqa: E731
    assert p(0.95).verdict == WORKS
    mid = p(0.92)  # at least 0.90 but under 0.95
    assert mid.verdict == PROMISING and _crit(mid, "psr").status == "pass"
    assert _crit(mid, "works_psr").status == "fail"
    low = p(0.89)
    assert low.verdict == NOT_WORKING and _crit(low, "psr").status == "fail"
    gone = p(None)
    assert (_crit(gone, "psr").status, _crit(gone, "works_psr").status) == (
        "not_measured", "not_measured",
    )  # fmt: skip
    assert gone.verdict == NOT_ENOUGH


@pytest.mark.parametrize(
    ("cvar", "n", "base", "status"),
    [
        (-0.125, 8, -0.10, "pass"),  # exactly 1.25x
        (-0.126, 8, -0.10, "fail"),
        (-0.10, 5, -0.10, "pass"),  # exactly min_tail_windows
        (-0.10, 4, -0.10, "not_measured"),  # too few windows in the tail
        (None, 8, -0.10, "not_measured"),
        (-0.10, 8, None, "not_measured"),
        (-0.10, None, -0.10, "not_measured"),
        (-0.10, 8, 0.0, "not_measured"),  # the base has no loss tail: never a pass
        (-0.10, 8, 0.02, "not_measured"),
    ],
)
def test_the_cvar_ratio_passes_fails_or_is_not_measured(
    cvar: float | None, n: int | None, base: float | None, status: str
) -> None:
    v = _tails(_strong(cvar_5=cvar, cvar_5_n=n, base_cvar_5=base))
    crit = _crit(v, "cvar_ratio")
    assert crit.status == status and crit.level == PROMISING
    assert (status == "pass") == (v.verdict in (PROMISING, WORKS))
    if base is not None and base >= 0:
        assert crit.value == "the base has no loss tail"


def test_a_failed_cvar_ratio_is_not_working_and_is_named() -> None:
    v = _tails(_strong(cvar_5=-0.5))
    assert v.verdict == NOT_WORKING and "5%" in v.rationale


def test_the_tails_bounds_come_from_the_settings() -> None:
    loose = VerdictSettings(
        tails=TailsVerdict(max_cvar_ratio=5.0, min_tail_windows=2, works_psr=0.99)
    )
    rows = _strong(cvar_5=-0.4, cvar_5_n=2, psr=0.97)
    v = judge("e", rows, SPLIT, loose, facts=EdgeFacts(profile="tails"), draws=draws(100))
    assert _crit(v, "cvar_ratio").status == "pass" and _crit(v, "works_psr").status == "fail"
    assert v.verdict == PROMISING


def test_the_shared_criteria_stay_shared_under_tails() -> None:
    rows = _strong()
    ids = lambda profile: [c.id for c in _judge(rows, profile).criteria]  # noqa: E731
    shared = ids("return")
    assert [i for i in ids("tails") if i not in ("psr", "cvar_ratio", "works_psr")] == shared
    for id in ("trades", "dsr", "pbo", "works_dsr", "works_trades", "works_picks_t", "random"):
        assert _crit(_judge(rows, "tails"), id) == _crit(_judge(rows, "return"), id)


def test_a_tails_basis_is_ranked_on_the_t_it_is_judged_on() -> None:
    """The basis choice passed no profile on, so a ``tails`` edge picked its horizon by the decile
    t and was judged on the bootstrap t. 15 d has the better lift but a failing bootstrap t."""
    rows = grid({15: 0.55, 21: 0.52}, {15: 0.55, 21: 0.52})
    bad = {"excess_roc_t": -9.0, "psr": 0.5, "cvar_5": -0.1, "cvar_5_n": 8, "base_cvar_5": -0.1}
    rows = [
        replace(r, **(bad if r.horizon_sessions == 15 else GOOD))  # type: ignore[arg-type]
        if r.slice_kind == "in_sample" and r.role != "baseline"
        else r
        for r in rows
    ]
    assert choose_basis(rows, T).key == ("vrp", 15)  # return: by lift, as before
    assert choose_basis(rows, T, profile="return") == choose_basis(rows, T)
    assert choose_basis(rows, T, profile="tails").key == ("vrp", 21)


@pytest.mark.parametrize("level", ["mid", "effective"])
def test_a_tails_judge_refuses_an_option_cost_level_it_does_not_read(level: str) -> None:
    """``option_cost_level`` was accepted and ignored: a ``mid`` setting judged at ``full``."""
    settings = replace(T, tails=replace(T.tails, option_cost_level=level))
    facts = EdgeFacts(profile="tails")
    with pytest.raises(ConfigurationError, match="judged at 'full' only"):
        judge("e", _strong(), SPLIT, settings, facts=facts)
    judge("e", _strong(), SPLIT, settings)  # the return profile never reads it
