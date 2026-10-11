"""``EdgeHorizons`` (ADR 0064): the verdict's screen at every holding period the run measured, the
basis marked, each with its in-sample, out-of-sample and all figures and the date its
out-of-sample count is expected, read from the stored projection of its own ``all`` row; a
hidden copy's out-of-sample and whole-history figures are withheld; a period not stored is
``not_stored``, never a zero."""

from datetime import date
from typing import Any

import pytest

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.edge_evidence.slices import horizons
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

EXITS = tuple(date(2026, 10, d) for d in range(1, 29))


def horizon_rows(h: int, oos: int, **kw: Any) -> list[dict[str, Any]]:
    """The whole-history, in-sample and frozen rows of ``momo`` at holding period ``h``."""
    base = {"horizon_sessions": h, "base_rate": 0.5}
    return [
        row("momo", "all", 0.55, FROZEN, sessions=300, **base, **kw),
        row("momo", "in_sample", 0.6, FROZEN, sessions=250, **base),
        row("momo", "frozen", 0.52, FROZEN, sessions=oos, **base),
    ]


def load(extra: list[dict[str, Any]], **write: Any) -> horizons.EdgeHorizons:
    backend = MemoryBackend()
    write_run(backend, "r1", FROZEN, 0.7, extra=extra, **write)
    ctx = stores(backend)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    return horizons.load_horizons(ctx, edge, official_basis(ctx, edge))


def test_every_holding_period_of_the_basis_screen_is_a_row_shortest_first_with_the_basis_marked():
    found = load(horizon_rows(5, 30) + horizon_rows(10, 30) + [
        row("other", "frozen", 0.9, FROZEN, horizon_sessions=7)
    ])  # fmt: skip
    assert (found.state, found.variant, found.needed) == (horizons.MEASURED, "momo", 40)
    assert [r.horizon for r in found.rows] == [5, 10, 20]  # the other screen's 7 is not here
    marked = [r.horizon for r in found.rows if r.basis]
    assert marked == [5]  # the verdict's own pick (best in-sample: 0.60 at 5 and 10, the shorter)


def test_a_row_carries_the_three_periods_lift_in_points_and_trades() -> None:
    found = load(horizon_rows(5, 30))
    five = found.rows[0]
    by = {f.period: f for f in five.figures}
    assert [f.period for f in five.figures] == ["all", "in_sample", "out_of_sample"]
    assert by["in_sample"].lift_pts == pytest.approx(10.0) and by["in_sample"].trades == 250
    assert by["out_of_sample"].lift_pts == pytest.approx(2.0)
    assert by["out_of_sample"].trades == 30 and by["out_of_sample"].thin
    assert not by["all"].thin


def test_the_date_the_out_of_sample_count_is_expected_reads_the_horizons_own_projection() -> None:
    proj = {
        "projected_exits": list(EXITS),
        "decisions_scheduled_oos": 20,
        "decisions_measured_oos": 20,
    }
    found = load(horizon_rows(5, 30, **proj) + horizon_rows(10, 30))
    five, ten = found.rows[0], found.rows[1]
    assert (five.oos_by.state, five.oos_by.have, five.oos_by.remaining) == ("projected", 30, 10)
    assert five.oos_by.expected_by == EXITS[9]  # 10 more at a full fill: the 10th stored exit
    assert ten.oos_by.state == "not_stored" and ten.oos_by.expected_by is None  # its own row


def test_an_out_of_sample_count_already_met_is_reached_with_no_date() -> None:
    found = load(horizon_rows(5, 45))
    assert found.rows[0].oos_by.state == "reached" and found.rows[0].oos_by.expected_by is None


def test_a_horizon_with_no_frozen_period_is_not_stored_and_has_no_date() -> None:
    ins = row(
        "momo", "in_sample", 0.6, FROZEN
    )  # the basis (20) needs an in-sample row to be chosen
    found = load([ins, row("momo", "all", 0.55, FROZEN, horizon_sessions=5, sessions=300)])
    five = found.rows[0]
    by = {f.period: f for f in five.figures}
    assert by["out_of_sample"].state == by["in_sample"].state == horizons.NOT_STORED
    assert by["out_of_sample"].win_rate is None and five.oos_by.state == "not_stored"


def test_a_run_with_no_basis_screen_rows_has_no_horizons() -> None:
    ctx = stores(MemoryBackend())
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = horizons.load_horizons(ctx, edge, official_basis(ctx, edge))
    assert found.state == horizons.NOT_STORED and found.rows == ()


def test_a_hidden_copy_shows_the_in_sample_figure_and_withholds_the_rest() -> None:
    backend = MemoryBackend()
    extra = [
        row("momo", "in_sample", 0.6, MOVED, edge_id="mine", user_id="me", exploratory=True,
            horizon_sessions=5),
        row("momo", "split", 0.99, MOVED, edge_id="mine", user_id="me", exploratory=True,
            horizon_sessions=5),
    ]  # fmt: skip
    write_own_run(backend, extra=extra)
    ctx = ctx_for(backend, with_copy())
    found = horizons.load_horizons(ctx, mine(ctx), official_basis(ctx, mine(ctx)))
    five = next(r for r in found.rows if r.horizon == 5)
    by = {f.period: f for f in five.figures}
    assert by["in_sample"].state == horizons.MEASURED
    assert by["out_of_sample"].state == by["all"].state == horizons.OOS_HIDDEN
    assert by["out_of_sample"].win_rate is None
    assert five.oos_by.state == "oos_hidden" and five.oos_by.expected_by is None
