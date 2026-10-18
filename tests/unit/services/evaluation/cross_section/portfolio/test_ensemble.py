"""An ensemble (ADR 0074 amendment) on the small world: its grid's books are averaged into one
variant counted as ONE trial, the members are reported with their own role and never a trial, and
the out-of-sample haircut is shown beside the in-sample and out-of-sample Sharpe ratios."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.services.evaluation.cross_section.harness import (
    EdgeEvaluation,
    _prior_trials,
    evaluate_edge,
)
from algotrade.services.evaluation.cross_section.reporting.report import render_edge_report
from algotrade.services.evaluation.cross_section.results import (
    edge_eval_frame,
    oos_haircuts,
    records,
    write_edge_eval,
)
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    IDS,
    World,
    build_world,
    edge,
    outcome_row,
    screen,
)

BLEND = "mix:N00=0.6,N01=0.4"  # -9.1% over the window
LOW = {**screen("asc"), "id": "lowmo"}  # ranks the cheapest names first: names 0..4


def _world(scale: bool = False) -> World:
    """The 20 names earning (i - 9.5)%; with ``scale`` every session's returns grow a little, so a
    Sharpe ratio exists on each side of a split."""

    def rows(day: date) -> list[dict[str, Any]]:
        k = 1.0 + 0.2 * DAYS.index(day) if scale and day in DAYS else 1.0
        return [
            outcome_row(
                iid, i, day, horizon_sessions=1, fwd_return=(i - 9.5) / 100 * k,
                fwd_excess_return=(i - 9.5) / 100 * k,
            )
            for i, iid in enumerate(IDS)
        ]  # fmt: skip

    w = build_world(rows_of=rows)
    w.configs = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "momo"): screen(),
            ("site", "strategies", "lowmo"): LOW,
        }
    )
    return w


def _run(w: World, weighting: str = "equal", **doc: Any) -> EdgeEvaluation:
    outcome = {
        "kind": "portfolio_return", "horizon_sessions": [1], "benchmark": BLEND,
        "start_offset_sessions": 1, "cost_bps": 0, "weighting": weighting,
    }  # fmt: skip
    e = edge(
        outcome=outcome, top_k=5, screeners=["momo", "lowmo"],
        **doc,
    )  # fmt: skip
    return evaluate_edge(
        w.reader, w.results, w.configs, UserContext("site"), e, DAYS[0], DAYS[-1], AS_OF
    )


def test_the_ensemble_averages_its_members_books_and_is_one_variant() -> None:
    result = _run(_world(), ensemble={"variants": ["momo", "lowmo"]})
    by = {r.variant: r for r in result.results}
    assert set(by) == {"momo", "lowmo", "ensemble"}
    assert (by["momo"].role, by["lowmo"].role, by["ensemble"].role) == (
        "member",
        "member",
        "screener",
    )
    book = dict(by["ensemble"].stats[0].weights)
    top = {f"EQ:N{i}": 0.1 for i in range(15, 20)}
    bottom = {f"EQ:N{i:02d}": 0.1 for i in range(5)}
    assert book == pytest.approx({**top, **bottom})  # each member holds 20% of five names
    # the ten names average 0%, the blend returns -9.1%: the session is worth 9.1%
    assert by["ensemble"].stats[0].pick_values == pytest.approx((0.091,))
    assert by["ensemble"].grid == 2 and by["momo"].grid is None
    assert by["ensemble"].stats[0].deciles == ()  # no single ranking, no decile figures


def test_the_ensemble_is_one_trial_whatever_its_grid_and_members_are_none() -> None:
    plain = _run(_world())  # two screeners, no ensemble: two trials
    grid = _run(_world(), ensemble={"variants": ["momo", "lowmo"]})
    assert plain.trials == 2
    assert grid.trials == 1  # the ensemble once; its members are not trials
    # the trial log keeps it so: a later run's prior trials hold the ensemble, not the members
    w = _world()
    ev = _run(w, ensemble={"variants": ["momo", "lowmo"]})
    write_edge_eval(w.results, ev, AS_OF)
    assert {(t[0], t[1]) for t in _prior_trials(w.results, "drift", "site")} == {
        ("main", "ensemble")
    }


def test_a_member_that_cannot_form_a_book_leaves_the_ensemble_session_out() -> None:
    """Weighted by score, ``lowmo`` (which ranks the cheap names first, a negative score) has no
    book: no ensemble session, never an average over the member that could."""
    result = _run(_world(), ensemble={"variants": ["momo", "lowmo"]}, weighting="score")
    by = {r.variant: r for r in result.results}
    assert {s.portfolio_reason for s in by["ensemble"].stats} == {"no_score:lowmo"}
    assert by["ensemble"].measures[0].sessions == 0
    assert by["momo"].measures[0].sessions > 0  # the member that could is still reported
    assert {s.portfolio_reason for s in by["lowmo"].stats} == {"no_score"}


def test_the_haircut_sits_beside_the_in_sample_and_out_of_sample_sharpe() -> None:
    result = _run(
        _world(scale=True),
        ensemble={"variants": ["momo", "lowmo"]},
        oos_class="trend",
        frozen_from=DAYS[3].isoformat(),
    )
    assert result.oos_haircut == 0.45
    (found,) = oos_haircuts(result)
    assert found["variant"] == "ensemble" and found["grid"] == 2
    assert found["in_sample_sharpe"] is not None and found["out_of_sample_sharpe"] is not None
    assert found["expected_sharpe"] == pytest.approx(found["in_sample_sharpe"] * 0.55)
    text = render_edge_report(
        {
            "edge": result.edge_id, "run_id": "r1", "trials": result.trials,
            "universe_snapshot": None, "survivorship": {}, "unclosed_sessions": {},
            "oos_haircut": oos_haircuts(result),
            "rows": records(edge_eval_frame(result, "r1", AS_OF)),
        }
    )  # fmt: skip
    line = next(x for x in text.splitlines() if x.startswith("OOS HAIRCUT"))
    assert "ensemble (an ensemble of 2) h=1: in-sample Sharpe" in line
    assert "after a 45% haircut" in line and "(display only: no verdict reads it)" in line


def test_an_edge_with_no_haircut_class_shows_none_and_a_member_is_never_listed() -> None:
    result = _run(_world(scale=True), frozen_from=DAYS[3].isoformat())
    assert result.oos_haircut is None and oos_haircuts(result) == []
    shown = _run(
        _world(scale=True),
        oos_class="trend",
        frozen_from=DAYS[3].isoformat(),
        ensemble={"variants": ["momo", "lowmo"]},
    )
    assert {h["variant"] for h in oos_haircuts(shown)} == {"ensemble"}  # not momo or lowmo


def test_the_haircut_class_is_not_part_of_what_a_run_measures() -> None:
    a = _run(_world(), ensemble={"variants": ["momo", "lowmo"]})
    b = _run(_world(), ensemble={"variants": ["momo", "lowmo"]}, oos_class="trend")
    assert a.run_hash == b.run_hash  # bookkeeping: display only
    assert _run(_world()).run_hash != a.run_hash  # the ensemble is a run input
