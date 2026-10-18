"""A small store for the time-series tests: the symbol SPY in the reference snapshot, and stored
raw outcomes (benchmark ``none``) at the entry session of every period of the turn-of-month
window over 2024-2025: each window earns +1.0% to +1.2%, the stretches between them a
cycle of -0.2% to +0.2%."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.config.edges.document import QUALITY_BAR, Edge, parse_edge
from algotrade.data import StoreReader
from algotrade.services.evaluation.time_series.periods import Period, periods
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

FIRST, LAST = date(2024, 1, 1), date(2025, 12, 31)
WINDOW, H = "turn_of_month", 4
SPY_ID = "EQ:SPY"
KNOWN = datetime(2026, 10, 5, 22, tzinfo=UTC)  # after the reference snapshot's stamp (T0)
AS_OF = datetime(2026, 10, 20, tzinfo=UTC)


def value_of(period: Period, k: int) -> float:
    """The raw return of the ``k``-th period: windows +1.0..1.2%, stretches -0.2..+0.2%."""
    return 0.010 + 0.001 * (k % 3) if period.inside else -0.002 + 0.001 * (k % 5)


def row(day: date, value: float | None, **changes: Any) -> dict[str, Any]:
    out = {
        "instrument_id": SPY_ID, "ts": pd.Timestamp(f"{day}T20:00Z"), "horizon_sessions": H,
        "window_end": day + timedelta(days=H), "benchmark": "none", "fwd_return": value,
        "fwd_excess_return": None, "fwd_max_return": 0.1, "fwd_max_drawdown": 0.0,
        "fwd_realised_vol": 0.2, "outcome_status": "COMPLETE",
    }  # fmt: skip
    return {**out, **changes}


def timed_edge(**changes: Any) -> Edge:
    doc: dict[str, Any] = {
        "id": "tom", "name": "Turn of the month", "thesis": "Money arrives at month end.",
        "mechanism": "m", "persistence": "p",
        "outcome": {
            "kind": "excess_return", "horizon_sessions": [H], "benchmark": "none",
            "start_offset_sessions": 1,
        },
        "schedule": f"calendar:{WINDOW}", "base": "out_of_window",
        "universe": {"where": {"all": [{"field": "instrument.symbol", "op": "in",
                                        "value": ["SPY"]}]}},
        "top_k": "all", "screeners": [], "status": "candidate",
        "sources": [{"title": "A paper"}],
        "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
    }  # fmt: skip
    doc.update(changes)
    return parse_edge({k: v for k, v in doc.items() if v is not None}, "tom", "tom.toml")


@dataclass
class World:
    backend: MemoryBackend
    writer: StoreWriter
    reader: StoreReader
    configs: MemoryConfigStore
    periods: list[Period]

    @property
    def results(self) -> ResultWriter:
        return ResultWriter(self.backend)

    def write_outcome(self, day: date, rows: list[dict[str, Any]], known: datetime = KNOWN) -> None:
        frame = stamped(rows, day, f"o-{day}", known, "outcomes")
        self.writer.write_table(FORWARD_RETURNS, day, f"o-{day}", frame)


def build_world(
    skip: frozenset[date] = frozenset(),
    changes: dict[date, dict[str, Any]] | None = None,
    known: datetime = KNOWN,
) -> World:
    """The store; ``skip``: entry sessions with no stored outcome; ``changes``: fields to
    override in the row of an entry session."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    snapshot = FIRST - timedelta(days=5)
    universe = universe_rows(["SPY"])
    writer.write_table("universe", snapshot, "u1", stamped(universe, snapshot, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), snapshot, "u1")
    )
    ps = periods(WINDOW, FIRST, LAST)
    w = World(backend, writer, StoreReader(backend), MemoryConfigStore({}), ps)
    for k, p in enumerate(ps):
        if p.entry not in skip:
            extra = (changes or {}).get(p.entry, {})
            w.write_outcome(p.entry, [row(p.entry, value_of(p, k), **extra)], known)
    return w
