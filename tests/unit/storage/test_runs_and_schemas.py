from datetime import UTC, date, datetime

import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id, run_session
from algotrade.storage.tables.schemas import TableSpec, spec_for, table_key, validate_frame
from tests.helpers.stored_frames import stamped


def test_run_record_json_round_trip() -> None:
    now = datetime(2026, 10, 2, 22, 1, 2, tzinfo=UTC)
    record = RunRecord("r", "job", date(2026, 10, 2), now, RunStatus.PARTIAL, now,
                       {"EQ:A": "OK"}, {"n": 1})  # fmt: skip
    assert RunRecord.from_json(record.to_json()) == record
    assert new_run_id("job", date(2026, 10, 2), now) == "job-2026-10-02-20261002T220102Z"


def test_run_session_reads_the_session_back_from_a_run_id() -> None:
    now = datetime(2026, 10, 3, 1, tzinfo=UTC)
    run_id = new_run_id("features-option_liquidity", date(2026, 10, 2), now)
    assert run_session(run_id) == date(2026, 10, 2)
    assert run_session("job-2") is None


def test_open_ended_tables_and_null_instrument() -> None:
    assert spec_for("rollups/instrument/x@v1").open_ended
    assert spec_for("results/screen").grain == "results"
    frame = stamped([{"instrument_id": None}], date(2026, 10, 2), "r")
    with pytest.raises(DataValidationError, match="null instrument_id"):
        validate_frame("rollups/instrument/x@v1", frame)


def test_start_run_and_finish_decide_complete_or_partial() -> None:
    from algotrade.storage.runs import start_run  # noqa: PLC0415

    now = datetime(2026, 10, 2, 22, 1, 2, tzinfo=UTC)
    record = start_run("screen-x-site", date(2026, 10, 2), now)
    assert record.status is RunStatus.RUNNING and record.run_id.startswith("screen-x-site-")
    assert record.finish(now, complete=False, stats={"n": 1}).status is RunStatus.PARTIAL
    assert record.stats == {"n": 1} and record.finished_at == now
    assert start_run("j", date(2026, 10, 2), now).finish(now).status is RunStatus.COMPLETE


def test_column_types_are_checked() -> None:
    from algotrade.storage.tables.schemas import Column  # noqa: PLC0415

    with pytest.raises(ValueError, match="unknown column type"):
        Column("x", "decimal")


def test_tables_declare_how_their_runs_combine() -> None:
    assert spec_for("events/dividend").runs == "merge"
    assert spec_for("events/reference_change").runs == "merge"
    for snapshot in ("bars/1d", "universe", "chains/option_quotes", "results/x", "rollups/daily/y"):
        assert spec_for(snapshot).runs == "snapshot"
    assert spec_for("instruments/reference").runs == "snapshot"
    id_map, history = spec_for("instruments/id_map"), spec_for("instruments/symbol_history")
    assert (id_map.runs, history.runs) == ("merge", "merge")
    assert table_key(id_map, ["instrument_id", "ts", "old_id"]) == ["old_id", "new_id"]
    assert table_key(history, ["instrument_id", "ts"]) == ["figi", "symbol", "valid_from"]
    assert table_key(spec_for("events/x"), ["instrument_id", "ts"]) == ["instrument_id", "ts"]
    with pytest.raises(ValueError, match="run mode"):
        TableSpec("t", "event", ("instrument_id",), runs="append")


def test_known_from_is_declared_on_every_event_table_only() -> None:
    from algotrade.storage.tables.schemas import KNOWN_FROM  # noqa: PLC0415

    for table in ("events/earnings", "events/split", "events/macro_release"):
        column = spec_for(table).column(KNOWN_FROM)
        assert column is not None and column.type == "date" and column.nullable, table
    for table in ("bars/1d", "rollups/instrument/x@v1", "instruments/reference"):
        assert spec_for(table).column(KNOWN_FROM) is None, table
    row = {"instrument_id": "EQ:A", "ts": datetime(2019, 5, 1, tzinfo=UTC)}
    validate_frame(
        "events/earnings", stamped([{**row, KNOWN_FROM: date(2019, 5, 1)}], date(2026, 10, 2), "r")
    )
