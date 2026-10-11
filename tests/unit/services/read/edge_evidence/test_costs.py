"""``EdgeCosts`` and ``EdgeCapacity`` (ADR 0064 decision 5): the cost levels and the break-even
cost per period, read from the stored ``cost`` rows of the official run at the verdict's basis;
an outcome that is not a return says so; a hidden copy shows only its in-sample period and the
withheld figures are nowhere."""

from dataclasses import replace
from typing import Any

import pytest

from algotrade.config.edges.document import Outcome
from algotrade.quant.edges.statistics import break_even_cost
from algotrade.services.read.edge_evidence import capacity, costs
from algotrade.services.read.edge_evidence.rows import load_basis_rows
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, row, stores, write_run
from tests.unit.services.read.evaluation.test_versions import (
    MOVED,
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)

OWN_BP = 20  # the document's cost: the stored mean is net of it
GROSS = 0.0125  # the picks' mean excess before any cost, 125 bp


def cost_rows(
    period: str, edge: str = "drift", user: str = "site", plain: bool = False, **kw: Any
) -> list[dict]:
    """One period's cost rows at 0, 15, 20 (own) and 50 bp: a lower win rate as cost rises;
    ``plain``: also the period's own row, with its cost-invariant decile spread."""
    split = kw.pop("split", FROZEN)
    return [
        row(
            "momo",
            "cost",
            0.6 - bp / 1000,
            split,
            edge_id=edge,
            user_id=user,
            slice_value=f"{period}:{bp}",
            mean_excess_picks=GROSS - bp / 1e4,
            base_rate=0.4,
            lift=1.2,
            **kw,
        )
        for bp in (0, 15, OWN_BP, 50)
    ] + (
        [row("momo", period, 0.5, split, edge_id=edge, user_id=user, decile_spread=0.03, **kw)]
        if plain
        else []
    )


def site_world(extra: list[dict], **kw: Any) -> tuple[Any, Any]:
    backend = MemoryBackend()
    write_run(backend, "r1", FROZEN, 0.7, extra=extra, **kw)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    return ctx, edge


def test_the_levels_are_the_stored_rows_by_period_and_cost_and_break_even_is_the_gross_mean() -> (
    None
):
    ctx, edge = site_world(
        cost_rows("all") + cost_rows("frozen") + cost_rows("in_sample", plain=True)
    )
    found = costs.load_edge_costs(ctx, edge)
    assert (found.state, found.variant, found.horizon) == (costs.MEASURED, "momo", 20)
    assert [(lv.period, lv.bp) for lv in found.levels] == [
        (p, bp) for p in ("all", "in_sample", "out_of_sample") for bp in (0, 15, 20, 50)
    ]
    first = found.levels[0]
    assert (first.win_rate, first.base_rate, first.mean_excess) == (0.6, 0.4, GROSS)
    assert first.lift_pts == pytest.approx(20.0)
    assert [lv.bp for lv in found.levels if lv.assumed] == [0.0] * 3  # no cost set: its own is 0
    by = {p.period: p for p in found.periods}
    assert by["all"].break_even_bp == pytest.approx(GROSS * 1e4)
    assert by["out_of_sample"].break_even_bp == pytest.approx(GROSS * 1e4)
    assert by["in_sample"].decile_spread == 0.03  # the period's own row, not a cost row's
    assert by["all"].decile_spread is None  # its row stored none (never a zero)


def test_the_documents_own_cost_is_marked_and_break_even_is_exact_from_any_level() -> None:
    ctx, edge = site_world(cost_rows("all"))
    basis = load_basis_rows(ctx, edge)
    found = costs.costs_of(basis, OWN_BP)
    assert [lv.bp for lv in found.levels if lv.assumed] == [OWN_BP]
    assert found.assumed_bp == OWN_BP
    # whichever level it is read from, the break-even is the gross mean in basis points
    for bp in (0, 15, 20, 50):
        row_ = next(r for r in basis.rows if r.slice_value == f"all:{bp}")
        assert break_even_cost(row_.mean_excess_picks, bp) == pytest.approx(GROSS * 1e4)


def test_an_outcome_that_is_not_a_return_says_so_from_the_document_whatever_rows_exist() -> None:
    ctx, edge = site_world(cost_rows("all"))  # even a stray cost row does not make it a return
    assert edge.settings is not None and edge.settings.cost_applies  # excess_return: a return
    other = replace(edge, settings=replace(edge.settings, cost_applies=False))
    found = costs.load_edge_costs(ctx, other)
    assert found.state == costs.NOT_A_COST_OUTCOME and found.levels == () and found.periods == ()


