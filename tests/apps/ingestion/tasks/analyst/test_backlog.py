"""``check_analyst_backlog``: the in-scope names the FMP rotation has not asked (ADR 0072 decision
6), the measure that NOT_FETCHED hides from the coverage check. WARN only, wired on the step."""

from dataclasses import replace
from datetime import timedelta

from algotrade.features.rollups.consensus.analyst_status import (
    NOT_FETCHED,
)
from algotrade.services.features import site_features
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.backlog import (
    CHECK,
    FINNHUB_CHECK,
    check_analyst_backlog,
    check_finnhub_backlog,
)
from algotrade_ingestion.tasks.analyst.snapshot import run
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from tests.apps.ingestion.tasks.analyst.test_snapshot import D1, context, seed


def limit(ctx: TaskContext, share: float) -> TaskContext:
    return replace(ctx, settings=replace(ctx.settings, max_analyst_backlog=share))


def test_names_the_rotation_has_not_reached_are_a_warning_above_the_limit() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)  # AAPL, NVDA, CHWY in scope
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1, "limit": 1})  # the night's budget reaches one name
    (check,) = check_analyst_backlog(ctx, D1)
    assert (check.name, check.status) == (CHECK, "WARN")
    assert check.data["in_scope"] == 3 and check.data["not_asked"] == 2
    assert "2 of 3 in-scope names not asked of FMP" in check.detail
    assert len(check.data["examples"]) == 2


def test_it_passes_when_the_backlog_is_within_the_limit() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1})  # AAPL and NVDA asked; CHWY refused: its marker is an attempt
    (check,) = check_analyst_backlog(ctx, D1)
    assert check.status == "PASS" and check.data["not_asked"] == 0


def test_a_name_asked_long_ago_is_back_in_the_backlog() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    run(context(writer, D1, []), {"session": D1})
    later = D1 + timedelta(days=4 * 7 + 1)  # past four refresh windows (7 days)
    ctx = context(writer, later, [], budget=0)  # a night with no FMP budget asks nobody
    run(ctx, {"session": later})
    (check,) = check_analyst_backlog(limit(ctx, 0.5), later)
    assert check.status == "WARN" and check.data["not_asked"] == 3


def test_nothing_without_a_finished_run_of_the_session() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    assert check_analyst_backlog(ctx, D1) == []


def test_a_name_that_only_ever_failed_stays_in_the_backlog() -> None:
    """A symbol the vendor rejects with an error is never reached: the features show it
    NOT_FETCHED, so the check must not count it asked."""
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [], broken=frozenset({"NVDA"}))
    run(ctx, {"session": D1})
    (check,) = check_analyst_backlog(ctx, D1)
    assert check.data["not_asked"] == 1 and check.data["examples"] == ["NVDA"]


def test_finnhub_names_the_rotation_has_not_reached_are_a_warning_above_the_limit() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [], per_night=1)  # Finnhub reaches one of the three names
    run(ctx, {"session": D1})
    (check,) = check_finnhub_backlog(ctx, D1)
    assert (check.name, check.status) == (FINNHUB_CHECK, "WARN")
    assert check.data["in_scope"] == 3 and check.data["not_asked"] == 2
    assert "2 of 3 in-scope names not asked of FINNHUB" in check.detail
    (fmp,) = check_analyst_backlog(ctx, D1)  # FMP asked all three: its own measure is separate
    assert fmp.status == "PASS"


def test_finnhub_passes_when_every_name_was_asked_and_an_empty_answer_counts() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [], empty=frozenset({"NVDA"}))
    run(ctx, {"session": D1})
    (check,) = check_finnhub_backlog(ctx, D1)
    assert check.status == "PASS" and check.data["not_asked"] == 0


def test_finnhub_names_that_only_failed_stay_in_the_backlog() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [], broken=frozenset({"NVDA"}))
    run(ctx, {"session": D1})
    (check,) = check_finnhub_backlog(ctx, D1)
    assert check.data["examples"] == ["NVDA"]


def test_finnhub_warns_with_the_reason_when_the_run_skipped_it() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    assert check_finnhub_backlog(ctx, D1) == []  # no finished run of the session
    no_key = replace(ctx, sources={k: v for k, v in ctx.sources.items() if "finnhub" not in k})
    run(no_key, {"session": D1})
    (check,) = check_finnhub_backlog(no_key, D1)  # every name reads NOT_FETCHED: say why
    assert (check.name, check.status) == (FINNHUB_CHECK, "WARN")
    assert check.detail.startswith("Finnhub was not asked tonight: ")
    assert len(check_analyst_backlog(no_key, D1)) == 1


# The groups that declare NOT_FETCHED, and the step and check that grade the names they hide (the
# vendor the group reads: FMP for the estimates and targets, Finnhub for the ratings).
DECLARING = {
    "analyst_estimates@v1": ("analyst-snapshot", check_analyst_backlog),
    "analyst_targets@v1": ("analyst-snapshot", check_analyst_backlog),
    "analyst_ratings@v1": ("analyst-snapshot", check_finnhub_backlog),
    "analyst_revisions@v1": ("analyst-snapshot", check_analyst_backlog),
}


def test_not_fetched_is_declared_only_by_groups_whose_step_runs_the_backlog_check() -> None:
    """Fitness (ADR 0072 decision 6): a feature that reads NOT_FETCHED as not covered hides the
    never-asked names from the coverage check. The declaring groups equal the list above (a new
    source declaring it must add its own check and name it here), and each step runs its check."""
    declaring = {
        f.group for f in site_features().features.values() if NOT_FETCHED in f.uncovered_statuses
    }
    assert declaring == set(DECLARING)
    steps = {s.name: s for s in NIGHTLY}
    for step, check in DECLARING.values():
        assert check in steps[step].accept_with
