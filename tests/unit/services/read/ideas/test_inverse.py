"""The inverse reads: a setup's picks (only when it qualifies) and the setups that picked an
instrument, strongest evidence first."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.services.ideas.setup_rule import CandidatePick
from algotrade.services.read.ideas import inverse
from algotrade.services.read.ideas.of_setup import PICKED, SetupPickSet
from algotrade.services.read.ideas.setups import QualifyingSetup, SessionSetups

CTX: Any = SimpleNamespace(session=SimpleNamespace(date=date(2026, 11, 2)))


def _setup(edge_id: str, level: str, lift: float) -> QualifyingSetup:
    summary = SimpleNamespace(verdict=level, lift_pts=lift, oos_trades=50)
    return QualifyingSetup(
        SimpleNamespace(id=edge_id, name=edge_id), "stocks", summary, "s", 5, None
    )  # type: ignore[arg-type]


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> None:
    weak, strong = _setup("weak", "promising", 1.0), _setup("strong", "works", 5.0)
    sets = {
        "weak": SetupPickSet(weak, PICKED, None, None, (CandidatePick("EQ:X", weak.standing, 2),)),
        "strong": SetupPickSet(
            strong, PICKED, None, None, (CandidatePick("EQ:X", strong.standing, 4),)
        ),
    }
    monkeypatch.setattr(inverse, "load_session_setups", lambda ctx: SessionSetups((weak, strong)))
    monkeypatch.setattr(inverse, "load_pick_set", lambda ctx, s: sets[s.edge.id])


def test_a_setup_that_does_not_qualify_has_no_picks(wired: None) -> None:
    assert inverse.load_picks_of_setup(CTX, "nope") is None
    found = inverse.load_picks_of_setup(CTX, "weak")
    assert found is not None and [p.instrument_id for p in found.picks] == ["EQ:X"]


def test_the_setups_of_an_instrument_come_strongest_first(wired: None) -> None:
    found = inverse.load_setups_of_instrument(CTX, "EQ:X")
    assert [(s.edge_id, s.place) for s in found] == [("strong", 4), ("weak", 2)]
    assert inverse.load_setups_of_instrument(CTX, "EQ:NONE") == ()
