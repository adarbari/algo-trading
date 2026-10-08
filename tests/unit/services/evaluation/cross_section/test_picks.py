"""``screen_variant`` and ``eligible``: a screener's picks best-first from what was known at the
session (the tie-break order, QUALIFIED only), the edge's universe, the survivorship flag; and
``screen_session`` itself saves nothing."""

from datetime import date, timedelta
from typing import Any

import pytest

from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section import picks
from algotrade.services.evaluation.cross_section.picks import (
    SelectionReads,
    eligible,
    screen_variant,
)
from algotrade.services.screening.run import screen_session
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    DAYS,
    IDS,
    N,
    World,
    build_world,
    screen,
)  # fmt: skip

USER = UserContext("site")


def test_picks_are_qualified_names_best_first_by_the_tie_break(world: World) -> None:
    run = screen_variant(world.reader, resolve_config(world.configs, "momo", USER), DAYS[0])
    assert run.qualified == tuple(reversed(IDS))  # the dearest name first
    assert run.ranking == run.qualified


def test_an_ascending_tie_break_ranks_the_other_way(world: World) -> None:
    configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): screen("asc")}
    )
    run = screen_variant(world.reader, resolve_config(configs, "momo", USER), DAYS[0])
    assert run.qualified == tuple(IDS)


def test_a_rejected_name_is_ranked_last_and_never_a_pick() -> None:
    w = build_world(price_of=lambda d, i: 0.0 if i == N - 1 else 100.0 + 10 * i)
    run = screen_variant(w.reader, resolve_config(w.configs, "momo", USER), DAYS[0])
    assert IDS[-1] not in run.qualified
    assert run.ranking[-1] == IDS[-1]  # ranked (last), not qualified
    assert len(run.qualified) == N - 1


def test_the_eligible_names_are_the_edges_universe_and_pre_snapshot_is_flagged() -> None:
    w = build_world(snapshot=DAYS[3])
    universe = parse_selection(ACTIVE, "active")
    assert eligible(w.reader, universe, DAYS[0]).ids == frozenset(IDS)
    run = screen_variant(w.reader, resolve_config(w.configs, "momo", USER), DAYS[0])
    assert run.pre_snapshot  # the snapshot is after the session: survivorship
    later = screen_variant(w.reader, resolve_config(w.configs, "momo", USER), DAYS[4])
    assert not later.pre_snapshot


def test_screen_session_writes_no_result_and_no_run_record(world: World) -> None:
    config = resolve_config(world.configs, "momo", USER)
    screened = screen_session(world.reader, config, DAYS[0])
    assert screened.rules is not None and len(screened.rules.rows) == N
    assert world.backend.runs.find("screen-momo-site", None) == []
    assert world.reader.table_names().count("results/rule_screen") == 0
    assert screened.universe.snapshot_date == DAYS[0] - timedelta(days=3)


def test_rule_scores_are_tie_break_oriented(world: World) -> None:
    desc = screen_variant(world.reader, resolve_config(world.configs, "momo", USER), DAYS[0])
    assert desc.scores[IDS[3]] == 130.0  # higher is better
    asc_rule = screen("asc")
    configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): asc_rule}
    )
    asc = screen_variant(world.reader, resolve_config(configs, "momo", USER), DAYS[0])
    assert asc.scores[IDS[3]] == -130.0  # ascending: the cheapest scores best
    bare = {k: v for k, v in screen().items() if k != "rank"}
    configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): bare}
    )
    with pytest.raises(ConfigurationError, match="tie_break"):
        screen_variant(world.reader, resolve_config(configs, "momo", USER), DAYS[0])


def test_universes_over_the_same_fields_select_the_same_names_from_one_read(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    cheap = parse_selection(
        {
            "name": "inactive",
            "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "INACTIVE"}]},
        },
        "inactive",
    )
    active = parse_selection(ACTIVE, "active")
    expected = [eligible(world.reader, u, DAYS[0]) for u in (active, cheap)]
    reads: list[date] = []
    real = picks.fields_view

    def counting(reader: Any, fields: Any, day: date, *a: Any, **k: Any) -> Any:
        reads.append(day)
        return real(reader, fields, day, *a, **k)

    monkeypatch.setattr(picks, "fields_view", counting)
    reads_of = SelectionReads(world.reader)
    got = [reads_of.eligible(u, DAYS[0]) for u in (active, cheap)]
    assert got == expected and reads == [DAYS[0]]  # the same fields at one session: one read
    reads_of.eligible(active, DAYS[1])
    assert reads == [DAYS[0], DAYS[1]]
