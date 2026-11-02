"""The basis's series, valued in the outcome's unit: windows by exit, gaps apart, never zero."""

from datetime import timedelta

import pytest

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.edge_evidence.drawdown import load_drawdown
from algotrade.services.read.edge_evidence.rolling import load_monthly, load_rolling_starts
from algotrade.services.read.edge_evidence.series import BasisSeries, load_basis_series
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_evidence.stored_result import DAYS, read, series_of, stored_run
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)


def basis_series(backend: MemoryBackend) -> BasisSeries:
    found = series_of(read(backend))
    assert isinstance(found, BasisSeries)
    return found


def test_windows_are_in_the_order_their_outcomes_became_known_with_their_side(
    backend: MemoryBackend,
) -> None:
    stored_run(backend, [series_row(d, FROZEN) for d in reversed(DAYS)])
    s = basis_series(backend)
    assert [w.row.decision_session for w in s.windows] == DAYS
    assert all(w.exit > w.row.decision_session for w in s.windows)  # known after it was decided
    assert [w.period for w in s.windows] == ["in_sample"] * 4 + ["out_of_sample"] * 4
    assert (s.key, s.unit, s.is_return, s.horizon, s.gaps) == (
        ("momo", 20),
        "excess_return",
        True,
        20,
        (),
    )


def test_a_row_with_no_number_is_a_gap_not_a_window_of_zero(backend: MemoryBackend) -> None:
    missing = {"picks": None, "pick_mean": None}
    stored_run(
        backend,
        [
            series_row(DAYS[0], FROZEN),
            series_row(DAYS[1], FROZEN, status="excluded_coverage", **missing),
            series_row(DAYS[2], FROZEN, status="no_picks", **missing),
            series_row(DAYS[3], FROZEN, status="lost_input", lost_table="rollups/x", **missing),
            series_row(DAYS[4], FROZEN, pick_mean=None),  # measured, but no mean stored
            series_row(DAYS[5], FROZEN, role="baseline", variant="spy"),  # not the basis
            series_row(DAYS[6], FROZEN, variant="other"),
        ],
    )
    s = basis_series(backend)
    assert [w.row.decision_session for w in s.windows] == [DAYS[0]]
    assert [g.decision_session for g in s.gaps] == DAYS[1:5]


def test_a_non_return_outcome_is_valued_in_wins_above_the_base_rate(
    backend: MemoryBackend,
) -> None:
    window = {"unit": "cushion", "picks": 5, "pick_hits": 4, "eligible": 20, "base_hits": 10}
    bad = {"unit": "cushion", "picks": 5, "pick_hits": None, "eligible": 20, "base_hits": 10}
    stored_run(
        backend,
        [series_row(DAYS[0], FROZEN, **window), series_row(DAYS[1], FROZEN, **bad)],
    )
    s = basis_series(backend)
    assert (s.unit, s.is_return) == ("cushion", False)
    assert [(w.value, w.base_value) for w in s.windows] == [(1.5, None)]  # 4 - 5 * 10 / 20
    assert len(s.gaps) == 1  # the window missing its wins is not valued at zero


def test_a_run_with_no_series_is_not_stored_and_no_run_is_not_run(backend: MemoryBackend) -> None:
    stored_run(backend, [])
    found = series_of(read(backend))
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_ROW
    assert found.kind.value == "NOT_STORED" and "re-run" in found.cause.text
    assert isinstance(series_of(read(MemoryBackend())), Unknown)


def test_a_series_of_another_horizon_is_not_the_basis(backend: MemoryBackend) -> None:
    stored_run(backend, [series_row(DAYS[0] + timedelta(days=0), FROZEN, horizon_sessions=15)])
    assert isinstance(series_of(read(backend)), Unknown)


def test_every_section_of_a_hidden_copy_is_in_sample_only() -> None:
    """Fitness: the rolling starts, months, drawdown and curve of a copy read the one filtered
    series, so none shows a window decided on or after its split (ADR 0064 decision 3)."""
    backend = MemoryBackend()
    write_own_run(backend)  # sessions a week before the split, on it and a week after
    ctx = ctx_for(backend, with_copy())
    edge = mine(ctx)
    series = load_basis_series(ctx, official_basis(ctx, edge))
    assert isinstance(series, BasisSeries) and series.hidden
    assert [w.period for w in series.windows] == ["in_sample"] and not series.gaps
    assert load_rolling_starts(series).starts == ()  # no window carries its counts here
    assert sum(m.trades for m in load_monthly(series).months) == 1
    drawdown = load_drawdown(series)
    assert (drawdown.max_out_of_sample, drawdown.vol_out_of_sample) == (None, None)
    assert len(drawdown.points) == 1


def test_an_option_setup_is_valued_on_its_collateral_and_a_share_setup_as_before(
    backend: MemoryBackend,
) -> None:
    # E11: an option setup's windows are its picks' return on collateral (and the base's), never
    # its value per entry price; a row of it with none stored is a gap
    option = {"unit": "pnl", "capital_basis": "cash_secured", "pick_mean": 0.004, "base_mean": 0.0}
    stored_run(
        backend,
        [
            series_row(DAYS[0], FROZEN, **option, pick_roc_mean=0.03, base_roc_mean=0.01),
            series_row(DAYS[1], FROZEN, **option, pick_roc_mean=-0.05, base_roc_mean=0.0),
            series_row(DAYS[2], FROZEN, **option),  # an older row: no return on capital
        ],
    )
    s = basis_series(backend)
    assert (s.unit, s.is_return) == ("return_on_capital", True)
    assert [(w.value, w.base_value) for w in s.windows] == [(0.03, 0.01), (-0.05, 0.0)]
    assert [g.decision_session for g in s.gaps] == [DAYS[2]]
    monthly = load_monthly(s)  # the month map reads the same collateral windows
    assert monthly.unit == "return_on_capital"
    assert sum(m.value for m in monthly.months if m.value is not None) == pytest.approx(
        sum(w.weighted for w in s.windows)
    )


def test_a_share_setup_with_a_notional_basis_keeps_its_value(backend: MemoryBackend) -> None:
    share = {"capital_basis": "notional", "pick_roc_mean": 0.5, "base_roc_mean": 0.5}
    stored_run(backend, [series_row(DAYS[0], FROZEN, **share)])
    s = basis_series(backend)
    assert s.unit == "excess_return"
    assert [(w.value, w.base_value) for w in s.windows] == [(0.02, 0.01)]  # unchanged
