"""One small store for the harness tests: 20 names, a rule screen ``momo`` that qualifies every
name and ranks it by ``underlying_price`` (name i costs 100 + 10 i), and stored outcomes whose
excess return rises with i (half the names hit), over the sessions of Sept 1-10 2026."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.document import QUALITY_BAR, Edge, parse_edge
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import FORWARD_RETURNS
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

DAYS = sessions_between(date(2026, 9, 1), date(2026, 9, 10))
N = 20
IDS = [f"EQ:N{i:02d}" for i in range(N)]
FEATURE = "rollups/instrument/option_liquidity@v1"
KNOWN = datetime(2026, 9, 30, 22, tzinfo=UTC)
AS_OF = datetime(2026, 10, 5, tzinfo=UTC)
ACTIVE = {
    "name": "active",
    "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
}


PRICE = "rollup.option_liquidity@v1.underlying_price"


def screen(rank: str = "desc") -> dict[str, Any]:
    return {
        "id": "momo",
        "kind": "screener",
        "impl": "rules",
        "version": 1,
        "selection": "active",
        "screening": {"min_coverage": 0.5},
        "criteria": {"price": {"field": PRICE, "op": "gt", "value": 0}},
        "rank": {"tie_break": PRICE, "tie_break_order": rank},
    }


def edge_document(**changes: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "id": "drift", "name": "Drift", "thesis": "Dear names keep rising.",
        "mechanism": "m", "persistence": "p",
        "outcome": {"kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY"},
        "schedule": "every_session", "universe": "active", "top_k": 5, "screeners": ["momo"],
        "status": "candidate", "sources": [{"title": "A paper"}],
        "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
    }  # fmt: skip
    doc.update(changes)
    return {k: v for k, v in doc.items() if v is not None}


def edge(**changes: Any) -> Edge:
    return parse_edge(edge_document(**changes), "drift", "drift.toml")


def outcome_row(iid: str, i: int, day: date, **changes: Any) -> dict[str, Any]:
    row = {
        "instrument_id": iid, "ts": pd.Timestamp(f"{day}T20:00Z"), "horizon_sessions": 2,
        "window_end": day + timedelta(days=2), "benchmark": "SPY", "fwd_return": (i - 9.5) / 100,
        "fwd_excess_return": (i - 9.5) / 100, "fwd_max_return": 0.1, "fwd_max_drawdown": 0.0,
        "fwd_realised_vol": 0.2, "outcome_status": "COMPLETE",
    }  # fmt: skip
    return {**row, **changes}


@dataclass
class World:
    backend: MemoryBackend
    writer: StoreWriter
    reader: StoreReader
    configs: MemoryConfigStore

    @property
    def results(self) -> ResultWriter:
        return ResultWriter(self.backend)

    def write_outcomes(
        self, day: date, rows: list[dict[str, Any]], known: datetime = KNOWN
    ) -> None:
        frame = stamped(rows, day, f"o-{day}", known, "outcomes")
        self.writer.write_table(FORWARD_RETURNS, day, f"o-{day}", frame)

    def write_features(
        self, day: date, price_of: Callable[[int], float] = lambda i: 100.0 + 10 * i
    ) -> None:
        rows = [
            {"instrument_id": iid, "underlying_price": price_of(i)} for i, iid in enumerate(IDS)
        ]
        self.writer.write_table(FEATURE, day, f"f-{day}", stamped(rows, day, f"f-{day}"))


def build_world(
    days: Sequence[date] = DAYS,
    price_of: Callable[[date, int], float] | None = None,
    snapshot: date | None = None,
    closed: Sequence[date] | None = None,
    rows_of: Callable[[date], list[dict[str, Any]]] | None = None,
) -> World:
    """The store over ``days``; ``price_of(day, i)`` overrides name i's price on a day; the
    universe snapshot is ``snapshot`` (default: before the first day); outcomes are stored
    for the ``closed`` days only (default: all), with ``rows_of(day)`` as the rows."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    universe = universe_rows([f"N{i:02d}" for i in range(N)])
    snapshot = snapshot or days[0] - timedelta(days=3)
    writer.write_table("universe", snapshot, "u1", stamped(universe, snapshot, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), snapshot, "u1")
    )
    configs = MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): screen()}
    )
    w = World(backend, writer, StoreReader(backend), configs)
    for day in days:
        w.write_features(
            day, (lambda i, d=day: price_of(d, i)) if price_of else lambda i: 100.0 + 10 * i
        )
        if closed is None or day in closed:
            default = [outcome_row(iid, i, day) for i, iid in enumerate(IDS)]
            w.write_outcomes(day, rows_of(day) if rows_of else default)
    return w


@pytest.fixture
def world() -> World:
    return build_world()
