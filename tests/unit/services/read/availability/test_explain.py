"""``explain``: the chain behind a table with nothing for the session, from the nightly run
record's steps (ADR 0056): source -> step -> table, root first, the leaf last."""

from datetime import UTC, date, datetime

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.features.registry import GROUPS
from algotrade.services.read.availability.cause import (
    Cause,
    CauseLevel,
    UnavailableKind,
    table_cause,
)
from algotrade.services.read.availability.explain import explain, failed_tables
from algotrade.services.read.availability.unavailable import features_of, unavailable_tables
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run

DAY = date(2026, 10, 2)
IBKR_IV = "rollups/instrument/ibkr_iv@v1"


def _stores(steps: dict[str, dict[str, object]] | None) -> StoreContext:
    backend = MemoryBackend()
    if steps is not None:
        run = start_run("nightly", DAY, datetime(2026, 10, 3, 2, tzinfo=UTC))
        run.stats = {"steps": steps}
        backend.runs.save(run)
    return open_stores(StoreReader(backend), MemoryConfigStore({}), UserContext("local"))


def test_a_skipped_step_gives_source_step_table() -> None:
    steps = {
        "ibkr-iv": {
            "status": "SKIPPED",
            "reason": "skipped: IB Gateway unreachable",
            "tables": [IBKR_IV],
        }
    }
    chain = explain(_stores(steps), table_cause(IBKR_IV, "no partition", session=DAY))
    assert [link.level for link in chain.links] == [
        CauseLevel.SOURCE,
        CauseLevel.STEP,
        CauseLevel.TABLE,
    ]
    assert chain.links[0].message == "IB Gateway unreachable"
    assert (chain.links[1].subject, chain.links[1].status) == ("ibkr-iv", "SKIPPED")
    assert chain.links[1].run_id is not None and chain.leaf.subject == IBKR_IV


def test_a_failed_step_names_its_error() -> None:
    steps = {"ibkr-iv": {"status": "FAILED", "error": "RuntimeError: boom", "tables": [IBKR_IV]}}
    chain = explain(_stores(steps), table_cause(IBKR_IV, "no partition", session=DAY))
    assert [link.level for link in chain.links] == [CauseLevel.STEP, CauseLevel.TABLE]
    assert chain.links[0].message == "RuntimeError: boom"


def test_a_succeeded_writer_leaves_the_leaf_alone() -> None:
    steps = {"ibkr-iv": {"status": "SUCCEEDED", "tables": [IBKR_IV]}}
    leaf = table_cause(IBKR_IV, "no partition", session=DAY)
    assert explain(_stores(steps), leaf) == leaf


def test_a_record_from_before_tables_were_recorded_stops_at_the_table() -> None:
    leaf = table_cause(IBKR_IV, "no partition", session=DAY)
    assert explain(_stores({"ibkr-iv": {"status": "FAILED"}}), leaf) == leaf
    assert explain(_stores(None), leaf) == leaf  # no nightly record at all


def test_a_table_without_a_session_is_not_expanded() -> None:
    leaf = table_cause(IBKR_IV, "no partition")
    assert explain(_stores({"ibkr-iv": {"status": "FAILED", "tables": [IBKR_IV]}}), leaf) == leaf


def test_a_failed_input_step_explains_the_rollup_that_reads_it() -> None:
    """A rollup whose writer succeeded but whose input table's step failed: the chain goes
    through the input table (bounded depth)."""
    group = next(g for g in GROUPS.values() if g.inputs and g.entity == "instrument")
    source = group.inputs[0].table
    steps = {
        "feed": {"status": "FAILED", "error": "down", "tables": [source]},
        "rollups": {"status": "SUCCEEDED", "tables": [group.table]},
    }
    chain = explain(_stores(steps), table_cause(group.table, "no rows", session=DAY))
    assert [link.level for link in chain.links] == [
        CauseLevel.STEP,
        CauseLevel.TABLE,
        CauseLevel.TABLE,
    ]
    assert [link.subject for link in chain.links] == ["feed", source, group.table]


def test_unavailable_tables_name_the_features_and_end_the_chain_with_them() -> None:
    table = next(iter(_tables_with_features()))
    [one] = unavailable_tables([table], DAY)
    assert one.kind is UnavailableKind.SYSTEM and one.features == features_of(table)
    assert one.guide_term == "unavailable_system"
    assert one.cause.links[0].subject == table and one.cause.leaf.level is CauseLevel.FEATURE
    assert one.cause.leaf.message.endswith("unavailable")
    assert unavailable_tables(["bars/1d"], DAY)[0].features == ()  # not a feature group's table


def _tables_with_features() -> list[str]:
    return [g.table for g in GROUPS.values()]


def test_a_catch_up_skip_is_a_step_not_a_source() -> None:
    steps = {
        "ibkr-iv": {
            "status": "SKIPPED",
            "reason": "latest closed session only",
            "tables": [IBKR_IV],
        }
    }
    chain = explain(_stores(steps), table_cause(IBKR_IV, "no partition", session=DAY))
    assert [link.level for link in chain.links] == [CauseLevel.STEP, CauseLevel.TABLE]


def test_every_table_link_of_the_leaf_is_tried() -> None:
    steps = {"ibkr-iv": {"status": "FAILED", "error": "down", "tables": [IBKR_IV]}}
    two = Cause(
        (
            table_cause("rollups/instrument/other@v1", "no rows", session=DAY).leaf,
            table_cause(IBKR_IV, "no rows", session=DAY).leaf,
        )
    )
    chain = explain(_stores(steps), two)
    assert chain.links[0].level is CauseLevel.STEP and len(chain.links) == 3


def test_failed_tables_close_over_the_groups_that_read_them() -> None:
    """The feed step was skipped and its rollup SUCCEEDED empty: the rollup is behind a failure,
    so a gap in it is SYSTEM; with the step SUCCEEDED nothing is failed."""
    group = next(g for g in GROUPS.values() if g.inputs and g.inputs[0].table != g.table)
    source = group.inputs[0].table
    skipped = {"feed": {"status": "SKIPPED", "tables": [source]}}
    done = {"feed": {"status": "SUCCEEDED", "tables": [source]}}
    assert group.table in failed_tables(_stores(skipped).reader, DAY)
    assert failed_tables(_stores(done).reader, DAY) == frozenset()
    assert source in failed_tables(_stores(None).reader, DAY, [source])  # no partition
