"""``EdgeRegimes`` (ADR 0064): the basis's stored regime rows, one row per regime label, served
as stored; the harness stores a regime over the whole run only, so the in-sample and
out-of-sample figures of a regime are ``not_stored`` (never derived, never zero); a hidden copy's
regime rows contain out-of-sample sessions and are withheld."""

from typing import Any

import pytest

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.edge_evidence.slices import regimes
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


def regime_row(label: str, hit: float, sessions: int = 60, **kw: Any) -> dict[str, Any]:
    return row(
        "momo", "regime", hit, FROZEN, slice_value=label, sessions=sessions, base_rate=0.4, **kw
    )


def load(extra: list[dict[str, Any]]) -> regimes.EdgeRegimes:
    backend = MemoryBackend()
    write_run(backend, "r1", FROZEN, 0.7, extra=extra)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    return regimes.load_regimes(ctx, official_basis(ctx, edge))


def test_each_regime_is_a_row_with_its_stored_whole_run_figures_in_severity_order() -> None:
    found = load([regime_row("STRESS", 0.45), regime_row("CALM", 0.6, sessions=200)])
    assert (found.state, found.variant, found.horizon) == (regimes.MEASURED, "momo", 20)
    assert [r.regime for r in found.rows] == ["CALM", "STRESS"]  # least to most severe
    calm = found.rows[0].figures[0]
    assert calm.period == "all" and calm.state == regimes.MEASURED
    assert (calm.win_rate, calm.base_rate, calm.trades) == (0.6, 0.4, 200)
    assert calm.lift_pts == pytest.approx(20.0)


def part(label: str, side: str, hit: float, sessions: int = 30, **kw: Any) -> dict[str, Any]:
    return row(
        "momo", "regime_part", hit, FROZEN, slice_value=f"{label}:{side}", sessions=sessions,
        base_rate=0.4, **kw,
    )  # fmt: skip


def test_a_regimes_sides_are_read_from_its_stored_parts() -> None:
    """The test that would have caught the IS / OOS tabs saying "Not stored" for stored data."""
    (calm,) = load(
        [
            regime_row("CALM", 0.6),
            part("CALM", "in_sample", 0.7, sessions=21),
            part("CALM", "out_of_sample", 0.5, sessions=6),
        ]
    ).rows
    by = {f.period: f for f in calm.figures}
    assert [f.period for f in calm.figures] == ["all", "in_sample", "out_of_sample"]
    assert by["in_sample"].state == regimes.MEASURED and by["in_sample"].trades == 21
    assert by["out_of_sample"].state == regimes.MEASURED and by["out_of_sample"].win_rate == 0.5


def test_the_split_figures_of_a_run_without_parts_are_not_stored_and_never_a_zero() -> None:
    (calm,) = load([regime_row("CALM", 0.6)]).rows
    by = {f.period: f for f in calm.figures}
    for period in ("in_sample", "out_of_sample"):
        assert by[period].state == regimes.NOT_STORED
        assert (by[period].win_rate, by[period].lift_pts, by[period].trades) == (None, None, None)


def test_a_label_no_session_fell_in_is_no_row_but_the_named_regimes_stay() -> None:
    found = load(
        [
            regime_row("UNKNOWN", 0.0, sessions=0),
            regime_row("STRESS", 0.0, sessions=0),
            regime_row("CALM", 0.6),
        ]
    )
    assert [r.regime for r in found.rows] == ["CALM", "STRESS"]


def test_a_regime_with_fewer_trades_than_the_verdict_needs_is_thin() -> None:
    found = load([regime_row("CALM", 0.6, sessions=200), regime_row("CRISIS", 0.7, sessions=9)])
    thin = {r.regime: r.figures[0].thin for r in found.rows}
    assert thin == {"CALM": False, "CRISIS": True}  # min_oos_trades 40: the verdict's own bar


def test_a_regime_label_outside_the_scale_follows_it_and_a_regime_of_another_screen_is_left() -> (
    None
):
    other = row("other", "regime", 0.9, FROZEN, slice_value="CALM")
    found = load([regime_row("UNKNOWN", 0.5), regime_row("CAUTION", 0.5), other])
    assert [r.regime for r in found.rows] == ["CAUTION", "UNKNOWN"]


def test_a_run_from_before_the_regime_rows_is_not_stored() -> None:
    found = load([])
    assert found.state == regimes.NOT_STORED and found.rows == ()


def test_an_edge_with_no_run_has_no_regimes() -> None:
    ctx = stores(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = regimes.load_regimes(ctx, official_basis(ctx, edge))
    assert found.state == regimes.NOT_STORED and found.variant is None and found.rows == ()


def test_a_hidden_copy_has_its_regimes_withheld_not_missing() -> None:
    backend = MemoryBackend()
    write_own_run(
        backend,
        extra=[
            row(
                "momo",
                "regime",
                0.99,
                MOVED,
                slice_value="CALM",
                edge_id="mine",
                user_id="me",
                exploratory=True,
            )
        ],
    )
    ctx = ctx_for(backend, with_copy())
    found = regimes.load_regimes(ctx, official_basis(ctx, mine(ctx)))
    assert found.state == regimes.OOS_HIDDEN and found.rows == ()


def test_a_hidden_copy_keeps_only_the_in_sample_parts_of_its_regimes() -> None:
    backend = MemoryBackend()
    mixed = [
        row("momo", "regime", 0.99, MOVED, slice_value="CALM", edge_id="mine", user_id="me",
            exploratory=True),
        row("momo", "regime_part", 0.9, MOVED, slice_value="CALM:in_sample", edge_id="mine",
            user_id="me", exploratory=True, sessions=11),
    ]  # fmt: skip
    write_own_run(backend, extra=mixed)
    ctx = ctx_for(backend, with_copy())
    found = regimes.load_regimes(ctx, official_basis(ctx, mine(ctx)))
    assert found.state == regimes.OOS_HIDDEN
    (calm,) = found.rows
    by = {f.period: f for f in calm.figures}
    assert by["in_sample"].state == regimes.MEASURED and by["in_sample"].trades == 11
    assert by["all"].state == by["out_of_sample"].state == regimes.OOS_HIDDEN
