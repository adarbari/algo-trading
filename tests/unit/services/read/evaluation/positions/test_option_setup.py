"""The option setup page's read object (ADR 0088, plan O1): the declared rules as structured
values, the evidence on collateral by hand (typical trade and quartiles, bad trade, kept the
premium, by year, stress), a share setup with no option section, and every UNKNOWN case: no
trade, no verdict basis, a licensed or unstored return, a run ending after the session."""

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.edges.positions.templates import KIND, NAME
from algotrade.services.read.evaluation.positions import option_evidence as evidence_module
from algotrade.services.read.evaluation.positions.option_setup import (
    OPTIONS,
    SHARES,
    load_option_setup,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import DOCS, EDGE, END, session_ctx, stores
from tests.unit.services.read.evaluation.positions.test_exit_rule import SETTINGS, trade
from tests.unit.services.read.evaluation.positions.test_exit_rule import world as share_world
from tests.unit.services.read.evaluation.positions.test_exit_rule_option import (
    OPTION,
    TEMPLATES,
)
from tests.unit.services.read.evaluation.positions.test_exit_rule_option import (
    world as option_world,
)

# twenty trades: the two worst in 2025, then 1% .. 18%; sorted: -0.20, -0.10, 0.01 .. 0.18
RETURNS = [-0.20, -0.10, *[round(0.01 * k, 2) for k in range(1, 19)]]


def option_trade(i: int, roc: float | None, **changes: Any) -> dict[str, Any]:
    row = trade(
        i, None, return_on_capital=roc, capital_basis="cash_secured", exit_kind="horizon",
        status="won" if roc is not None and roc > 0 else "lost", hit=roc is not None and roc > 0,
    )  # fmt: skip
    if i < 2:  # the two worst trades are of 2025
        day = date(2025, 11, 3) + timedelta(days=i)
        row |= {"decision_session": day, "entry_session": day + timedelta(days=1),
                "exit_session": day + timedelta(days=29)}  # fmt: skip
    return row | changes


LEDGER = [option_trade(i, r) for i, r in enumerate(RETURNS)]


AFTER = date(2026, 10, 5)  # a session after the run was committed (the read is bounded to it)


def setup(trades: list[dict[str, Any]] | None = None, day: date = AFTER, **outcome: Any) -> Any:
    ctx, _ = option_world(LEDGER if trades is None else trades, day, **outcome)
    found = load_option_setup(ctx, "drift")
    assert found is not None
    return found


def test_the_rules_are_the_documents_declared_position_as_structured_values() -> None:
    found = setup(exit={"stop_loss": 2.0, "take_profit": 0.5, "exit_dte": 21})
    rules = found.rules
    assert found.position_kind == OPTIONS and found.rules_unknown is None
    assert rules is not None and rules.template == "short_put"
    assert [(x.kind, x.qty, x.right, x.strike, x.delta) for x in rules.legs] == [
        ("option", -1, "P", "delta", 0.25)
    ]
    assert (rules.collateral, rules.tenor_days, rules.start_offset_sessions) == (
        "cash_secured", 30, 1,
    )  # fmt: skip
    assert (rules.take_profit, rules.stop_loss, rules.exit_dte) == (0.5, 2.0, 21)
    assert rules.schedule == "every_session" and rules.case_valued == ()


def test_the_typical_bad_and_kept_figures_by_hand() -> None:
    ev = setup().evidence
    assert ev is not None and ev.unknown is None
    assert (ev.basis_screener, ev.basis_horizon, ev.trades) == ("momo", 20, 20)
    # the median of the 10th and 11th sorted values, numpy's linear quartiles
    assert ev.typical == pytest.approx(0.085)
    assert (ev.typical_lo, ev.typical_hi) == (pytest.approx(0.0375), pytest.approx(0.1325))
    assert (ev.bad_mean, ev.bad_trades) == (pytest.approx(-0.20), 1)  # the worst 5% of 20: one
    assert ev.kept == 18  # every trade above zero but the two losses


def test_a_trade_at_zero_did_not_keep_the_premium() -> None:
    ev = setup([option_trade(0, 0.0), option_trade(1, 0.05)]).evidence
    assert ev is not None and (ev.trades, ev.kept) == (2, 1)


def test_by_year_groups_the_decision_sessions() -> None:
    ev = setup().evidence
    assert ev is not None
    by = {y.year: y for y in ev.by_year}
    assert (by[2025].trades, by[2025].typical, by[2025].kept) == (2, pytest.approx(-0.15), 0)
    assert (by[2026].trades, by[2026].kept) == (18, 18)
    assert by[2026].typical == pytest.approx(0.095)  # the median of 0.01 .. 0.18
    assert [y.year for y in ev.by_year] == [2025, 2026]


def test_the_costs_are_the_stored_levels_not_recomputed() -> None:
    ev = setup().evidence
    assert ev is not None and ev.costs is not None
    assert ev.costs.levels == ()  # this run stored no cost row: never a recomputed level
    assert ev.costs.state in ("not_stored", "not_a_cost_outcome")


def test_the_stress_windows_hold_the_worst_trade_open_in_each_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def episode(key: str, peak: date, trough: date) -> Any:
        return SimpleNamespace(key=key, name=key.title(), peak=peak, trough=trough)

    found = (
        episode("fall25", date(2025, 11, 1), date(2025, 11, 20)),  # the two 2025 trades are open
        episode("calm", date(2024, 1, 2), date(2024, 2, 1)),  # none was open
    )
    monkeypatch.setattr(
        evidence_module, "load_regime_episodes", lambda ctx: SimpleNamespace(episodes=found)
    )
    ev = setup().evidence
    assert ev is not None and ev.stress_unknown is None
    fall, calm = ev.stress
    assert (fall.trades, fall.worst) == (2, pytest.approx(-0.20))
    assert (calm.trades, calm.worst) == (0, None)  # nothing open: no worst, not a zero


def test_no_known_episode_is_a_reason_not_an_empty_win() -> None:
    ev = setup().evidence
    assert ev is not None and ev.stress == ()
    assert ev.stress_unknown is not None and ev.stress_unknown.code is UnknownCode.NO_ROW


def test_a_share_setup_has_no_option_section() -> None:
    ctx, _ = share_world(None)
    found = load_option_setup(ctx, "drift")
    assert found is not None and found.position_kind == SHARES
    assert found.rules is None and found.evidence is None
    assert found.rules_unknown is not None
    assert found.rules_unknown.code is UnknownCode.NOT_APPLICABLE


def test_no_such_edge_is_none() -> None:
    ctx, _ = option_world(LEDGER, AFTER)
    assert load_option_setup(ctx, "nope") is None


def test_no_trade_is_unknown_never_zero() -> None:
    ev = setup([]).evidence
    assert ev is not None and ev.unknown is not None and ev.unknown.code is UnknownCode.NO_ROW
    assert (ev.trades, ev.typical, ev.bad_mean, ev.kept, ev.by_year) == (0, None, None, 0, ())


def test_excluded_picks_are_not_counted() -> None:
    gone = option_trade(30, None, status="excluded", excluded_reason="no_chain", hit=None)
    ev = setup([*LEDGER, gone]).evidence
    assert ev is not None and ev.unknown is None and ev.trades == 20


def test_one_trade_without_a_return_on_capital_makes_the_section_unknown() -> None:
    ev = setup([*LEDGER, option_trade(30, None)]).evidence
    assert ev is not None and ev.unknown is not None
    assert ev.unknown.code is UnknownCode.NOT_STORED and ev.typical is None


def test_a_run_from_before_the_ledger_is_not_stored() -> None:
    ctx, _ = option_world(None, AFTER)
    found = load_option_setup(ctx, "drift")
    assert found is not None and found.evidence is not None
    assert found.evidence.unknown is not None
    assert found.evidence.unknown.code is UnknownCode.NOT_STORED


def test_a_licensed_ledger_is_licence_unknown_to_a_viewer_without_it() -> None:
    ev = setup([option_trade(i, r, licence="personal") for i, r in enumerate(RETURNS)]).evidence
    assert ev is not None and ev.unknown is not None and ev.unknown.code is UnknownCode.LICENCE
    assert ev.typical is None


def test_a_trade_that_exits_after_the_session_is_not_read() -> None:
    late = option_trade(31, 0.9, exit_session=AFTER + timedelta(days=5))
    ev = setup([*LEDGER, late]).evidence
    assert ev is not None and ev.trades == 20 and ev.kept == 18


def test_a_run_that_ends_after_the_session_has_no_evidence() -> None:
    ev = setup(day=END - timedelta(days=3)).evidence
    assert ev is not None and ev.unknown is not None and ev.unknown.code is UnknownCode.NOT_RUN
    assert ev.trades == 0


def test_a_setup_with_no_run_has_no_basis_and_no_invented_verdict() -> None:
    docs = {
        **DOCS, **SETTINGS, ("site", "edges", "drift"): {**EDGE, "outcome": OPTION},
        ("site", KIND, NAME): TEMPLATES,
    }  # fmt: skip
    ctx = session_ctx(stores(MemoryBackend(), docs=docs), AFTER)
    found = load_option_setup(ctx, "drift")
    assert found is not None and found.position_kind == OPTIONS and found.rules is not None
    assert found.evidence is not None and found.evidence.unknown is not None
    assert found.evidence.unknown.code is UnknownCode.NOT_RUN
    assert (found.evidence.trades, found.evidence.typical, found.evidence.costs) == (0, None, None)


def test_a_live_verdict_on_a_newer_run_than_the_bounded_one_is_not_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live judge reads the unbounded canonical run: its basis is no basis of the (older)
    run the ledger is read from, so the section is UNKNOWN, never a mixed read."""
    real = evidence_module.runs

    def load(ctx: Any, edge: Any, bounded: bool = False) -> Any:
        found = real.load_canonical_run(ctx, edge, bounded)
        if bounded or found.run is None:
            return found
        return replace(found, run=replace(found.run, run_id="newer"))

    monkeypatch.setattr(
        evidence_module, "runs",
        SimpleNamespace(load_canonical_run=load, load_run_trades=real.load_run_trades),
    )  # fmt: skip
    ev = setup().evidence
    assert ev is not None and ev.unknown is not None and ev.unknown.code is UnknownCode.NOT_RUN
    assert ev.trades == 0 and ev.typical is None


def test_a_non_finite_return_on_capital_is_not_stored_never_dropped() -> None:
    ev = setup([*LEDGER, option_trade(30, float("nan"))]).evidence
    assert ev is not None and ev.unknown is not None
    assert ev.unknown.code is UnknownCode.NOT_STORED and ev.trades == 0
