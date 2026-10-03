from datetime import UTC, date, datetime

import pytest

from algotrade.core.errors import DataValidationError
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.schemas import spec_for, validate_frame
from tests.storage_helpers import stamped


def test_run_record_json_round_trip() -> None:
    now = datetime(2026, 10, 2, 22, 1, 2, tzinfo=UTC)
    record = RunRecord("r", "job", date(2026, 10, 2), now, RunStatus.PARTIAL, now,
                       {"EQ:A": "OK"}, {"n": 1})  # fmt: skip
    assert RunRecord.from_json(record.to_json()) == record
    assert new_run_id("job", date(2026, 10, 2), now) == "job-2026-10-02-20261002T220102Z"


def test_open_ended_tables_and_null_instrument() -> None:
    assert spec_for("features/x@v1").open_ended
    assert spec_for("results/screen").grain == "results"
    frame = stamped([{"instrument_id": None}], date(2026, 10, 2), "r")
    with pytest.raises(DataValidationError, match="null instrument_id"):
        validate_frame("features/x@v1", frame)
