from datetime import timedelta

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens.ideas import Ideas, load_ideas, screener_priority
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.screens.conftest import CONFIGS, D1, context, write_gated

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


def test_paused_picks_are_no_ideas_but_are_listed_apart_with_their_reason(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ideas = load_ideas(context(reader), 10)
    assert "EQ:BBB" in _ids(ideas)  # beta still picks it
    assert [i.instrument_id for i in ideas.items if i.picks[0].config_id == "alpha"] == ["EQ:AAA"]
    assert ideas.paused_total == 2
    assert [(p.instrument_id, p.result.config_id) for p in ideas.paused] == [
        ("EQ:BBB", "alpha"), ("EQ:DDD", "alpha")
    ]  # fmt: skip
    first = ideas.paused[0]
    assert first.result.decision == "PAUSED" and first.result.reasons == "regime=STRESS: alpha"
    assert first.instrument is not None and first.instrument.symbol == "BBB"
    alpha = next(s for s in ideas.screeners if s.screener.id == "alpha")
    assert alpha.picked == 1 and alpha.run is not None and alpha.run.paused == 2
    assert [r.instrument_id for r in alpha.top] == ["EQ:AAA"]  # a paused row is no top pick


def test_the_paused_section_is_capped_by_the_limit_but_counts_every_row(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ideas = load_ideas(context(reader), 1)
    assert ideas.paused_total == 2 and len(ideas.paused) == 1


def test_an_idea_carries_its_best_picks_regime_and_size(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    by_id = {i.instrument_id: i for i in load_ideas(context(reader), 10).items}
    assert (by_id["EQ:AAA"].regime, by_id["EQ:AAA"].size_multiplier) == ("STRESS", 0.5)
    assert (by_id["EQ:BBB"].regime, by_id["EQ:BBB"].size_multiplier) == (None, None)  # beta's


def test_no_paused_rows_is_an_empty_section(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert (ideas.paused_total, ideas.paused) == (0, ())
