"""``evaluate_time_series`` and its place in ``evaluate_edge``: a known result by hand, exclusions
that are never misses, the frozen split, random window sets, and the rows the verdict reads."""

from datetime import date

import pytest

from algotrade.config.edges.document import MAIN, QUALITY_BAR
from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.results import edge_eval_frame, write_edge_eval
from algotrade.services.evaluation.evidence.contract import trade_problems as trades_problems
from algotrade.services.evaluation.time_series import harness
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from algotrade.services.read.context import open_stores
from algotrade.services.read.evaluation.edges import load_edge
from algotrade.services.read.evaluation.verdict import load_edge_verdict
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.time_series.conftest import (
    AS_OF,
    FIRST,
    LAST,
    WINDOW,
    H,
    World,
    build_world,
    timed_edge,
    value_of,
)

SPLIT = date(2025, 1, 1)


def run(w: World, split: date | None = None, draws: int = 1000):  # type: ignore[no-untyped-def]
    return evaluate_time_series(
        w.reader, timed_edge(), FIRST, LAST, AS_OF, lambda d: "calm", split, False, draws
    )


def test_a_known_result_by_hand() -> None:
    w = build_world()
    ran = run(w)
    assert (ran.window, ran.horizon, ran.scheduled, ran.unclosed) == (
        WINDOW,
        H,
        23,
        0,
    )  # December 2025's window runs into 2026
    (spy,) = ran.results
    m = spy.measures[0]
    windows = [value_of(p, k) for k, p in enumerate(w.periods) if p.inside]
    others = [value_of(p, k) for k, p in enumerate(w.periods) if not p.inside]
    assert (m.sessions, m.picks, m.hits, m.hit_rate) == (23, 23, 23, 1.0)
    assert m.mean_excess_picks == pytest.approx(sum(windows) / len(windows))
    assert m.bh_mean == pytest.approx(sum(others) / len(others))
    assert m.decile_spread == pytest.approx(m.mean_excess_picks - m.bh_mean)
    assert m.eligible == len(others) and m.base_rate == pytest.approx(
        sum(v > 0 for v in others) / len(others)
    )
    assert m.decile_t is not None and m.decile_t > 3 and m.lift is not None and m.lift > 1
    assert [x.slice_kind for x in spy.measures] == ["all", "year", "year", "regime"]
    assert not spy.lost and spy.randoms == ()  # no split, so no out-of-sample draws


def test_a_period_with_no_outcome_is_excluded_with_its_reason_never_a_miss() -> None:
    base = build_world()
    gone, flagged = base.periods[0].entry, base.periods[2].entry
    w = build_world(
        skip=frozenset({gone}),
        changes={flagged: {"outcome_status": "UNMEASURED", "fwd_return": None,
                           "outcome_reason": "BAD_BAR", "fwd_max_return": None,
                           "fwd_max_drawdown": None}},
    )  # fmt: skip
    (spy,) = run(w).results
    assert spy.lost == {harness.NO_OUTCOME: 1, "UNMEASURED:BAD_BAR": 1}
    assert spy.measures[0].picks + spy.measures[0].eligible == len(w.periods) - 2


def test_an_unknown_symbol_is_unmeasured_with_a_reason() -> None:
    w = build_world()
    edge = timed_edge(
        universe={
            "where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["SPY", "ZZZZ"]}]}
        }
    )
    ran = evaluate_time_series(w.reader, edge, FIRST, LAST, AS_OF, lambda d: "calm", None, False)
    spy, zzzz = ran.results
    assert spy.measures[0].picks == 23
    assert zzzz.lost == {harness.UNKNOWN_SYMBOL: len(w.periods)}
    assert (zzzz.measures[0].sessions, zzzz.measures[0].hit_rate) == (0, None)
    assert ran.unclosed == 0  # SPY measured every window


def test_a_split_gives_the_frozen_slice_and_a_thousand_random_window_sets() -> None:
    w = build_world()
    (spy,) = run(w, SPLIT).results
    by = {m.slice_kind: m for m in spy.measures}
    assert by["in_sample"].picks + by["frozen"].picks == by["all"].picks
    assert len(spy.randoms) == 1000
    assert {d.picks for d in spy.randoms} == {by["frozen"].picks}
    assert all(d.base_rate == by["frozen"].base_rate for d in spy.randoms)
    assert run(w, SPLIT).results[0].randoms == spy.randoms  # seeded: the same draws again


