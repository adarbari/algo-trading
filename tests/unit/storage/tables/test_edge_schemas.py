"""The trade contract's columns on the ledger, the paper record and the legs (ADR 0088, E6a): a
partition written with them and one written before read together with the older rows null (never
a default), and each column has the type of the contract's."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.services.evaluation.evidence.contract import TRADE_COLUMNS
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.edge_schemas import EDGE_LEGS, EDGE_PAPER, EDGE_TRADES
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 11), date(2026, 9, 14)
KNOWN = datetime(2026, 9, 15, 22, tzinfo=UTC)
NEW_TRADES = ("exit_kind", "capital_basis", "price_source", "return_on_capital", "max_adverse")
NEW_PAPER = ("exit_kind", "price_source", "return_on_capital")
NEW_LEGS = (
    "pick_exit", "pick_exit_kind", "pick_source", "pick_licence", "pick_capital", "pick_roc_gross",
    "pick_roc", "pick_adverse",
)  # fmt: skip


def _trade(day: date, **changes: object) -> dict[str, object]:
    return {
        "edge_id": "e", "user_id": "site", "edge_variant": None, "variant": "v",
        "horizon_sessions": 2, "range_from": D1, "split_from": None, "decision_session": day,
        "instrument_id": "EQ:A", "value": 0.01, **changes,
    }  # fmt: skip


def test_an_older_ledger_partition_reads_the_contract_columns_as_null() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    new = {"exit_kind": "HORIZON", "capital_basis": "notional", "price_source": "bars",
           "return_on_capital": 0.009, "max_adverse": 0.02}  # fmt: skip
    for day, run, row in ((D1, "r1", _trade(D1)), (D2, "r2", _trade(D2, **new))):
        writer.write_table(EDGE_TRADES.name, day, run, stamped([row], day, run, KNOWN, "edge-eval"))
    out = StoreReader(backend).table_range(EDGE_TRADES.name, D1, D2).set_index("decision_session")  # type: ignore[union-attr]
    for column in NEW_TRADES:
        assert pd.isna(out.loc[D1, column]), column
        assert not pd.isna(out.loc[D2, column]), column
    assert out.loc[D1, "value"] == 0.01


def test_the_contract_columns_have_the_contracts_types_and_are_nullable() -> None:
    dtype = {c.name: c.dtype for c in TRADE_COLUMNS}
    for spec, names in ((EDGE_TRADES, NEW_TRADES), (EDGE_PAPER, NEW_PAPER)):
        declared = {c.name: c for c in spec.columns}
        for column in names:
            assert str(declared[column].type).startswith(dtype[column]), column
            assert declared[column].nullable, column


def test_the_legs_carry_the_picks_contract_fields() -> None:
    assert set(NEW_LEGS) <= {c.name for c in EDGE_LEGS.columns}
