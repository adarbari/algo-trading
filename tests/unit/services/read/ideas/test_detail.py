"""``load_idea_detail``: one idea's page: the setup shown (asked for, else the best), the sections
filled from the setup, a ticker no qualifying setup picked has no page, a section with a missing
input says why (ADR 0083 amendment 2026-11-01 (b))."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.services.ideas.setup_rule import CandidatePick
from algotrade.services.read.evaluation.positions.exit_rule import ExitRule
from algotrade.services.read.ideas import detail, of_setup
from algotrade.services.read.ideas.inverse import InstrumentSetup
from algotrade.services.read.ideas.setups import QualifyingSetup, SessionSetups
from algotrade.services.read.values import Unknown, UnknownCode

D = date(2026, 11, 2)  # a Monday
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D))


def _setup(edge_id: str, level: str) -> QualifyingSetup:
    summary = SimpleNamespace(
        verdict=level,
        lift_pts=3.0,
        lift=0.1,
        oos_trades=90,
        trades=200,
        result="held out",
        basis="b",
    )
    edge = SimpleNamespace(
        id=edge_id, name=edge_id, thesis="why", mechanism="how", persistence="because"
    )
    return QualifyingSetup(edge, "stocks", summary, f"s_{edge_id}", 5, None)  # type: ignore[arg-type]


STRONG, WEAK = _setup("strong", "works"), _setup("weak", "promising")


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"events": []}
    monkeypatch.setattr(
        detail, "resolve_id", lambda ctx, key: "EQ:X" if key in ("X", "EQ:X") else None
    )
    found = (
        InstrumentSetup("strong", "strong", "stocks", "works", 2),
        InstrumentSetup("weak", "weak", "stocks", "promising", 1),
    )
    monkeypatch.setattr(detail, "load_setups_of_instrument", lambda ctx, iid: found)
    monkeypatch.setattr(detail, "load_session_setups", lambda ctx: SessionSetups((STRONG, WEAK)))
    run = SimpleNamespace(run_id="r")
    monkeypatch.setattr(
        of_setup,
        "load_pick_set",
        lambda ctx, s: of_setup.SetupPickSet(
            s,
            of_setup.PICKED,
            None,
            run,
            (CandidatePick("EQ:X", s.standing, 1),),  # type: ignore[arg-type]
        ),
    )
    result = SimpleNamespace(decision="QUALIFIED", criteria=("c1",), columns=(), instrument=None)
    monkeypatch.setattr(detail, "load_results", lambda ctx, wanted, runs: {("r", "EQ:X"): result})
    monkeypatch.setattr(detail, "display_metrics", lambda r: ())
    monkeypatch.setattr(detail, "earnings_first", lambda ctx, ids: set())
    monkeypatch.setattr(detail, "watch_out", lambda r, early: ())
    monkeypatch.setattr(detail, "load_instruments", lambda ctx, ids: {})
    monkeypatch.setattr(
        detail,
        "exit_rule_at",
        lambda ctx, edge, iid, bounded=False: ExitRule(edge.id, None, seen.get("hold", 5)),
    )
    events = SimpleNamespace(
        gaps=(),
        ahead=(
            SimpleNamespace(kind="own_earnings", date=date(2026, 11, 5)),
            SimpleNamespace(kind="own_earnings", date=date(2026, 12, 20)),
            SimpleNamespace(kind="macro_release", date=date(2026, 11, 4)),
        ),
    )
    monkeypatch.setattr(detail, "load_instrument_events", lambda ctx, ids, days: {"EQ:X": events})
    seen["bounded"] = []
    return seen


def test_the_best_setup_is_shown_by_default_and_the_one_asked_for_when_given(wired: Any) -> None:
    assert detail.load_idea_detail(CTX, "X").setup.edge_id == "strong"  # type: ignore[union-attr]
    asked = detail.load_idea_detail(CTX, "EQ:X", "weak")
    assert asked is not None and asked.setup.edge_id == "weak"
    assert [s.edge_id for s in asked.setups] == ["strong", "weak"]


def test_an_unknown_name_or_a_setup_that_did_not_pick_it_has_no_page(wired: Any) -> None:
    assert detail.load_idea_detail(CTX, "NOPE") is None
    assert detail.load_idea_detail(CTX, "X", "other") is None


def test_the_sections_come_from_the_setup_and_the_pick(wired: Any) -> None:
    found = detail.load_idea_detail(CTX, "X")
    assert found is not None
    assert (found.why.thesis, found.why.decision, found.why.criteria) == (
        "why",
        "QUALIFIED",
        ("c1",),
    )
    assert (found.evidence.level, found.evidence.oos_trades, found.learn) == ("works", 90, "strong")
    assert found.exit_rule.hold_sessions == 5


def test_only_the_names_own_earnings_before_the_hold_ends_are_risks(wired: Any) -> None:
    found = detail.load_idea_detail(CTX, "X")
    assert found is not None
    assert found.risks.hold_ends == date(2026, 11, 9)  # five sessions after Mon 2 Nov
    assert [e.date for e in found.risks.events] == [date(2026, 11, 5)]
    assert found.risks.persistence == "because"


def test_with_no_hold_known_no_events_are_listed_and_the_reason_is_carried(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    why = Unknown(UnknownCode.NOT_RUN, None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        detail,
        "exit_rule_at",
        lambda ctx, edge, iid, bounded=False: ExitRule(edge.id, None, None, why),
    )
    found = detail.load_idea_detail(CTX, "X")
    assert found is not None
    assert (found.risks.hold_ends, found.risks.events, found.risks.unknown) == (None, (), why)


def test_the_exit_rule_is_read_bounded_to_the_session(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[bool] = []

    def rule(ctx: Any, edge: Any, iid: str, bounded: bool = False) -> ExitRule:
        asked.append(bounded)
        return ExitRule(edge.id, None, 5)

    monkeypatch.setattr(detail, "exit_rule_at", rule)
    detail.load_idea_detail(CTX, "X")
    assert asked == [True]


def test_an_unreadable_pick_row_and_a_missing_earnings_source_are_unknown_not_empty(
    wired: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detail, "load_results", lambda ctx, wanted, runs: {})
    found = detail.load_idea_detail(CTX, "X")
    assert found is not None and found.why.unknown is not None and found.why.criteria == ()
    gap = SimpleNamespace(
        part="own_earnings",
        instrument_id="EQ:X",
        unknown=Unknown(UnknownCode.NO_ROW, None),  # type: ignore[arg-type]
    )
    events = SimpleNamespace(ahead=(), gaps=(gap,))
    monkeypatch.setattr(detail, "load_instrument_events", lambda ctx, ids, days: {"EQ:X": events})
    risky = detail.load_idea_detail(CTX, "X")
    assert risky is not None and risky.risks.unknown is gap.unknown
    monkeypatch.setattr(detail, "load_instrument_events", lambda ctx, ids, days: {})
    none = detail.load_idea_detail(CTX, "X")
    assert none is not None and none.risks.unknown is not None
