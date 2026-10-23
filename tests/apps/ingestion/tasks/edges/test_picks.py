"""The ``edge-picks`` task (ADR 0081): the stored rows are the harness's picks, a re-run writes
nothing new (resumable by the store), the whole session is one publish, and the acceptance check
fails when an edge has no row."""

import itertools
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.edges import picks as task
from algotrade_ingestion.tasks.framework import entries_ops
from algotrade_ingestion.workflows.nightly.nightly import skip_reason
from tests.helpers.ingest_fakes import task_ctx
from tests.unit.services.evaluation.cross_section.conftest import (
    ACTIVE,
    AS_OF,
    DAYS,
    World,
    build_world,
    edge_document,
    screen,
    world,  # noqa: F401  (the fixture)
)

DAY = DAYS[0]
CLOCK = (AS_OF.replace(hour=12) + timedelta(minutes=i) for i in itertools.count())
NO_N18 = {"where": {"all": [{"field": "instrument.symbol", "op": "not_in", "value": ["N18"]}]}}


def configs(**second: Any) -> MemoryConfigStore:
    return MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "momo"): screen(),
            ("site", "edges", "drift"): edge_document(),
            ("site", "edges", "narrow"): edge_document(
                id="narrow", name="Narrow", universe=NO_N18, **second
            ),
        }
    )


def run(w: World, cfg: MemoryConfigStore, session=DAY, **options: Any):  # type: ignore[no-untyped-def]
    tick = next(CLOCK)
    ctx = replace(task_ctx(w.writer, w.reader, clock=lambda: tick), configs=cfg)
    return task.store_picks(ctx, session, task.Options(**options))


def rows(w: World, day=DAY) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    found = w.reader.table(task.TABLE, day)
    return pd.DataFrame() if found is None else found


def picks_of(w: World, edge_id: str) -> list[str]:
    found = rows(w)
    return list(found[found["edge_id"] == edge_id].iloc[0]["pick_ids"])


def test_a_run_stores_each_edges_picks_of_the_session(world: World) -> None:  # noqa: F811
    record = run(world, configs())
    assert record.status is RunStatus.COMPLETE and record.stats["written"] == 2
    found = rows(world)
    assert sorted(found["edge_id"]) == ["drift", "narrow"]
    assert set(found["user_id"]) == {"site"} and set(found["source"]) == {"edge-picks"}
    assert set(found["status"]) == {"picked"} and set(found["screener"]) == {"momo"}
    assert picks_of(world, "drift") == [f"EQ:N{i}" for i in (19, 18, 17, 16, 15)]
    assert picks_of(world, "narrow") == [f"EQ:N{i}" for i in (19, 17, 16, 15, 14)]  # no N18


def test_a_second_run_decides_and_writes_nothing_that_is_stored(world: World) -> None:  # noqa: F811
    run(world, configs())
    again = run(world, configs())
    assert again.stats["written"] == 0
    assert len(rows(world)) == 2


def test_a_run_finishes_what_an_earlier_one_left(world: World) -> None:  # noqa: F811
    run(world, configs(), edge="drift")
    assert list(rows(world)["edge_id"]) == ["drift"]
    run(world, configs())
    assert sorted(rows(world)["edge_id"]) == ["drift", "narrow"]


def test_a_window_stores_every_session_in_one_run(world: World) -> None:  # noqa: F811
    record = run(world, configs(), session=DAYS[2], start=DAYS[0], end=DAYS[2])
    assert record.stats["written"] == 2 * len(record.stats["sessions"])
    assert all(len(rows(world, d)) == 2 for d in DAYS[:3])


def test_a_session_whose_data_is_missing_is_a_skipped_row_not_a_missing_one() -> None:
    w = build_world(no_features=[DAYS[3]])
    record = run(w, configs(), session=DAYS[3])
    assert record.status is RunStatus.COMPLETE
    found = rows(w, DAYS[3])
    assert set(found["status"]) == {"skipped"} and all(found["reason"])
    assert record.stats["skipped"]


def test_the_acceptance_check_fails_without_a_run_and_without_rows(world: World) -> None:  # noqa: F811
    assert task.check_edge_picks(world.reader, DAY, None)[0].status == "FAIL"  # type: ignore[arg-type]
    run(world, configs())
    (check,) = task.check_edge_picks(world.reader, DAY, None)  # type: ignore[arg-type]
    assert check.status == "PASS"


def test_an_unknown_edge_is_refused(world: World) -> None:  # noqa: F811
    with pytest.raises(ConfigurationError):
        run(world, configs(), edge="nope")


def test_the_task_is_skipped_with_no_config_store(world: World) -> None:  # noqa: F811
    ctx = replace(task_ctx(world.writer, world.reader), configs=None)
    assert skip_reason("edge-picks", ctx) is not None
    assert entries_ops.run_edge_picks  # the registered entry


def test_a_skipped_row_is_decided_again_by_the_next_run() -> None:
    w = build_world(no_features=[DAYS[3]])
    run(w, configs(), session=DAYS[3])
    assert set(rows(w, DAYS[3])["status"]) == {"skipped"}
    w.write_features(DAYS[3])  # the data arrives late
    again = run(w, configs(), session=DAYS[3])
    assert again.stats["written"] == 2 and set(rows(w, DAYS[3])["status"]) == {"picked"}
