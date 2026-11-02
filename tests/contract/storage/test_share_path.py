"""``outcomes/instrument/share_path@v1`` (ADR 0088, E3c-2a): the table is registered keyed by
``(instrument_id, position_key, benchmark)`` and merges runs, and its value rules refuse a measured
row without its exit, an UNMEASURED one with a return, an unknown exit kind or reason, and a
DELISTED exit on a COMPLETE row."""

from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.schemas import SHARE_PATH, share_path_problems, spec_for
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

S = date(2026, 10, 5)


def row(key: str = "k", **changes: Any) -> dict[str, Any]:
    base = {
        "instrument_id": "EQ:A", "ts": pd.Timestamp(S, tz="UTC"), "position_key": key,
        "licence": "open", "window_end": date(2026, 10, 8), "hold_sessions": 3, "benchmark": "SPY",
        "entry_close": 100.0, "exit_session": date(2026, 10, 7), "exit_index": 2,
        "exit_kind": "TAKE_PROFIT", "gross_return": 0.06, "underlying_return": 0.06,
        "benchmark_return": 0.01,
        "max_adverse": 0.0, "exit_unknown_closes": 0, "outcome_status": "COMPLETE",
        "outcome_reason": None,
    }  # fmt: skip
    return {**base, **changes}


UNMEASURED = {
    "exit_session": None, "exit_index": None, "exit_kind": None, "gross_return": None,
    "underlying_return": None, "benchmark_return": None, "max_adverse": None,
    "outcome_status": "UNMEASURED", "outcome_reason": "NO_BAR",
}  # fmt: skip


def test_the_table_is_registered_keyed_by_position_and_merges_runs() -> None:
    spec = spec_for(SHARE_PATH)
    assert spec.runs == "merge" and spec.key == ("instrument_id", "position_key", "benchmark")
    backend = MemoryBackend()
    StoreWriter(backend).write_table(SHARE_PATH, S, "r1", stamped([row("a"), row("b")], S, "r1"))
    later = stamped([row("a", **UNMEASURED)], S, "r2")
    StoreWriter(backend).write_table(SHARE_PATH, S, "r2", later)
    got = backend.tables.read(SHARE_PATH, S)
    assert got is not None
    by_key = got.set_index("position_key")["outcome_status"].to_dict()
    assert by_key == {"a": "UNMEASURED", "b": "COMPLETE"}


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"exit_session": None}, "exit_session is null on a measured"),
        ({**UNMEASURED, "gross_return": 0.1}, "gross_return must be null when UNMEASURED"),
        ({"exit_kind": "EXPIRED"}, "exit_kind must be one of"),
        ({"exit_kind": "DELISTED"}, "DELISTED goes with"),
        ({**UNMEASURED, "outcome_reason": "STALE_CHAIN"}, "outcome_reason must be one of"),
        ({"benchmark_return": None}, "benchmark_return is null on a measured row"),
    ],
)
def test_the_value_rules_refuse_an_inconsistent_row(changes: dict[str, Any], problem: str) -> None:
    frame = pd.DataFrame([row(), row("u", **UNMEASURED), row("d", exit_kind="DELISTED",
                          outcome_status="DELISTED"), row("x", **changes)])  # fmt: skip
    assert any(problem in p for p in share_path_problems(frame))
    assert share_path_problems(frame.iloc[:3]) == []
    with pytest.raises(DataValidationError):
        StoreWriter(MemoryBackend()).write_table(
            SHARE_PATH, S, "r", stamped([row("x", **changes)], S, "r")
        )
