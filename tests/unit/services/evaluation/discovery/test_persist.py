"""``write_winners_study``: a discovery run lands in ``results/winners_study`` as one run, rows
and record together, never half of one."""

from datetime import UTC, datetime

import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.data import StoreReader
from algotrade.services.evaluation.discovery.persist import (
    JOB,
    NOTE,
    winners_frame,
    write_winners_study,
)
from algotrade.services.evaluation.discovery.results import DiscoveryResult
from algotrade.services.evaluation.discovery.tells import find_tells
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import WINNERS_STUDY
from tests.unit.services.evaluation.discovery.conftest import settings
from tests.unit.services.evaluation.discovery.test_tells import frames, independent

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def result() -> DiscoveryResult:
    return find_tells(frames(independent), settings(permutations=10))


def test_the_frame_has_exactly_the_tables_columns_and_names_blocks() -> None:
    found = result()
    frame = winners_frame(found, "r1", NOW)
    assert {c.name for c in WINNERS_STUDY.columns} == set(frame.columns)
    assert set(frame["row_kind"]) >= {"block", "tell", "proposal"}
    assert (frame[frame["row_kind"] == "block"]["block"] >= 0).all()
    assert (frame["blocks"] == found.blocks).all() and "independent" in NOTE


def test_results_atomic_one_run() -> None:
    """One run is one run id on every row and one COMPLETE record carrying the gate; a failure
    between the rows and the record leaves no row visible. Catches: rows readable without their
    run record (a half run the drafts writer would trust)."""
    found = result()
    backend = MemoryBackend()
    writer, reader = ResultWriter(backend), StoreReader(backend)
    last = found.sessions[-1].session
    record = write_winners_study(writer, found, NOW)
    stored = reader.table("results/winners_study", last)
    assert stored is not None and set(stored["run_id"]) == {record.run_id}
    saved = writer.load_run(record.run_id)
    assert saved is not None and saved.job == JOB and saved.stats["passed"] is found.passed
    assert saved.stats["blocks"] == found.blocks

    broken = MemoryBackend()
    bad_writer = ResultWriter(broken)

    def boom(_record: object) -> None:
        raise OSError("disk full")

    bad_writer.save_run = boom  # type: ignore[method-assign]
    with pytest.raises(OSError):
        write_winners_study(bad_writer, found, NOW)
    assert StoreReader(broken).table("results/winners_study", last) is None


def test_an_invalid_frame_publishes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    found = result()
    backend = MemoryBackend()
    monkeypatch.setattr(
        "algotrade.services.evaluation.discovery.persist.winners_frame",
        lambda *a: winners_frame(found, "r1", NOW).assign(surprise=1.0),
    )
    with pytest.raises(DataValidationError):
        write_winners_study(ResultWriter(backend), found, NOW)
    assert StoreReader(backend).table("results/winners_study", found.sessions[-1].session) is None
