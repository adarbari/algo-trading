"""The site's trial log reads the records of the legacy owners (``LEGACY_SITE_OWNERS``) from before
``LEGACY_SITE_CUTOFF`` as its own, each trial once; a trial's statistics read the series its
unit calls for; and the sides of an outcome (ADR 0053 amendment) measured end to end on the small
world: the bottom of the ranking among liquid names, the spread, the borrow, the ledger."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from algotrade.config.user import UserContext
from algotrade.quant.edges.statistics import sharpe
from algotrade.services.evaluation.cross_section.detail.trades import trades_frame
from algotrade.services.evaluation.cross_section.detail.windows import SeriesFacts
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    VariantResult,
    _prior_trials,
    _slice_rows,
    evaluate_edge,
)
from algotrade.services.evaluation.cross_section.legs.key import leg_key
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.results import edge_eval_frame
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    AS_OF,
    DAYS,
    IDS,
    build_world,
    edge,
)


def test_the_sites_trial_log_includes_the_legacy_local_runs() -> None:
    class Record:
        def __init__(self, hash_: str) -> None:
            self.stats = {"trials": [{"variant": "momo", "config_hash": hash_, "horizon": 2}]}
            self.finished_at = self.started_at = datetime(2026, 10, 5, tzinfo=UTC)

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            known = {"edge-eval:drift:site": "a", "edge-eval:drift:local": "b"}
            return [Record(known[job])] if job in known else []

    seen = _prior_trials(Writer(), "drift", "site")  # type: ignore[arg-type]
    assert seen == {("main", "momo", "a", 2), ("main", "momo", "b", 2)}
    assert _prior_trials(Writer(), "drift", "alice") == set()  # a user's log is their own


def test_the_legacy_log_counts_a_trial_once_and_only_before_the_cutoff() -> None:
    class Record:
        def __init__(self, at: datetime) -> None:
            self.stats = {"trials": [{"variant": "momo", "config_hash": "h", "horizon": 2}]}
            self.finished_at, self.started_at = at, at

    before = datetime(2026, 10, 5, tzinfo=UTC)
    after = datetime(2026, 10, 12, tzinfo=UTC)

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            return [Record(before)] if job.endswith(":site") else [Record(before), Record(after)]

    assert _prior_trials(Writer(), "drift", "site") == {("main", "momo", "h", 2)}  # once

    class Later:
        def runs_for(self, job: str) -> list[Record]:
            return [] if job.endswith(":site") else [Record(after)]

    assert _prior_trials(Later(), "drift", "site") == set()  # a local run after the cutoff


def test_a_cushion_or_ratio_result_reads_the_excess_wins_and_a_return_its_mean() -> None:
    """ADR 0064 amendment 2026-10-11: the harness reads the unit off the result's series and
    passes it to the slice rows, so a non-return Sharpe ratio is of the excess wins."""
    day = date(2026, 1, 5)
    stats = tuple(
        SessionStat(day + timedelta(days=i), "BULL", (2.0, 2.0), 1 + i % 2, (8, 0.5, 0.0), 6)
        for i in range(6)
    )
    for unit, wins in (("cushion", True), ("ratio", True), ("excess_return", False)):
        result = VariantResult("v", "screener", "h", 15, stats, (), series=SeriesFacts((), unit))
        assert result.unit == unit and result.wins is wins
    assert not VariantResult("v", "screener", "h", 15, stats, ()).wins  # no series: a return
    (all_, *_), _ = _slice_rows(stats, None, False, False, None, None, 0.0, wins=True)
    assert all_.sharpe == pytest.approx(sharpe([s.excess_wins for s in stats]))
    (plain, *_), _ = _slice_rows(stats, None, False, False, None, None, 0.0)
    assert plain.sharpe is None  # every session's mean is 2.0: no spread, no Sharpe ratio


def test_a_logged_baseline_is_not_a_trial_and_a_record_without_roles_still_counts() -> None:
    class Record:
        def __init__(self, trials: list[dict[str, object]]) -> None:
            self.stats = {"trials": trials}
            self.finished_at = self.started_at = datetime(2026, 10, 11, tzinfo=UTC)

    logged = [
        {"variant": "momo", "role": "screener", "config_hash": "a", "horizon": 2},
        {"variant": "spy", "role": "baseline", "config_hash": "b", "horizon": 2},
        {"variant": "old", "config_hash": "c", "horizon": 2},  # before roles were logged
    ]

    class Writer:
        def runs_for(self, job: str) -> list[Record]:
            return [Record(logged)] if job == "edge-eval:drift:alice" else []

    seen = _prior_trials(Writer(), "drift", "alice")  # type: ignore[arg-type]
    assert seen == {("main", "momo", "a", 2), ("main", "old", "c", 2)}


def _sided(side: str, **outcome: Any) -> EdgeEvaluation:
    """The small world (name i earns (i - 9.5)% over 2 sessions and ranks by its price, so name 19
    is the best) with every name liquid but name 0, run for an edge of ``side`` over 5 names."""
    w = build_world()
    for day in (*DAYS, DAYS[-1] + timedelta(days=4)):
        rows = [
            {"instrument_id": i, "adv_usd_20d": 1e6 if k == 0 else 1e7} for k, i in enumerate(IDS)
        ]
        w.writer.write_table(
            "rollups/instrument/price_stats@v2", day, f"p-{day}", stamped(rows, day, f"p-{day}")
        )
    doc = {
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "side": side, **outcome,
    }  # fmt: skip
    e = edge(outcome=doc, top_k=5, frozen_from="2026-09-04")
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
    )


def test_a_short_edge_shorts_the_worst_liquid_names_and_pays_the_borrow() -> None:
    (r,) = _sided("short", borrow_bps_annual=252).results
    m = r.measures[0]
    # name 0 is below the dollar-volume floor: the short leg is names 1..5 (-8.5% .. -4.5%)
    assert {p.instrument_id for s in r.stats for p in s.picks} == {
        f"EQ:N{i:02d}" for i in range(1, 6)
    }
    assert all(p.side == "short" for s in r.stats for p in s.picks)
    assert [p.rank for p in r.stats[0].picks] == [1, 2, 3, 4, 5]  # rank 1: the worst
    borrow = 0.0252 * 2 / 252
    assert m.mean_excess_picks == pytest.approx(0.065 - borrow)
    assert (m.hit_rate, m.base_rate, m.lift) == (1.0, 0.5, 2.0)  # the short's own hits and base
    assert m.decile_spread == pytest.approx(0.18)  # the ranking's: best tenth minus worst
    assert r.side == "short" and r.stats[0].short_values is None


def test_a_short_leg_without_a_known_dollar_volume_is_empty_not_the_illiquid_names() -> None:
    w = build_world()  # no price_stats table at all: no name's volume is known
    e = edge(outcome={"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
                      "start_offset_sessions": 1, "side": "short"}, top_k=5)  # fmt: skip
    ev = evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
    )
    assert all(not s.picks for s in ev.results[0].stats)
    assert ev.results[0].measures[0].picks == 0


def test_a_long_short_edge_is_a_spread_with_no_base_rate_and_both_legs_in_the_ledger() -> None:
    ev = _sided("long_short", borrow_bps_annual=252)
    (r,) = ev.results
    m = r.measures[0]
    borrow = 0.0252 * 2 / 252
    assert m.mean_excess_picks == pytest.approx(0.075 + 0.065 - borrow)  # names 15..19 minus 1..5
    assert (m.hit_rate, m.base_rate, m.lift) == (None, None, None)
    assert r.costs == () and r.stats[0].short_values is not None
    frame = trades_frame(ev, "run-1", AS_OF)
    first = frame[frame["decision_session"] == frame["decision_session"].min()]
    assert sorted(first["side"].unique()) == ["long", "short"] and len(first) == 10
    shorts = first[first["side"] == "short"]
    assert np.allclose(sorted(shorts["gross_value"]), [-0.085, -0.075, -0.065, -0.055, -0.045])
    assert (shorts["value"] > 0).all()  # a short's value is minus the excess return, net


def test_the_side_is_a_column_of_the_results_and_the_random_draws_follow_it() -> None:
    ev = _sided("short")
    frame = edge_eval_frame(ev, "run-1", AS_OF)
    assert set(frame["side"]) == {"short"}  # the screener's rows and its random draws alike
    assert any(str(v).startswith("random") for v in frame["role"])
    long = edge_eval_frame(_sided("long"), "run-1", AS_OF)
    assert set(long["side"]) == {"long"}


def test_a_leg_key_does_not_change_for_a_long_edge_and_does_for_a_short_ones_floor() -> None:
    args = ("t", "u", "iv", None, 1, 10, "e", 5, "event", "event", (0.0, 15.0))
    assert leg_key(*args) == leg_key(*args, None)
    assert leg_key(*args, 5e6) != leg_key(*args, 1e6) != leg_key(*args)
