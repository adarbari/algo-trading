"""The setup state (ADR 0088 decision 16, design 2.3): the pure rule over the stored verdict and
the night's gate (ON, OFF, PAUSED, UNKNOWN, each with its reason), and the loader over the four
states with the night read from ``results/edge_picks`` (``pick_edges.load_edge_night``)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.evaluation.pick_edges import EdgeNight
from algotrade.services.read.evaluation.positions import state as module
from algotrade.services.read.evaluation.positions.state import (
    SetupStateCode,
    decide_state,
    load_setup_state,
)
from algotrade.services.read.evaluation.verdict.model import (
    DIAGNOSTIC,
    NOT_ENOUGH,
    NOT_WORKING,
    PROMISING,
    WAITING,
    WORKS,
)
from algotrade.services.read.values import UnknownCode

ON, OFF, PAUSED, UNKNOWN = (
    SetupStateCode.ON,
    SetupStateCode.OFF,
    SetupStateCode.PAUSED,
    SetupStateCode.UNKNOWN,
)
D = date(2026, 11, 2)
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D), user=SimpleNamespace(user_id="me"))
GATE = object()  # any declared gate


@pytest.mark.parametrize(
    ("verdict", "gated", "night", "state"),
    [
        (WORKS, False, None, ON),
        (PROMISING, True, EdgeNight("picked", ""), ON),
        (WORKS, True, EdgeNight("not_decision_day", ""), ON),
        (WORKS, True, EdgeNight("gate_closed", "VIX curve not met"), PAUSED),
        (NOT_WORKING, True, EdgeNight("gate_closed", "VIX curve not met"), OFF),
        (NOT_ENOUGH, False, None, OFF),
        (DIAGNOSTIC, False, None, OFF),
        (None, False, None, UNKNOWN),
        (WAITING, False, None, UNKNOWN),
        (WORKS, True, None, UNKNOWN),
        (WORKS, True, EdgeNight("skipped", "regime unknown"), UNKNOWN),
        (WORKS, True, EdgeNight("unjudged", "a book"), UNKNOWN),
    ],
)
def test_the_rule(
    verdict: str | None, gated: bool, night: EdgeNight | None, state: SetupStateCode
) -> None:
    assert decide_state(verdict, gated, night).state == state


def test_a_closed_gate_pauses_with_the_gates_reason() -> None:
    found = decide_state(WORKS, True, EdgeNight("gate_closed", "VIX curve not met"))
    assert found.reason == "VIX curve not met"


def _load(
    monkeypatch: pytest.MonkeyPatch,
    verdict: str | None,
    rows: list[dict[str, Any]],
    gate: object | None = GATE,
    mine: bool = False,
) -> module.SetupState:
    doc = SimpleNamespace(id="e1", gate=gate)
    summary = None if verdict is None else SimpleNamespace(verdict=verdict)
    frame = pd.DataFrame(rows, columns=["user_id", "edge_id", "screener", "status", "reason"])
    monkeypatch.setattr(module, "parsed_edges", lambda ctx, user: [doc])
    monkeypatch.setattr(module, "load_stored_summary", lambda ctx, edge, bounded: summary)
    monkeypatch.setattr(pick_edges, "partition", lambda ctx, table: frame)
    return load_setup_state(CTX, SimpleNamespace(id="e1", mine=mine))  # type: ignore[arg-type]


def _row(status: str, reason: str | None = None, edge: str = "e1", user: str = "site") -> Any:
    return {"user_id": user, "edge_id": edge, "screener": "s", "status": status, "reason": reason}


def test_the_loader_reads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    found = _load(monkeypatch, WORKS, [_row("picked")])
    assert (found.state, found.unknown) == (ON, None)


def test_the_loader_reads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _load(monkeypatch, NOT_WORKING, [_row("picked")]).state == OFF


def test_the_loader_reads_paused_from_any_screeners_gate_closed_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_row("skipped", "x"), _row("gate_closed", "VIX curve not met")]
    found = _load(monkeypatch, PROMISING, rows)
    assert (found.state, found.reason) == (PAUSED, "VIX curve not met")


def test_the_loader_reads_unknown_with_a_cause_never_a_public_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _load(monkeypatch, WORKS, [_row("skipped", "no options/chain for 2026-11-02")])
    assert (found.state, found.reason) == (UNKNOWN, "")
    assert found.unknown is not None and found.unknown.code == UnknownCode.NOT_STORED


def test_no_stored_verdict_is_unknown_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    found = _load(monkeypatch, None, [])
    assert found.unknown is not None and found.unknown.code == UnknownCode.NOT_RUN


def test_another_edges_or_users_row_is_not_this_setups_night(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_row("gate_closed", "x", edge="e2"), _row("gate_closed", "x", user="u1")]
    assert _load(monkeypatch, WORKS, rows).state == UNKNOWN


def test_an_ungated_setup_does_not_need_its_night(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _load(monkeypatch, WORKS, [], gate=None).state == ON


def test_a_users_own_setup_is_not_applicable(monkeypatch: pytest.MonkeyPatch) -> None:
    found = _load(monkeypatch, WORKS, [_row("picked")], mine=True)
    assert found.unknown is not None and found.unknown.code == UnknownCode.NOT_APPLICABLE
