"""The decay with its live bar: the same statistic over the settled paper trades, in the units of
the other bars, never a zero and never a hidden out-of-sample figure."""

from datetime import date
from typing import Any

import pytest

from algotrade.services.read.edge_evidence.basis import official_basis
from algotrade.services.read.edge_evidence.decay import load_decay
from algotrade.services.read.edge_evidence.series import load_basis_series
from algotrade.services.read.evaluation.decay import EdgeDecay
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_desk.conftest import context, store, trade
from tests.unit.services.read.edge_evidence.stored_result import DAYS, basis_of, stored_run
from tests.unit.services.read.evaluation.conftest import EDGE, FROZEN, series_row, session_ctx
from tests.unit.services.read.evaluation.test_versions import (
    ctx_for,
    mine,
    with_copy,
    write_own_run,
)

SELL = date(2026, 6, 1)
PAPER = {
    "measure": "mean_excess",
    "value": 0.012,
    "horizon_sessions": 20,
    "source": 0,
    "sample": 20,
}


def decay_of(
    backend: MemoryBackend, published: dict[str, Any] | None = None, **doc: Any
) -> EdgeDecay:
    changed = {**doc, **({"published": published} if published else {})}
    extra = {("site", "edges", "drift"): {**EDGE, **changed}} if changed else None
    ctx = context(backend, date(2026, 10, 5), extra=extra)
    edge = load_edge(ctx, "drift")
    assert edge is not None
    found = load_decay(ctx, edge, load_basis_series(ctx, basis_of(ctx)))
    assert found is not None
    return found


def setup(backend: MemoryBackend) -> None:
    kw = {"picks": 4, "eligible": 20, "base_hits": 10, "pick_hits": 2}
    stored_run(backend, [series_row(d, FROZEN, **kw) for d in DAYS[:3]])
    rows = [  # session 1: 3 of 4 won; session 2: 2 of 4; session 3 (no series row): ignored
        *[
            trade(
                f"A{i}",
                DAYS[0],
                "won" if i < 3 else "lost",
                sell=SELL,
                excess_return=0.04 if i < 3 else -0.02,
            )
            for i in range(4)
        ],
        *[
            trade(f"B{i}", DAYS[1], "won" if i < 2 else "lost", sell=SELL, excess_return=0.01)
            for i in range(4)
        ],
        trade("C0", date(2026, 9, 1), "won", sell=SELL),
    ]
    store(backend, rows)


def bars(found: EdgeDecay) -> dict[str, object]:
    return {b.period: b for b in found.bars}


def test_the_live_bar_is_the_lift_in_points_over_the_sessions_the_series_has_a_base_rate_for(
    backend: MemoryBackend,
) -> None:
    setup(backend)
    found = decay_of(backend)  # no published figure: every bar reads the lift in points
    assert [b.period for b in found.bars] == ["published", "in_sample", "out_of_sample", "live"]
    live = bars(found)["live"]
    assert (live.state, live.n) == ("measured", 2)  # type: ignore[attr-defined]
    assert live.value == pytest.approx((5 / 8 - 0.5) * 100)  # type: ignore[attr-defined]


def test_the_live_mean_excess_is_the_mean_of_the_sessions_means(backend: MemoryBackend) -> None:
    setup(backend)
    live = bars(decay_of(backend, PAPER))["live"]
    session1 = (3 * 0.04 - 0.02) / 4
    assert live.state == "measured" and live.n == 3  # type: ignore[attr-defined]
    assert live.value == pytest.approx((session1 + 0.01 + 0.02) / 3)  # type: ignore[attr-defined]


def test_a_decile_spread_cannot_be_measured_from_the_paper_record(backend: MemoryBackend) -> None:
    setup(backend)
    live = bars(decay_of(backend, {**PAPER, "measure": "decile_spread"}))["live"]
    assert (live.state, live.value) == ("not_measured_live", None)  # type: ignore[attr-defined]


def test_another_holding_period_than_the_papers_is_not_comparable(backend: MemoryBackend) -> None:
    setup(backend)
    outcome = {**EDGE["outcome"], "horizon_sessions": [20, 60]}
    found = decay_of(backend, {**PAPER, "horizon_sessions": 60}, outcome=outcome)
    live = bars(found)["live"]
    assert (live.state, live.value) == ("not_comparable", None)  # type: ignore[attr-defined]


def test_no_settled_trade_is_not_stored_never_zero(backend: MemoryBackend) -> None:
    stored_run(backend)
    live = bars(decay_of(backend))["live"]
    assert (live.state, live.value) == ("not_stored", None)  # type: ignore[attr-defined]


def test_a_hidden_copy_keeps_its_live_bar_hidden_with_the_out_of_sample_one() -> None:
    backend = MemoryBackend()
    write_own_run(backend)
    ctx = session_ctx(ctx_for(backend, with_copy()), date(2026, 10, 5))
    edge = mine(ctx)
    basis = official_basis(ctx, edge)
    found = load_decay(ctx, edge, load_basis_series(ctx, basis))
    assert found is not None
    states = {b.period: b.state for b in found.bars}
    assert states["out_of_sample"] == states["live"] == "oos_hidden"