def test_a_window_not_known_at_as_of_is_not_read() -> None:
    w = build_world()
    last_window = [p for p in w.periods if p.inside][-1]
    seen = evaluate_time_series(
        w.reader, timed_edge(), FIRST, LAST, AS_OF, lambda d: "calm", None, False
    )
    assert last_window.entry in {e for e, _ in seen.results[0].in_window}
    late = build_world(known=AS_OF.replace(year=2027))  # every row stamped after as_of
    ran = evaluate_time_series(
        late.reader, timed_edge(), FIRST, LAST, AS_OF, lambda d: "calm", None, False
    )
    assert ran.results[0].measures[0].picks == 0 and ran.unclosed == 23


def test_evaluate_edge_gives_the_rows_the_verdict_reads() -> None:
    w = build_world()
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"),
        timed_edge(frozen_from="2025-01-01"), FIRST, LAST, AS_OF,
    )  # fmt: skip
    (r,) = ev.results
    assert (r.variant, r.role, r.horizon, r.edge_variant) == ("SPY", "screener", H, MAIN)
    assert (
        ev.trials == 1 and r.measures[0].trials == 1 and r.measures[0].deflated_sharpe is not None
    )
    assert ev.start_sessions == {H: 23} and ev.unclosed_sessions == {H: 0}
    assert ev.benchmark == "none" and r.timing is not None
    frame = edge_eval_frame(ev, "run-1", AS_OF)
    kinds = set(zip(frame["role"], frame["slice_kind"], strict=True))
    assert {("screener", "all"), ("screener", "frozen"), ("screener", "in_sample"),
            ("random", "draw")} <= kinds  # fmt: skip
    frozen = frame[frame["slice_kind"] == "frozen"].iloc[0]
    assert frozen["decile_t"] > 2 and frozen["hit_rate"] == 1.0 and frozen["sessions"] > 0


def test_the_stored_rows_reach_the_verdict_and_the_t_ratio_is_the_edges_t() -> None:
    """A clear in-window effect over 23 windows is judged by the same verdict as any edge: the
    Welch t of the frozen slice is the 'top vs bottom decile t' it reads, and 23 windows are
    too few to rate, said in the verdict's own words."""
    w = build_world()
    doc = {
        "id": "tom", "name": "Turn of the month", "thesis": "Money arrives at month end.",
        "mechanism": "m", "persistence": "p", "schedule": f"calendar:{WINDOW}",
        "base": "out_of_window", "top_k": "all", "screeners": [], "status": "candidate",
        "frozen_from": date(2025, 1, 1), "sources": [{"title": "A paper"}],
        "universe": {"where": {"all": [{"field": "instrument.symbol", "op": "in",
                                        "value": ["SPY"]}]}},
        "outcome": {"kind": "excess_return", "horizon_sessions": [H], "benchmark": "none",
                    "start_offset_sessions": 1},
        "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
    }  # fmt: skip
    configs = MemoryConfigStore({("site", "edges", "tom"): doc})
    edge = timed_edge(frozen_from="2025-01-01")
    ev = evaluate_edge(w.reader, w.results, configs, UserContext("site"), edge, FIRST, LAST, AS_OF)
    write_edge_eval(w.results, ev, AS_OF, owner="site")
    ctx = open_stores(w.reader, configs, UserContext("site"))
    loaded = load_edge(ctx, "tom")
    assert loaded is not None
    verdict = load_edge_verdict(ctx, loaded)
    frozen = next(m for m in ev.results[0].measures if m.slice_kind == "frozen")
    assert verdict.decile_t == pytest.approx(frozen.decile_t)
    assert verdict.basis.startswith("SPY") and verdict.oos_trades == frozen.sessions
    labels = {c.id: c.label for c in verdict.criteria}
    assert "Welch" in labels["decile_t"] and "Welch" in labels["works_t"]
    assert verdict.verdict == "not_enough_data", verdict.rationale


def test_the_windows_are_trade_contract_rows_equal_to_the_measured_values() -> None:
    """E6a (ADR 0088, 2.5a): the in-window rows of an instrument as contract rows; their values
    are ``in_window``'s, in step, and no measure changed."""
    w = build_world()
    (spy,) = run(w).results
    trades = spy.trades
    assert trades is not None and trades_problems(trades) == []
    assert list(trades["entry_session"]) == [d for d, _ in spy.in_window]
    assert list(trades["value"]) == pytest.approx([v for _, v in spy.in_window])
    assert set(trades["capital_basis"]) == {"notional"} and set(trades["price_source"]) == {"bars"}
    assert (trades["return_on_capital"] == trades["value"]).all() and trades["hit"].all()
