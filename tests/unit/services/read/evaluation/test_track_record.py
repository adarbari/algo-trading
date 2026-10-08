"""A screener's track record: the frozen slice of the canonical run only. Exploratory rows never
reach it, a missing canonical run is NOT_RUN with the reason (never an older value), and a
screener no edge lists has none."""

from datetime import date

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import open_stores
from algotrade.services.read.evaluation.track_record import load_track_records
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    EDGE,
    FROZEN,
    session_ctx,
    stores,
    write_run,
)


def one(backend: MemoryBackend, screener: str = "momo"):  # type: ignore[no-untyped-def]
    (found,) = load_track_records(stores(backend), screener)
    return found


def test_exploratory_rows_never_reach_the_track_record(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6, minutes=0)
    write_run(backend, "explore", date(2026, 3, 1), 0.99, minutes=30)  # later, higher
    record = one(backend)
    assert record.not_run is None and record.run_id == "canon" and record.edge_id == "drift"
    (horizon,) = record.horizons
    assert (horizon.hit_rate, horizon.base_rate, horizon.lift) == (0.6, 0.4, 1.25)
    assert (horizon.sessions, horizon.picks, horizon.horizon_sessions) == (12, 60, 20)
    assert record.split_from == FROZEN and record.run_label and "drift" in record.run_label


def test_only_exploratory_runs_leave_it_not_run(backend: MemoryBackend) -> None:
    write_run(backend, "explore", date(2026, 3, 1), 0.99)
    record = one(backend)
    assert record.run_id is None and record.horizons == ()
    assert record.not_run is not None and record.not_run.code is UnknownCode.NOT_RUN


def test_no_run_at_all_is_not_run(backend: MemoryBackend) -> None:
    record = one(backend)
    assert record.not_run is not None and record.not_run.code is UnknownCode.NOT_RUN


def test_a_screener_no_edge_lists_has_no_entry(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6)
    assert load_track_records(stores(backend), "other") == ()


def test_a_screener_in_two_edges_gets_two_entries_by_edge_id(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6)
    docs = {**DOCS, ("site", "edges", "alpha"): {**EDGE, "id": "alpha", "name": "Alpha"}}
    ctx = open_stores(StoreReader(backend), MemoryConfigStore(docs), UserContext("me"))
    first, second = load_track_records(ctx, "momo")
    assert (first.edge_id, first.edge_name, first.not_run is not None) == ("alpha", "Alpha", True)
    assert (second.edge_id, second.run_id, second.not_run) == ("drift", "canon", None)


def test_after_session_is_disclosed_on_the_track_record(backend: MemoryBackend) -> None:
    write_run(backend, "canon", FROZEN, 0.6)  # committed 2026-10-02
    (before,) = load_track_records(session_ctx(stores(backend), date(2026, 9, 30)), "momo")
    assert before.after_session is True
    (without,) = load_track_records(stores(backend), "momo")
    assert without.after_session is False
