"""``load_pick_set``: a setup's own picks from the public ``pick_edges`` read, the night's meaning
when nobody counted (UNKNOWN is never "no picks"), and the licence filter."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.evaluation.pick_edges import PickEdge
from algotrade.services.read.ideas import of_setup
from algotrade.services.read.ideas.setups import QualifyingSetup
from algotrade.services.read.screens.runs import LatestRun

D = date(2026, 11, 2)
RUN = SimpleNamespace(run_id="r1", config_id="scr")
SETUP = QualifyingSetup(
    SimpleNamespace(id="e1", name="Edge one"),  # type: ignore[arg-type]
    "stocks",
    SimpleNamespace(verdict="works", lift_pts=3.0, oos_trades=100),  # type: ignore[arg-type]
    "scr",
    5,
    None,
)
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D))


def _edge(code: str, place: int | None = None, who: str = "e1") -> PickEdge:
    return PickEdge(who, "n", code == pick_edges.COUNTS, code, None, place)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    ids: list[str],
    answer: dict[str, tuple[PickEdge, ...]],
    withheld: frozenset[str] = frozenset(),
    run: Any = RUN,
) -> None:
    rows = pd.DataFrame({"instrument_id": ids, "decision": ["QUALIFIED"] * len(ids)})
    monkeypatch.setattr(
        of_setup, "load_latest_runs", lambda ctx, keys: {keys[0]: LatestRun(run, None)}
    )
    monkeypatch.setattr(of_setup, "run_picks", lambda ctx, r: rows)
    monkeypatch.setattr(of_setup, "run_withheld", lambda ctx, r: withheld)
    monkeypatch.setattr(pick_edges, "load_pick_edges", lambda ctx, r, picks: answer)


def test_the_setups_own_picks_come_in_place_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(
        monkeypatch,
        ["EQ:A", "EQ:B", "EQ:C"],
        {
            of_setup.PROBE: (_edge(pick_edges.NOT_COUNTED),),
            "EQ:A": (_edge(pick_edges.NOT_COUNTED),),
            "EQ:B": (_edge(pick_edges.COUNTS, 1),),
            "EQ:C": (_edge(pick_edges.COUNTS, 2), _edge(pick_edges.COUNTS, 1, "other")),
        },
    )
    found = of_setup.load_pick_set(CTX, SETUP)
    assert found.state == of_setup.PICKED
    assert [(p.instrument_id, p.place) for p in found.picks] == [("EQ:B", 1), ("EQ:C", 2)]


@pytest.mark.parametrize("code", [pick_edges.NOT_STORED, pick_edges.UNJUDGED])
def test_a_night_the_step_did_not_store_is_unknown_never_empty(
    monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    _wire(monkeypatch, ["EQ:A"], {of_setup.PROBE: (_edge(code),), "EQ:A": (_edge(code),)})
    found = of_setup.load_pick_set(CTX, SETUP)
    assert found.state == of_setup.UNKNOWN and found.unknown is not None and not found.picks


def test_not_a_decision_day_and_a_decision_day_that_picked_nothing_are_empty_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, [], {of_setup.PROBE: (_edge(pick_edges.NOT_A_DECISION_DAY),)})
    assert of_setup.load_pick_set(CTX, SETUP).state == of_setup.NOT_A_DECISION_DAY
    _wire(monkeypatch, [], {of_setup.PROBE: (_edge(pick_edges.NOT_COUNTED),)})
    assert of_setup.load_pick_set(CTX, SETUP).state == of_setup.NOTHING_PICKED


def test_a_basis_screener_with_no_run_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, [], {}, run=None)
    found = of_setup.load_pick_set(CTX, SETUP)
    assert found.state == of_setup.UNKNOWN and found.run is None


def test_picks_of_a_run_the_viewer_may_not_rank_are_dropped_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(
        monkeypatch,
        ["EQ:A"],
        {of_setup.PROBE: (_edge(pick_edges.NOT_COUNTED),), "EQ:A": (_edge(pick_edges.COUNTS, 1),)},
        withheld=frozenset({"iv_rank"}),
    )
    found = of_setup.load_pick_set(CTX, SETUP)
    assert found.picks == () and found.dropped == 1
