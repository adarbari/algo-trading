from datetime import timedelta

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens.ideas import Ideas, load_ideas, screener_priority
from algotrade.services.read.values import UnknownCode
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.screens.conftest import CONFIGS, D1, context

PRIORITY = {("me", "preferences", "preferences"): {"ideas": {"priority": ["beta", "nope"]}}}


def _ids(found: Ideas) -> list[str]:
    return [i.instrument_id for i in found.items]


def test_no_priority_ranks_by_score_then_tie_break(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert (ideas.session, ideas.priority, ideas.total) == (D1, (), 3)
    # Unlisted screeners share one place: score decides (BBB 90 by beta, AAA 50, DDD 10).
    assert _ids(ideas) == ["EQ:BBB", "EQ:AAA", "EQ:DDD"]
    first = ideas.items[0]
    assert first.rank == 1 and first.instrument is not None and first.instrument.symbol == "BBB"
    assert [(p.config_id, p.decision) for p in first.picks] == [
        ("beta", "QUALIFIED"), ("alpha", "WATCH")
    ]  # fmt: skip


def test_priority_first_and_the_users_screen_wins(reader: StoreReader) -> None:
    ideas = load_ideas(context(reader, PRIORITY), 10)
    assert ideas.priority == ("beta", "nope")
    assert _ids(ideas) == ["EQ:BBB", "EQ:DDD", "EQ:AAA"]  # beta's picks first
    # The site's beta run (CCC 99) is not me's beta: CCC is no idea.
    assert "EQ:CCC" not in _ids(ideas)
    assert [s.screener.id for s in ideas.screeners] == ["beta", "alpha", "gamma"]


def test_screeners_count_the_whole_run_and_say_not_run(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 1)  # one item shown; counts are over the run
    assert _ids(ideas) == ["EQ:BBB"] and ideas.total == 3
    by_id = {s.screener.id: s for s in ideas.screeners}
    alpha = by_id["alpha"]
    assert alpha.run is not None and alpha.run.run_id == "r1"
    assert (alpha.picked, alpha.not_run) == (2, None)
    assert [r.instrument_id for r in alpha.top] == ["EQ:AAA", "EQ:BBB"]  # picks by rank
    gamma = by_id["gamma"]  # ran on D0 only: no lookback
    assert (gamma.run, gamma.picked, gamma.top) == (None, 0, ())
    assert gamma.not_run is not None and gamma.not_run.code is UnknownCode.NOT_RUN


def test_a_session_nothing_ran_for(reader: StoreReader) -> None:
    later = open_context(
        reader, MemoryConfigStore(CONFIGS), UserContext("me"), D1 + timedelta(days=1)
    )
    ideas = load_ideas(later, 10)
    assert (ideas.items, ideas.total) == ((), 0)
    assert all(s.not_run is not None for s in ideas.screeners)


def test_priority_is_read_from_the_users_preferences(reader: StoreReader) -> None:
    assert screener_priority(context(reader, PRIORITY)) == ("beta", "nope")
    assert screener_priority(context(reader)) == ()
