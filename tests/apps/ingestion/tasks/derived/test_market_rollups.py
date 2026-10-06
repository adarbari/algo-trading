"""The ``market-rollups`` task (ADR 0047): over three sessions it writes one ``MKT:US`` row
per session for each market group, ``--only`` picks groups (an unknown one is an error), the
``rollups`` task never computes a market group, and the registry exposes the same parameters
as ``rollups``."""

import dataclasses

import pytest

from algotrade.features.site import site_features
from algotrade_ingestion.tasks.derived import market_rollups, rollups
from algotrade_ingestion.tasks.derived.market_rollups import compute_market_rollups
from algotrade_ingestion.tasks.derived.rollups import SITE, compute_rollups
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import MARKET_COUNTS, market_store, only_market_counts


@pytest.fixture(autouse=True)
def with_market(monkeypatch: pytest.MonkeyPatch) -> None:
    only_market_counts(monkeypatch, site_features(SITE))


def test_three_sessions_write_one_market_row_each() -> None:
    writer, reader, days = market_store()
    record = compute_market_rollups(task_ctx(writer), days[-1], start=days[-3], end=days[-1])
    assert record.job == "market-rollups"
    assert record.items == {MARKET_COUNTS.key: "OK: 3 sessions, 3 rows"}
    for day in days[-3:]:
        frame = reader.table(MARKET_COUNTS.table, day)
        assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    assert reader.table(MARKET_COUNTS.table, days[0]) is None  # outside the range


def test_the_registered_task_takes_a_session_a_range_and_only() -> None:
    spec = TASKS["market-rollups"]
    assert spec.module is market_rollups
    assert [p.flags for p in spec.params] == [p.flags for p in TASKS["rollups"].params]
    writer, reader, days = market_store()
    ctx = task_ctx(writer)
    session = days[-1]
    record = run_task("market-rollups", ctx, {"session": session, "only": MARKET_COUNTS.key})
    assert record.items == {MARKET_COUNTS.key: "OK: 1 sessions, 1 rows"}
    assert reader.table(MARKET_COUNTS.table, session) is not None
    ranged = {"session": session, "start": days[-2], "end": session}
    assert run_task("market-rollups", ctx, ranged).items == {
        MARKET_COUNTS.key: "OK: 2 sessions, 2 rows"
    }


def test_only_computes_the_named_group_and_an_unknown_one_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = dataclasses.replace(MARKET_COUNTS, name="market_other")
    monkeypatch.setitem(site_features(SITE).groups, other.key, other)
    writer, reader, days = market_store()
    record = compute_market_rollups(task_ctx(writer), days[-1], only=[other.key])
    assert record.items == {other.key: "OK: 1 sessions, 1 rows"}
    assert reader.table(other.table, days[-1]) is not None
    assert reader.table(MARKET_COUNTS.table, days[-1]) is None
    both = compute_market_rollups(task_ctx(writer), days[-1])
    assert set(both.items) == {MARKET_COUNTS.key, other.key}
    with pytest.raises(KeyError, match="unknown rollups"):
        compute_market_rollups(task_ctx(writer), days[-1], only=["nope@v1"])


def test_each_task_declares_its_entitys_tables_only() -> None:
    assert MARKET_COUNTS.table not in rollups.TABLES
    assert rollups.tables_of("market") == (MARKET_COUNTS.table,)
    assert market_rollups.tables_of("instrument") == rollups.tables_of("instrument")


def test_the_rollups_task_never_computes_a_market_group() -> None:
    writer, reader, days = market_store()
    record = compute_rollups(task_ctx(writer), days[-1])
    assert MARKET_COUNTS.key not in record.items
    assert reader.table(MARKET_COUNTS.table, days[-1]) is None
