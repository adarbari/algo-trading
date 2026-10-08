"""A screener's track record: the frozen slice of the canonical run only. Exploratory rows never
reach it, a missing canonical run is NOT_RUN with the reason (never an older value), and a
screener no edge lists has none."""

from datetime import date

from algotrade.services.read.evaluation.track_record import load_track_record
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.evaluation.conftest import FROZEN, stores, write_run


def test_exploratory_rows_never_reach_the_track_record(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6, minutes=0)
    write_run(backend, "explore", date(2026, 3, 1), 0.99, minutes=30)  # later, higher
    found = load_track_record(stores(backend), "momo")
    assert found.record is not None and found.not_run is None
    record = found.record
    assert record.run_id == "canon" and record.edge_id == "drift"
    (horizon,) = record.horizons
    assert (horizon.hit_rate, horizon.base_rate, horizon.lift) == (0.6, 0.4, 1.25)
    assert (horizon.sessions, horizon.picks, horizon.horizon_sessions) == (12, 60, 20)
    assert record.split_from == FROZEN and "drift" in record.run_label


def test_only_exploratory_runs_leave_it_not_run(backend: MemoryBackend) -> None:
    write_run(backend, "explore", date(2026, 3, 1), 0.99)
    found = load_track_record(stores(backend), "momo")
    assert found.record is None and found.not_run is not None
    assert found.not_run.code is UnknownCode.NOT_RUN


def test_no_run_at_all_is_not_run(backend: MemoryBackend) -> None:
    found = load_track_record(stores(backend), "momo")
    assert found.record is None and found.not_run is not None
    assert found.not_run.code is UnknownCode.NOT_RUN


def test_a_screener_no_edge_lists_is_not_run(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6)
    found = load_track_record(stores(backend), "other")
    assert found.record is None and found.not_run is not None
    assert found.not_run.code is UnknownCode.NOT_RUN
