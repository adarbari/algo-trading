"""The evidence curve (ADR 0064): plotted at the exit, additive, gaps never zero-filled, the
unit deciding the kind, a hidden copy's out-of-sample side withheld, and the live stroke anchored
on the backtest."""

from datetime import date, timedelta

import pytest

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.edge_evidence.curve import (
    CUMULATIVE_EXCESS,
    EXCESS_WINS,
    EdgeCurve,
    load_curve,
)
from algotrade.services.read.edge_evidence.series import load_basis_series
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_desk.conftest import store, trade
from tests.unit.services.read.edge_evidence.stored_result import DAYS, EXIT, read, stored_run
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)


def curve_of(ctx, edge_id: str = "drift") -> EdgeCurve:  # type: ignore[no-untyped-def]
    edge = load_edge(ctx, edge_id)
    assert edge is not None
    basis = official_basis(ctx, edge)
    return load_curve(ctx, edge, basis, load_basis_series(ctx, basis))


def test_the_curve_adds_the_windows_at_their_exit_against_the_field(
    backend: MemoryBackend,
) -> None:
    rows = [
        series_row(d, FROZEN, pick_mean=0.01 * (i + 1), base_mean=0.005) for i, d in enumerate(DAYS)
    ]
    stored_run(backend, list(reversed(rows)))
    c = curve_of(read(backend))
    assert (c.kind, c.unit, c.split_from, c.hidden) == (
        CUMULATIVE_EXCESS,
        "excess_return",
        FROZEN,
        False,
    )
    assert [p.exit for p in c.points] == [d + EXIT for d in DAYS]  # never at the decision
    assert all(p.exit > p.decision for p in c.points)
    assert [round(p.cumulative, 6) for p in c.points] == [
        0.01,
        0.03,
        0.06,
        0.10,
        0.15,
        0.21,
        0.28,
        0.36,
    ]
    assert [round(p.base_cumulative or 0, 6) for p in c.points] == [
        0.005 * (i + 1) for i in range(8)
    ]
    assert [p.period for p in c.points] == ["in_sample"] * 4 + ["out_of_sample"] * 4
    assert c.points[0].trades == 5 and c.gaps == () and c.unknown is None


def test_a_window_with_no_number_is_a_gap_the_line_joins_over(backend: MemoryBackend) -> None:
    gone = {"picks": None, "pick_mean": None}
    stored_run(
        backend,
        [
            series_row(DAYS[0], FROZEN, pick_mean=0.02),
            series_row(DAYS[1], FROZEN, status="excluded_coverage", **gone),
            series_row(DAYS[2], FROZEN, status="excluded_coverage", **gone),
            series_row(
                DAYS[4], FROZEN, status="lost_input", lost_table="rollups/price_stats@v2", **gone
            ),
            series_row(DAYS[5], FROZEN, pick_mean=0.03),
        ],
    )
    c = curve_of(read(backend))
    assert [round(p.cumulative, 4) for p in c.points] == [0.02, 0.05]  # no flat zero segment
    first, lost = c.gaps
    assert (first.kind, first.start, first.end) == ("excluded_coverage", DAYS[1], DAYS[2] + EXIT)
    assert first.unknown is None
    assert lost.kind == "lost_input" and lost.unknown is not None
    assert lost.unknown.kind.value == "SYSTEM"  # a trader reads only this
    assert lost.unknown.cause.leaf.subject == "rollups/price_stats@v2"  # the admin's chain


def test_a_non_return_outcome_is_a_curve_of_wins_above_the_base_rate(
    backend: MemoryBackend,
) -> None:
    kw = {"unit": "cushion", "picks": 4, "eligible": 20, "base_hits": 10}
    stored_run(
        backend,
        [
            series_row(d, FROZEN, pick_hits=h, **kw)
            for d, h in zip(DAYS[:3], (4, 1, 2), strict=True)
        ],
    )
    c = curve_of(read(backend))
    assert (c.kind, c.unit) == (EXCESS_WINS, "cushion")
    assert [p.value for p in c.points] == [2.0, -1.0, 0.0]  # hits - 4 * 0.5
    assert [p.cumulative for p in c.points] == [2.0, 1.0, 1.0]
    assert all(p.base_value is None and p.base_cumulative is None for p in c.points)


def test_no_series_is_unknown_with_a_reason_never_a_flat_curve(backend: MemoryBackend) -> None:
    stored_run(backend, [])
    c = curve_of(read(backend))
    assert c.points == () and c.live is None
    assert c.unknown is not None and c.unknown.code is UnknownCode.NO_ROW
    assert curve_of(read(MemoryBackend())).unknown.code is UnknownCode.NOT_RUN  # type: ignore[union-attr]


