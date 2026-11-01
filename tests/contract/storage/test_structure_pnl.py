"""``outcomes/option/structure_pnl@v2`` (ADR 0088, design 2.5): the table round-trips its list
columns through every backend, runs merge per ``(instrument_id, position_key)``, and its value rules
refuse a COMPLETE trade without its exit and an UNMEASURED one with a P&L."""

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import STRUCTURE_PNL, spec_for, structure_pnl_problems
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, structure_pnl_row

S = date(2026, 10, 5)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def test_the_table_is_registered_keyed_by_position_and_merges_runs(backend: Backend) -> None:
    spec = spec_for(STRUCTURE_PNL)
    assert spec.runs == "merge" and spec.key == ("instrument_id", "position_key")
    first = stamped([structure_pnl_row(key="a"), structure_pnl_row(key="b")], S, "r1")
    later = stamped([structure_pnl_row(key="a", pnl_mid=0.9)], S, "r2")
    StoreWriter(backend).write_table(STRUCTURE_PNL, S, "r1", first)
    StoreWriter(backend).write_table(STRUCTURE_PNL, S, "r2", later)
    got = backend.tables.read(STRUCTURE_PNL, S)
    assert got is not None
    by_key = got.set_index("position_key")
    assert set(by_key.index) == {"a", "b"} and by_key.at["a", "pnl_mid"] == 0.9
    assert list(by_key.at["b", "leg_strikes"]) == [95.0]
    assert list(by_key.at["b", "leg_expiries"]) == [date(2026, 11, 20)]


def test_a_null_leg_list_element_and_a_null_column_stay_null(backend: Backend) -> None:
    row = structure_pnl_row(leg_contract_ids=[None], leg_entry_iv=None, regt_margin=None)
    StoreWriter(backend).write_table(STRUCTURE_PNL, S, "r1", stamped([row], S, "r1"))
    got = backend.tables.read(STRUCTURE_PNL, S)
    assert got is not None and got["regt_margin"].isna().all() and got["leg_entry_iv"].isna().all()
    assert list(got["leg_contract_ids"].iloc[0]) == [None]


def test_the_value_rules_refuse_an_incomplete_complete_row_and_a_pnl_on_unmeasured() -> None:
    ok = pd.DataFrame([structure_pnl_row()])
    assert structure_pnl_problems(ok) == []
    no_exit = pd.DataFrame([structure_pnl_row(exit_kind=None, pnl_mid=None)])
    assert any("exit_kind is null" in p for p in structure_pnl_problems(no_exit))
    bad_kind = pd.DataFrame([structure_pnl_row(exit_kind="NOPE", price_source="bars")])
    found = structure_pnl_problems(bad_kind)
    assert any("exit_kind must be one of" in p for p in found)
    assert any("price_source must be one of" in p for p in found)
    unmeasured = pd.DataFrame([structure_pnl_row(outcome_status="UNMEASURED")])
    found = structure_pnl_problems(unmeasured)
    assert any("needs an outcome_reason" in p for p in found)
    assert any("pnl_mid must be null" in p for p in found)
    ragged = pd.DataFrame([structure_pnl_row(leg_qty=[-1.0, 100.0])])
    assert any("as long as each other" in p for p in structure_pnl_problems(ragged))


def test_a_row_without_its_required_columns_is_refused(backend: Backend) -> None:
    row = structure_pnl_row()
    del row["position_key"]
    with pytest.raises(DataValidationError):
        StoreWriter(backend).write_table(STRUCTURE_PNL, S, "r1", stamped([row], S, "r1"))
