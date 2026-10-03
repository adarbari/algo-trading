"""Reading the nightly report's inputs back from stored run records (read-only)."""

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.workflows.nightly import records
from tests.helpers import nightly_runs as fx

ORDER = ["universe-build", "shares", "bars", "chains", "rollups", "screens", "quality"]


def _store() -> tuple[StoreReader, StoreWriter]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    steps = fx.summary()["runs"][0]["steps"]
    nightly = RunRecord(
        "nightly-2026-10-02-20261003T132614Z", "nightly", fx.D, fx.START, RunStatus.PARTIAL,
        fx.END, {}, {"steps": dict(sorted(steps.items()))},
    )  # fmt: skip
    older = replace(nightly, run_id="nightly-2026-10-02-20261003T110118Z",
                    started_at=fx.START - timedelta(hours=2), stats={"steps": {}})  # fmt: skip
    for record in (older, nightly, *fx.records().values()):
        writer.save_run(record)
    # Outside the nightly's window: an earlier manual chains run is not this night's.
    stale = replace(fx.records()[(fx.D.isoformat(), "chains")], run_id="option_chains-old",
                    finished_at=fx.START - timedelta(hours=3))  # fmt: skip
    writer.save_run(stale)
    purge = RunRecord(
        "purge_raw-2026-10-02-20261003T135214Z", "purge_raw", fx.D, fx.END, RunStatus.COMPLETE,
        fx.END + timedelta(seconds=2), {}, {"raw_files_removed": 3},
    )  # fmt: skip
    writer.save_run(purge)
    return StoreReader(backend), writer


def test_job_names_come_from_the_task_modules() -> None:
    assert records.job_name("chains") == "option_chains"
    assert records.job_name("quality") == "data_quality"
    assert records.job_name("screens") is None


def test_stored_summary_rebuilds_the_latest_nightly() -> None:
    reader, _ = _store()
    summary = records.stored_summary(reader, fx.D, ORDER)
    assert summary is not None
    assert list(summary["runs"][0]["steps"]) == ORDER
    assert summary["runs"][0]["status"] == "PARTIAL" and summary["status"] == "PARTIAL"
    assert summary["steps"]["purge-raw"]["result"] == {"raw_files_removed": 3}
    assert summary["started_at"] == fx.START.isoformat()
    assert summary["duration_s"] == (fx.END - fx.START).total_seconds() + 2
    assert records.stored_summary(reader, fx.D - timedelta(days=1)) is None


def test_task_records_pick_this_nights_records() -> None:
    reader, _ = _store()
    summary = records.stored_summary(reader, fx.D, ORDER)
    assert summary is not None
    found = records.task_records(reader, summary)
    assert set(found) == {(fx.D.isoformat(), s) for s in ("chains", "shares", "quality")}
    assert found[(fx.D.isoformat(), "chains")].run_id != "option_chains-old"
    assert records.task_records(reader, {"runs": [{"session": "2026-01-02", "steps": {}}]}) == {}


def test_labels_are_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, _ = _store()
    assert records.labels(reader, fx.D, ["0000759828"]) == {}
    assert records.labels(reader, fx.D, ["EQ:BBG000QL42S5"]) == {}  # no reference: no labels

    def reference(reader: Any, on: Any, ids: Any) -> pd.DataFrame:
        return pd.DataFrame({"instrument_id": ["EQ:BBG000QL42S5"], "symbol": ["XMAX"]})

    monkeypatch.setattr(records, "instruments", reference)
    assert records.labels(reader, fx.D, ["EQ:BBG000QL42S5"]) == {"EQ:BBG000QL42S5": "XMAX"}
    report = records.load_report(reader, fx.summary(), 5)
    labelled = [e for g in report.failures for e in g.examples if e.label]
    assert [e.label for e in labelled] == ["XMAX"]


def test_history_is_earlier_nightlies_newest_first() -> None:
    reader, writer = _store()
    earlier = RunRecord(
        "nightly-2026-10-01-20261002T010000Z", "nightly", fx.D - timedelta(days=1),
        fx.START - timedelta(days=1), RunStatus.COMPLETE, fx.END - timedelta(days=1), {},
        {"steps": {"chains": {"status": "COMPLETE", "duration_s": 600.0}}},
    )  # fmt: skip
    writer.save_run(earlier)
    assert records.history(reader, fx.START) == [{"chains": 600.0}]  # the empty one skipped
    assert len(records.history(reader, None)) == 2
    report = records.load_report(reader, fx.summary(), 5, 9000.0)
    chains = next(t for t in report.timings if t.step == "chains")
    assert chains.previous_s == 600.0 and chains.slower