def test_a_hidden_copy_shows_its_in_sample_side_only_and_no_live_stroke() -> None:
    backend = MemoryBackend()
    write_own_run(backend)  # three sessions: one before the split, one on it, one after
    ctx = ctx_for(backend, with_copy())
    c = curve_of(ctx, mine(ctx).id)
    assert c.hidden and len(c.points) == 1 and c.points[0].period == "in_sample"
    assert c.live is not None and c.live.state == "oos_hidden" and c.live.points == ()


def test_the_live_stroke_is_anchored_on_the_backtest_and_settled_trades_only(
    backend: MemoryBackend,
) -> None:
    stored_run(backend)  # eight windows of 1%: cumulative 0.08 once the last has exited
    first = date(2026, 9, 1)  # after every backtest exit (the last is 2026-07-21)
    won = [
        trade("EQ:A", first, "won", sell=date(2026, 9, 30), excess_return=0.04),
        trade("EQ:B", first, "won", sell=date(2026, 9, 30), rank=2, excess_return=0.02),
        trade(
            "EQ:C", first + timedelta(days=1), "lost", sell=date(2026, 10, 1), excess_return=-0.01
        ),
        trade("EQ:D", first + timedelta(days=2), "open", sell=date(2026, 10, 9)),  # not yet
        trade("EQ:E", first + timedelta(days=3), "skipped", sell=date(2026, 10, 2)),
        trade("EQ:F", first, "won", sell=date(2026, 9, 30), screener="other", excess_return=0.5),
    ]
    store(backend, won)
    live = curve_of(read(backend, date(2026, 10, 5))).live
    assert live is not None and live.state == "recorded"
    assert (live.since, live.closed, live.sessions) == (first, 3, 2)
    assert live.anchor == pytest.approx(0.08)
    assert [(p.sell, round(p.value, 4), p.trades) for p in live.points] == [
        (date(2026, 9, 30), 0.03, 2),  # the mean of the session's settled trades
        (date(2026, 10, 1), -0.01, 1),
    ]
    assert [round(p.cumulative, 4) for p in live.points] == [0.11, 0.10]


def test_a_trade_whose_sell_session_is_after_the_session_is_open_not_a_point(
    backend: MemoryBackend,
) -> None:
    stored_run(backend)
    store(
        backend,
        [trade("EQ:A", date(2026, 9, 1), "won", sell=date(2026, 9, 30), excess_return=0.04)],
    )
    before = curve_of(read(backend, date(2026, 9, 29))).live  # settled a day later
    after = curve_of(read(backend, date(2026, 10, 5))).live
    assert before is not None and before.state == "none" and before.points == ()
    assert after is not None and len(after.points) == 1


def test_no_paper_trades_is_none_not_a_zero_stroke(backend: MemoryBackend) -> None:
    stored_run(backend)
    live = curve_of(read(backend)).live
    assert live is not None and live.state == "none" and live.points == () and live.anchor is None


def test_a_live_record_before_the_first_exit_starts_from_zero(backend: MemoryBackend) -> None:
    stored_run(backend)
    store(
        backend,
        [trade("EQ:A", date(2026, 5, 1), "won", sell=date(2026, 5, 20), excess_return=0.04)],
    )
    live = curve_of(read(backend)).live
    assert live is not None and live.anchor == 0.0  # the sum of no windows
    assert [round(p.cumulative, 4) for p in live.points] == [0.04]


def test_a_non_return_live_stroke_is_wins_above_the_series_base_rate_at_the_same_session(
    backend: MemoryBackend,
) -> None:
    kw = {"unit": "cushion", "picks": 4, "eligible": 20, "base_hits": 10, "pick_hits": 2}
    stored_run(backend, [series_row(d, FROZEN, **kw) for d in DAYS])
    d = DAYS[0]  # a session the series measured (base rate 0.5), one it did not
    rows = [
        *[trade(f"EQ:{i}", d, "won" if i < 3 else "lost", sell=date(2026, 6, 1)) for i in range(4)],
        trade("EQ:Z", date(2026, 7, 1), "won", sell=date(2026, 7, 29)),
    ]
    store(backend, rows)
    live = curve_of(read(backend)).live
    assert live is not None and len(live.points) == 1  # no base rate at 07-01: no point
    assert live.points[0].value == pytest.approx(3 - 4 * 0.5)
    assert live.sessions == 2 and live.closed == 5
