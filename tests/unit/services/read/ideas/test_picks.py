"""``load_setup_picks``: a tab's list from its qualifying setups (cap, also-in, groups, the
Unproven state when no setup qualifies, the left-out counts, the watchlist after the cap)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.services.ideas.setup_rule import CandidatePick
from algotrade.services.read.ideas import of_setup, picks
from algotrade.services.read.ideas.setups import NO_VERDICT, QualifyingSetup, SessionSetups

D = date(2026, 11, 2)
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D))


def _setup(edge_id: str, level: str, lift: float, tab: str = "stocks") -> QualifyingSetup:
    summary = SimpleNamespace(verdict=level, lift_pts=lift, oos_trades=100)
    edge = SimpleNamespace(id=edge_id, name=f"Setup {edge_id}")
    return QualifyingSetup(edge, tab, summary, f"scr_{edge_id}", 5, None)  # type: ignore[arg-type]


def _set(setup: QualifyingSetup, ids: list[str], state: str = of_setup.PICKED) -> Any:
    run = SimpleNamespace(run_id=f"run_{setup.edge.id}")
    found = tuple(CandidatePick(i, setup.standing, n) for n, i in enumerate(ids, 1))
    return of_setup.SetupPickSet(setup, state, None, run, found)  # type: ignore[arg-type]


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Any:
    def go(
        sets: list[Any],
        left: dict[tuple[str, str], tuple[str, ...]] | None = None,
        watched: tuple[str, ...] = (),
    ) -> None:
        by_id = {s.setup.edge.id: s for s in sets}
        found = SessionSetups(tuple(s.setup for s in sets), left or {})
        monkeypatch.setattr(picks, "load_session_setups", lambda ctx: found)
        monkeypatch.setattr(of_setup, "load_pick_set", lambda ctx, s: by_id[s.edge.id])
        monkeypatch.setattr(picks, "load_results", lambda ctx, wanted, runs: {})
        monkeypatch.setattr(picks, "earnings_first", lambda ctx, ids: set())
        monkeypatch.setattr(picks, "load_watchlist_ids", lambda ctx: watched)

    return go


def test_the_list_is_capped_after_ranking_and_groups_count_what_they_show(wire: Any) -> None:
    a, b = _setup("a", "works", 4.0), _setup("b", "promising", 9.0)
    wire(
        [_set(a, [f"EQ:A{n:02d}" for n in range(12)]), _set(b, [f"EQ:B{n:02d}" for n in range(8)])]
    )
    found = picks.load_setup_picks(CTX, "stocks")
    assert (found.state, found.total, len(found.ideas)) == (picks.LISTED, 20, picks.CAP)
    assert [i.rank for i in found.ideas] == list(range(1, 16))
    assert [(g.edge_id, g.picked, g.shown) for g in found.groups] == [("a", 12, 12), ("b", 8, 3)]


def test_a_ticker_in_two_setups_lists_the_other_as_also_in(wire: Any) -> None:
    a, b = _setup("a", "works", 4.0), _setup("b", "promising", 9.0)
    wire([_set(a, ["EQ:X"]), _set(b, ["EQ:X", "EQ:Y"])])
    found = picks.load_setup_picks(CTX, "stocks")
    first = found.ideas[0]
    assert (first.instrument_id, first.setup_id) == ("EQ:X", "a")
    assert [(x.edge_id, x.place) for x in first.also_in] == [("b", 1)]


def test_a_tab_with_no_qualifying_setup_is_unproven_with_its_left_out_counts(wire: Any) -> None:
    wire([], {("premium", NO_VERDICT): ("e1", "e2")})
    found = picks.load_setup_picks(CTX, "premium")
    assert (found.state, found.ideas, found.groups) == (picks.UNPROVEN, (), ())
    assert [(c.kind, c.count) for c in found.left_out] == [(NO_VERDICT, 2)]


def test_a_night_that_picks_nothing_is_an_empty_list_never_unproven(wire: Any) -> None:
    a = _setup("a", "works", 4.0)
    wire([_set(a, [], of_setup.NOT_A_DECISION_DAY)])
    found = picks.load_setup_picks(CTX, "stocks")
    assert (found.state, found.ideas) == (picks.LISTED, ())
    assert found.groups[0].state == of_setup.NOT_A_DECISION_DAY


def test_licence_dropped_picks_are_counted_not_named(wire: Any) -> None:
    a = _setup("a", "works", 4.0)
    held = _set(a, [])
    held = of_setup.SetupPickSet(a, of_setup.PICKED, None, held.run, (), ("EQ:1", "EQ:2", "EQ:3"))
    wire([held])
    found = picks.load_setup_picks(CTX, "stocks")
    assert [(c.kind, c.count) for c in found.left_out] == [(picks.LICENCE, 3)]


def test_the_watchlist_keeps_watched_ideas_under_the_cap_and_never_counts_hidden_ones(
    wire: Any,
) -> None:
    """ADR 0083 amendment (c): the filter applies after the cap of 15; ``total`` and ``picked``
    are the unfiltered list's, ``shown`` and the licence count only watched names."""
    a, b = _setup("a", "works", 4.0), _setup("b", "promising", 9.0)
    held = of_setup.SetupPickSet(b, of_setup.PICKED, None, None, (), ("EQ:L1", "EQ:L2"))
    ids = [f"EQ:A{n:02d}" for n in range(20)]
    wire([_set(a, ids), held], watched=("EQ:A03", "EQ:A17", "EQ:L2"))
    found = picks.load_setup_picks(CTX, "stocks")
    assert [(i.instrument_id, i.rank) for i in found.ideas] == [("EQ:A03", 4)]  # A17: past the cap
    assert (found.total, found.watchlist) == (20, picks.CAP)
    assert [(g.edge_id, g.picked, g.shown) for g in found.groups] == [("a", 20, 1), ("b", 0, 0)]
    assert [(c.kind, c.count) for c in found.left_out] == [(picks.LICENCE, 1)]


def test_no_watchlist_is_no_filter(wire: Any) -> None:
    a = _setup("a", "works", 4.0)
    wire([_set(a, ["EQ:X", "EQ:Y"])])
    found = picks.load_setup_picks(CTX, "stocks")
    assert ([i.instrument_id for i in found.ideas], found.watchlist) == (["EQ:X", "EQ:Y"], None)