def test_the_documents_outcome_decides_whether_a_cost_applies_and_its_orientation() -> None:
    plain = Outcome("excess_return", (20,), "SPY")
    below = Outcome("hit_target", (20,), "SPY", measure="excess_return", direction="below")
    ratio = Outcome("hit_target", (20,), "none", measure="realised_to_implied_vol")
    assert (plain.is_return, plain.sign, below.is_return, below.sign) == (True, 1.0, True, -1.0)
    assert not ratio.is_return and not Outcome("expires_otm", (20,), "none").is_return


def test_break_even_undoes_a_below_outcomes_orientation() -> None:
    """Stored mean = sign * (gross - cost): gross 1.25%, 20 bp cost, direction below."""
    assert break_even_cost(-(0.0125 - 0.0020), 20, -1.0) == pytest.approx(125.0)
    assert break_even_cost(0.0125 - 0.0020, 20) == pytest.approx(125.0)


def test_a_run_from_before_the_cost_rows_is_not_stored_never_not_a_cost_outcome() -> None:
    ctx, edge = site_world([])
    found = costs.load_edge_costs(ctx, edge)
    assert found.state == costs.NOT_STORED and found.levels == ()
    assert all(p.state == costs.NOT_STORED for p in found.periods)


def test_an_edge_with_no_run_has_no_rows_and_no_state_beyond_not_stored() -> None:
    ctx = stores(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert edge is not None
    basis = load_basis_rows(ctx, edge)
    assert basis.run is None and basis.rows == () and "no official result" in basis.reason
    assert costs.load_edge_costs(ctx, edge).state == costs.NOT_STORED


def test_a_screen_and_holding_period_can_be_named_and_default_to_the_verdicts_basis() -> None:
    ctx, edge = site_world(cost_rows("all"))
    assert load_basis_rows(ctx, edge).variant == "momo"
    other = load_basis_rows(ctx, edge, "momo", 5)
    assert (other.variant, other.horizon, other.rows) == ("momo", 5, ())


def test_a_hidden_copy_shows_the_in_sample_period_and_the_rest_is_hidden_not_missing() -> None:
    backend = MemoryBackend()
    extra = [
        *cost_rows("in_sample", "mine", "me", split=MOVED, exploratory=True),
        *cost_rows("all", "mine", "me", split=MOVED, exploratory=True),
        *cost_rows("split", "mine", "me", split=MOVED, exploratory=True),
    ]
    write_own_run(backend, extra=extra)
    ctx = ctx_for(backend, with_copy())
    found = costs.load_edge_costs(ctx, mine(ctx))
    assert {lv.period for lv in found.levels} == {"in_sample"}  # nothing of the rest is served
    by = {p.period: p for p in found.periods}
    assert by["in_sample"].state == costs.MEASURED and by["in_sample"].break_even_bp is not None
    assert by["all"].state == by["out_of_sample"].state == costs.OOS_HIDDEN
    assert by["all"].break_even_bp is None and by["out_of_sample"].decile_spread is None
    served = capacity.load_edge_capacity(ctx, mine(ctx))
    assert {p.period: p.state for p in served.periods}["out_of_sample"] == costs.OOS_HIDDEN


def test_the_capacity_of_each_period_with_the_floor_it_is_read_against() -> None:
    adv = {"pick_adv_median": 8e6, "pick_adv_known": 30, "pick_adv_low": 4, "picks": 40}
    ctx, edge = site_world([row("momo", "in_sample", 0.5, FROZEN, **adv)])
    found = capacity.load_edge_capacity(ctx, edge)
    assert (found.state, found.floor_usd) == (capacity.MEASURED, 5_000_000.0)
    by = {p.period: p for p in found.periods}
    ins = by["in_sample"]
    assert (ins.state, ins.picks, ins.adv_median, ins.adv_known, ins.adv_low) == (
        capacity.MEASURED, 40, 8e6, 30, 4
    )  # fmt: skip
    assert by["out_of_sample"].state == capacity.NOT_STORED  # an older row: unknown
    assert by["out_of_sample"].adv_median is None and by["all"].state == capacity.NOT_STORED


def test_no_pick_with_a_stored_volume_is_not_stored_never_a_zero_median() -> None:
    ctx, edge = site_world([row("momo", "in_sample", 0.5, FROZEN, pick_adv_known=0, picks=12)])
    found = capacity.load_edge_capacity(ctx, edge)
    assert found.state == capacity.NOT_STORED
    assert all(p.adv_median is None and p.adv_low is None for p in found.periods)
