"""A small store for the edge read objects: edge ``drift`` (frozen from FROZEN, implemented by
the site screener ``momo``) with its committed runs. ``write_run`` stores a run the way the
harness does: its record ``edge-eval:<edge>:<owner>`` and its rows in the partition of its range
end (the same end for every run here, so their rows share one partition)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.edges.document import QUALITY_BAR
from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import stamped

START, END, FROZEN = date(2026, 1, 5), date(2026, 9, 30), date(2026, 6, 1)
T = datetime(2026, 10, 2, 3, tzinfo=UTC)

EDGE: dict[str, Any] = {
    "id": "drift", "name": "Drift", "thesis": "Dear names keep rising.", "mechanism": "m",
    "persistence": "p", "schedule": "every_session", "universe": "active", "top_k": 5,
    "screeners": ["momo"], "baselines": [], "status": "candidate",
    "frozen_from": FROZEN, "sources": [{"title": "A paper"}],
    "outcome": {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
                "start_offset_sessions": 1},
    "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
}  # fmt: skip
DOCS: dict[tuple[str, str, str], dict[str, Any]] = {
    ("site", "edges", "drift"): EDGE,
    ("site", "selections", "active"): {
        "name": "active",
        "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
    },
    ("site", "screeners", "momo@1"): {
        "id": "momo", "kind": "screener", "impl": "rules", "version": 1, "selection": "active",
        "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5}},
    },
}  # fmt: skip


def row(
    variant: str, kind: str, hit_rate: float, split: date | None, **changes: Any
) -> dict[str, Any]:
    out = {
        "edge_id": "drift", "user_id": "site", "variant": variant, "role": "screener",
        "edge_variant": None, "horizon_sessions": 20, "slice_kind": kind, "slice_value": kind,
        "range_from": START, "range_to": END, "split_from": split, "exploratory": False,
        "sessions": 12, "picks": 60, "hits": 30, "hit_rate": hit_rate, "base_rate": 0.4,
        "lift": 1.25,
    }  # fmt: skip
    return {**out, **changes}


def write_run(
    backend: MemoryBackend,
    run_id: str,
    split: date | None,
    hit_rate: float,
    owner: str = "site",
    minutes: int = 0,
    status: RunStatus = RunStatus.COMPLETE,
    exploratory: bool | None = None,
) -> None:
    """A run of ``drift``: an ``all`` row and a frozen (or, for another split, a ``split``)
    row for ``momo``; ``minutes`` after T."""
    writer = ResultWriter(backend)
    at = T + timedelta(minutes=minutes)
    kind = "frozen" if split == FROZEN else "split"
    rows = [
        row("momo", "all", 0.3, split, user_id=owner),
        row("momo", kind, hit_rate, split, user_id=owner, exploratory=split != FROZEN),
    ]
    frame = stamped(rows, END, run_id, at, "edge-eval")
    stats = {
        "edge": "drift", "split_from": split.isoformat() if split else None,
        "exploratory": split != FROZEN if exploratory is None else exploratory,
        "range": [START.isoformat(), END.isoformat()], "as_of": "2026-10-01T00:00:00+00:00",
        "trials_counted": 1,
    }  # fmt: skip
    record = RunRecord(run_id, f"edge-eval:drift:{owner}", END, at)
    with writer.publishing(run_id, at):
        writer.write_result("edge_eval", END, run_id, frame, pending=True)
        writer.save_run(record.finish(at, complete=status is RunStatus.COMPLETE, stats=stats))
    if status not in (RunStatus.COMPLETE, RunStatus.PARTIAL):
        record.status = status
        writer.save_run(record)


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


def stores(backend: MemoryBackend, user: str = "me") -> StoreContext:
    return open_stores(StoreReader(backend), MemoryConfigStore(DOCS), UserContext(user))
