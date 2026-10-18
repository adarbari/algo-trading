"""The site's trial log reads the records of the legacy owners (``LEGACY_SITE_OWNERS``) from before
``LEGACY_SITE_CUTOFF`` as its own, each trial once; a trial's statistics read the series its
unit calls for; and the sides of an outcome (ADR 0053 amendment) measured end to end on the small
world: the bottom of the ranking among liquid names, the spread, the borrow, the ledger; and
the ``pair_spread`` outcome (EB H9): the cheap class against its sibling by hand, the rich leg's
borrow, the sibling read at the decision session, a sibling with no stored row."""

import math
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
    N,
    World,
    build_world,
    edge,
    outcome_row,
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


def test_a_session_with_too_few_scores_has_no_short_leg_and_is_not_measured() -> None:
    """Fail closed: with 6 of 20 names scored there is no honest bottom, so a short or long-short
    session is left out (``excluded_coverage``) while a long edge still counts its picks."""
    nan = float("nan")
    w = build_world(price_of=lambda d, i: 100.0 + 10 * i if i < 6 else nan)
    for side in ("short", "long_short", "long"):
        e = edge(outcome={"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
                          "start_offset_sessions": 1, "side": side}, top_k=3)  # fmt: skip
        ev = evaluate_edge(
            w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
        )
        (r,) = ev.results
        if side == "long":
            assert r.measures[0].picks > 0
        else:
            assert all(s.excluded_coverage and not s.picks for s in r.stats), side


STARTS = [DAYS[0], DAYS[2], DAYS[4], DAYS[6]]  # every 2nd session of Sept 1-10


def run_pair(w: World, e=None) -> EdgeEvaluation:  # type: ignore[no-untyped-def]
    user = UserContext("site")
    return evaluate_edge(
        w.reader, w.results, w.configs, user, e or edge(), DAYS[0], DAYS[-1], AS_OF
    )


SIBLING = "rollup.share_classes@v1.sibling_id"
PAIR_OUTCOME = {
    "kind": "pair_spread", "horizon_sessions": [2], "benchmark": "none", "pair_field": SIBLING,
    "start_offset_sessions": 1, "borrow_bps_annual": 0,
}  # fmt: skip


def pair_world(partner: dict[date, int] | None = None) -> World:
    """Every name's sibling: the neighbour of its pair (0-1, 2-3, ...), or ``partner[day]``'s
    shift (name i with i + shift) on a day listed, to show which partition is read."""
    w = build_world()
    for day in [*DAYS, DAYS[-1] + timedelta(days=1)]:
        shift = (partner or {}).get(day)
        rows = [
            {"instrument_id": iid, "sibling_id": IDS[(i + 1) % N if i % 2 == 0 else i - 1]}
            if shift is None
            else {"instrument_id": iid, "sibling_id": IDS[(i + shift) % N]}
            for i, iid in enumerate(IDS)
        ]
        w.write_rollup("rollups/instrument/share_classes@v1", day, rows)
    return w


def test_a_pair_spread_run_measures_the_cheap_class_against_its_sibling_by_hand() -> None:
    """Name i earns (i - 9.5)%. The picks 15..19 each against their pair neighbour: 15 beats 14
    by 1 point, 16 trails 17 by 1, 17 beats 16, 18 trails 19, 19 beats 18: the mean is +0.2 points,
    three of five hit. Judged as a spread: the stored side is long_short (a diagnostic)."""
    ev = run_pair(pair_world(), edge(outcome=PAIR_OUTCOME))
    (r,) = ev.results
    m = r.measures[0]
    assert (m.sessions, m.picks, m.hits) == (4, 20, 12)
    assert m.mean_excess_picks == pytest.approx(0.002)
    assert m.eligible == 80 and m.base_rate == pytest.approx(0.5)  # a name and its mirror
    assert r.side == "long_short"
    assert edge_eval_frame(ev, "run-1", AS_OF)["side"].eq("long_short").all()
    assert [s.session for s in r.stats] == STARTS  # a horizon apart: the windows never overlap
    first = r.stats[0].picks
    assert [p.reason for p in first] == [""] * 5  # every pick has its pair


def test_the_rich_legs_borrow_is_paid_and_the_site_default_fills_an_unset_rate() -> None:
    free = run_pair(pair_world(), edge(outcome=PAIR_OUTCOME)).results[0].measures[0]
    dear = {**PAIR_OUTCOME, "borrow_bps_annual": 2520}  # 25.2% a year over 2 of 252 sessions
    paid = run_pair(pair_world(), edge(outcome=dear)).results[0].measures[0]
    assert free.mean_excess_picks - paid.mean_excess_picks == pytest.approx(0.252 * 2 / 252)
    unset = {k: v for k, v in PAIR_OUTCOME.items() if k != "borrow_bps_annual"}
    site = run_pair(pair_world(), edge(outcome=unset)).results[0].measures[0]
    assert site.mean_excess_picks < free.mean_excess_picks  # the verdict.toml default applies


def test_a_pair_spread_reads_the_sibling_at_the_decision_session_never_a_later_one() -> None:
    e = edge(outcome=PAIR_OUTCOME)
    clean = run_pair(pair_world(), e)
    later = {d: 2 for d in DAYS if d not in STARTS}  # a reclassification after every D
    assert run_pair(pair_world(later), e).results == clean.results
    at_d = dict.fromkeys(STARTS, 2)  # ... and one at D itself changes the answer
    assert run_pair(pair_world(at_d), e).results != clean.results


def test_a_pick_whose_sibling_has_no_stored_row_is_excluded_with_a_reason() -> None:
    def rows(day: date) -> list[dict[str, Any]]:
        return [outcome_row(iid, i, day) for i, iid in enumerate(IDS) if i != 18]  # 18: no row

    first = run_pair(build_pair_without(rows), edge(outcome=PAIR_OUTCOME)).results[0].stats[0]
    reasons = {p.instrument_id: p.reason for p in first.picks}
    assert reasons[IDS[19]] == "no_sibling_row"  # 19's sibling is 18
    assert reasons[IDS[18]] == "no_entry_bar"  # 18 itself has no row at all
    assert first.excluded_missing >= 1 and first.pick_values
    assert all(math.isfinite(v) for v in first.pick_values)


def build_pair_without(rows_of: Any) -> World:
    w = build_world(rows_of=rows_of)
    for day in [*DAYS, DAYS[-1] + timedelta(days=1)]:
        rows = [
            {"instrument_id": iid, "sibling_id": IDS[(i + 1) % N if i % 2 == 0 else i - 1]}
            for i, iid in enumerate(IDS)
        ]
        w.write_rollup("rollups/instrument/share_classes@v1", day, rows)
    return w
