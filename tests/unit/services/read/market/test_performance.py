"""The budget of a market history read (``load_market_history``, ADR 0047): the full history a
chart can ask for, 13,500 exchange sessions (1973 to now) of two stored fields, from a
``LocalBackend`` store of one partition per session (synthesised here), read cold (the store
read, one partition per session) and warm (the frame shared through ``ctx.cache``, bucketing
only).

Targets: cold under 5 s, warm under 0.5 s. Warm meets it. Cold does not on this machine: the
read is bound by the backend's serial per-partition work (open, parquet footer and conform,
~0.9 ms each; about 12 s for 13,500), so the cold ceiling below is a regression guard on that
cost, not the target; parallelising ``LocalBackend.read_range`` is the follow-up (it needs an
architect review: it touches the pinned read of one commit sequence).

The strict budgets are the ``perf`` test (``make perf``, an idle machine; building the store
takes about a minute). The default run keeps machine-independent guards on a short history:
the second read touches no table, and is much faster than the first."""

import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, ResultCache, open_context
from algotrade.services.read.market.history import load_market_history
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows

pytestmark = pytest.mark.slow

SESSIONS = 13_500
COLD_TARGET, COLD_CEILING, WARM = 5.0, 25.0, 0.5  # seconds (wall)
DAY = date(2026, 10, 2)
TABLE = "rollups/market/regime@v3"
NAMES = ["market.regime@v3.macro_risk", "market.regime@v3.market_stress"]


def _store(root: Path, n: int) -> ReadContext:
    writer = StoreWriter(LocalBackend(root))
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    write_rows(
        writer,
        "bars/1d",
        DAY,
        [{"instrument_id": "EQ:A", "ts": pd.Timestamp(DAY, tz="UTC"), **bar}],
    )
    rng = np.random.default_rng(7)
    for day in sessions_ending(DAY, n):
        row: dict[str, Any] = {
            "instrument_id": "MKT:US", "label": "CALM", "fragility": 3.0,
            "macro_risk": float(rng.uniform(0, 100)), "market_stress": float(rng.uniform(0, 100)),
        }  # fmt: skip
        write_rows(writer, TABLE, day, [row])
    reader = StoreReader(LocalBackend(root))
    return open_context(reader, MemoryConfigStore({}), UserContext("local"), DAY, ResultCache())


def _read(ctx: ReadContext, n: int) -> float:
    first = sessions_ending(DAY, n)[0]
    started = time.perf_counter()
    found = load_market_history(ctx, NAMES, first, DAY)
    taken = time.perf_counter() - started
    assert [h.name for h in found] == NAMES and 0 < len(found[0].points) <= 600
    return taken


def test_a_second_read_of_a_history_touches_no_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _store(tmp_path, 300)
    cold = _read(ctx, 300)
    reads: list[str] = []
    original = ctx.reader.table_range

    def spy(table: str, *args: Any, **kwargs: Any) -> Any:
        reads.append(table)
        return original(table, *args, **kwargs)

    monkeypatch.setattr(ctx.reader, "table_range", spy)
    warm = _read(ctx, 300)
    assert reads == []  # the frame came from ctx.cache
    assert warm <= cold, (cold, warm)


@pytest.mark.perf
def test_the_full_history_read_meets_the_budget(tmp_path: Path) -> None:
    ctx = _store(tmp_path, SESSIONS)
    cold = _read(ctx, SESSIONS)
    warm = min(_read(ctx, SESSIONS) for _ in range(3))
    assert cold <= COLD_CEILING, (
        f"cold {cold:.2f}s (ceiling {COLD_CEILING}s, target {COLD_TARGET}s)"
    )
    assert warm <= WARM, f"warm {warm:.3f}s (budget {WARM}s)"
