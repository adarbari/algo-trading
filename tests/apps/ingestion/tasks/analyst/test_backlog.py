"""``check_analyst_backlog``: the in-scope names the FMP rotation has not asked (ADR 0072 decision
6), the measure that NOT_FETCHED hides from the coverage check. WARN only, wired on the step."""

from dataclasses import replace
from datetime import timedelta

from algotrade.data.analyst.reading import KINDS as ANALYST_KINDS
from algotrade.data.analyst.reading import snapshot_window
from algotrade.features.rollups.consensus import analyst_estimates as ae
from algotrade.features.rollups.consensus.analyst_status import (
    LOOKBACK,
    NOT_COVERED,
    NOT_FETCHED,
    OK,
)
from algotrade.services.features import site_features
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.backlog import CHECK, check_analyst_backlog
from algotrade_ingestion.tasks.analyst.snapshot import run
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from tests.apps.ingestion.tasks.analyst.test_snapshot import D1, context, seed
from tests.helpers.analyst_snapshots import FIRST, universe


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


def test_not_fetched_is_never_declared_without_the_backlog_check_on_the_step() -> None:
    """Fitness (ADR 0072 decision 6): a feature that reads NOT_FETCHED as not covered hides the
    never-asked names from the coverage check, so the step that fetches them must grade them."""
    declaring = [
        f.key for f in site_features().features.values() if NOT_FETCHED in f.uncovered_statuses
    ]
    assert declaring, "the analyst groups declare NOT_FETCHED"
    step = next(s for s in NIGHTLY if s.name == "analyst-snapshot")
    assert check_analyst_backlog in step.accept_with


def test_the_groups_read_the_markers_the_task_writes() -> None:
    """The task's own rows, not a hand-built frame: a refused name reads NOT_COVERED, an answered
    one OK, a name the rotation has not reached NOT_FETCHED (the backlog this check counts)."""
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1, "limit": 2})  # two of the three names reach FMP tonight
    snaps = snapshot_window(ctx.reader, ANALYST_KINDS, FIRST).at(D1, LOOKBACK)
    ids = [f"EQ:{s}" for s in ("AAPL", "NVDA", "CHWY")]
    inputs = {ae.SNAPSHOTS: snaps, ae.UNIVERSE: universe(*ids), ae.FINANCIALS: None}
    got = ae.compute(inputs, D1, ae.EstimatesParams()).set_index("instrument_id")
    assert got["estimates_status"].to_dict() == {
        "EQ:AAPL": OK,
        "EQ:CHWY": NOT_COVERED,  # refused: its marker says so
        "EQ:NVDA": NOT_FETCHED,  # not reached tonight: no row, no marker
    }
