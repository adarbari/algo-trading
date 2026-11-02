"""The helpers of the option-outcomes writer. ``option_fields``: the catalogue fields of an option
trade's exit rules, read per close: a
close's value comes only from that close's own partition (a later or earlier session's value for
the same name is never read), the latest ``knowledge_ts`` read is returned, a missing partition,
name or NaN is no value (the rule is UNKNOWN), and a field no stored group holds is refused with a
reason (an expression feature, an instrument fact, a group with no partition in the range).
``option_paths.position_rows`` (below): the row shaping of a trade window."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.engines.structures.trades import Trade
from algotrade.storage.tables.schemas import STRUCTURE_PNL, spec_for, structure_pnl_problems
from algotrade.storage.tables.spec import COMMON
from algotrade_ingestion.tasks.derived.option_fields import FieldLoader, refuse_unstored
from algotrade_ingestion.tasks.derived.option_paths import COLUMNS, position_rows
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import stamped

IV = "rollup.iv30@v1.iv30"
TABLE = "rollups/instrument/iv30@v1"
D1, D2, D3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
K1, K2 = datetime(2026, 10, 5, 23, tzinfo=UTC), datetime(2026, 10, 6, 23, tzinfo=UTC)


def _stored() -> tuple[FieldLoader, object]:
    writer, reader = store()
    for day, known, values in ((D1, K1, {"EQ:A": 0.20, "EQ:B": 0.30}), (D2, K2, {"EQ:A": 0.90})):
        rows = [{"instrument_id": i, "iv30": v} for i, v in values.items()]
        writer.write_table(TABLE, day, f"r-{day}", stamped(rows, day, f"r-{day}", known))
    return FieldLoader(reader), reader


def test_a_close_reads_only_its_own_partition_and_reports_what_it_stamped() -> None:
    loader, _ = _stored()
    one, stamp1 = loader(D1, [IV], ["EQ:A", "EQ:B"])
    two, stamp2 = loader(D2, [IV], ["EQ:A", "EQ:B"])
    assert one == {"EQ:A": {IV: 0.20}, "EQ:B": {IV: 0.30}} and stamp1 == K1
    assert two == {"EQ:A": {IV: 0.90}, "EQ:B": {IV: None}} and stamp2 == K2  # no D1 fill for B


def test_a_session_with_no_partition_gives_nothing_and_no_stamp() -> None:
    loader, _ = _stored()
    assert loader(D3, [IV], ["EQ:A"]) == ({}, None)
    assert loader(D1, [], ["EQ:A"]) == ({}, None)  # no field named: nothing is read


def test_the_same_session_is_read_once_a_run_and_a_wider_name_set_rereads_it() -> None:
    loader, reader = _stored()
    calls = []
    original = reader.table
    reader.table = lambda *a, **k: calls.append(a[:2]) or original(*a, **k)  # type: ignore[method-assign]
    loader(D1, [IV], ["EQ:A"])
    loader(D1, [IV], ["EQ:A"])
    assert len(calls) == 1
    out, _ = loader(D1, [IV], ["EQ:A", "EQ:B"])  # a name the cache lacks
    assert len(calls) == 2 and set(out) == {"EQ:A", "EQ:B"}


def test_a_field_with_no_stored_group_partition_in_range_is_refused_with_a_reason() -> None:
    _, reader = _stored()
    assert refuse_unstored(reader, [IV], [D2, D3]) == []  # D2 is stored
    (gone,) = refuse_unstored(reader, [IV], [D3])
    assert "no stored partition" in gone and IV in gone
    other = refuse_unstored(reader, ["rollup.nothing@v1.x"], [D1])
    assert "no stored partition" in other[0]  # a group never written


@pytest.mark.parametrize("field", ["instrument.sector", "feature.my_formula", "bogus"])
def test_a_field_that_is_not_a_stored_group_column_is_refused(field: str) -> None:
    _, reader = _stored()
    (problem,) = refuse_unstored(reader, [field], [D1])
    assert field in problem and "not a stored feature" in problem


# ---- option_paths.position_rows: the row shaping of a trade window ----------------------

STAMPS = [datetime(2026, 10, 5 + i, 23, tzinfo=UTC) for i in range(4)]
END = date(2026, 10, 9)


def _trade(name: str, exit_index: int, **changes: object) -> Trade:
    base = Trade(
        name, exit_index=exit_index, kinds=["option"], contract_ids=["OPT:P"], rights=["P"],
        strikes=[95.0], expiries=[date(2026, 11, 20)], qty=[-1.0], leg_mid=[2.0],
        leg_half_spread=[0.05], leg_delta=[-0.3], entry_spot=100.0, entry_net_mid=-2.0,
        entry_half_spread=0.05, exit_session=date(2026, 10, 7), exit_kind="TAKE_PROFIT",
        exit_basis="QUOTE", exit_net_mid=-1.0, exit_half_spread=0.05, pnl_mid=1.0, option_pnl=1.0,
        stock_pnl=0.0, collateral=95.0,
    )  # fmt: skip
    for key, value in changes.items():
        setattr(base, key, value)
    return base


def _rows(trades: list[Trade]) -> pd.DataFrame:
    return position_rows(
        trades, STAMPS, key="k", hold=3, window_end=END, price_source="cboe", licence="open",
        ts=datetime(2026, 10, 5, 20, tzinfo=UTC),
    )  # fmt: skip


def test_the_columns_are_exactly_the_tables_declared_ones() -> None:
    declared = {c.name for c in spec_for(STRUCTURE_PNL).columns if c.name not in COMMON}
    assert set(COLUMNS) == declared | {"knowledge_ts"}
    assert list(_rows([_trade("EQ:A", 2)]).columns) == list(COLUMNS)


def test_a_trade_is_known_when_its_exit_close_was_not_when_the_window_ended() -> None:
    early, held = _rows([_trade("EQ:A", 1), _trade("EQ:B", 3)]).to_dict("records")
    assert pd.Timestamp(early["knowledge_ts"]) == pd.Timestamp(STAMPS[1])
    assert pd.Timestamp(held["knowledge_ts"]) == pd.Timestamp(STAMPS[3])


def test_a_stamp_missing_at_a_close_does_not_lower_the_latest_known() -> None:
    stamps = [STAMPS[0], None, STAMPS[2], None]
    rows = position_rows(
        [_trade("EQ:A", 3)], stamps, key="k", hold=3, window_end=END, price_source="cboe",
        licence="open", ts=datetime(2026, 10, 5, 20, tzinfo=UTC),
    )  # fmt: skip
    assert pd.Timestamp(rows["knowledge_ts"].iloc[0]) == pd.Timestamp(STAMPS[2])


def test_an_unmeasured_trade_has_its_reason_and_no_pnl_and_no_legs_means_null_lists() -> None:
    chosen = _trade("EQ:A", 4, reason="NO_EXIT_QUOTE", exit_session=None, exit_kind=None,
                    exit_basis=None, exit_net_mid=float("nan"), pnl_mid=float("nan"),
                    option_pnl=float("nan"), stock_pnl=float("nan"))  # fmt: skip
    unselectable = Trade("EQ:B", reason="NO_EXPIRY")
    rows = _rows([chosen, unselectable])
    assert list(rows["outcome_status"]) == ["UNMEASURED", "UNMEASURED"]
    assert list(rows["outcome_reason"]) == ["NO_EXIT_QUOTE", "NO_EXPIRY"]
    assert rows["pnl_mid"].isna().all() and rows["exit_kind"].isna().all()
    assert rows["leg_kinds"].iloc[1] is None and rows["leg_strikes"].iloc[1] is None
    assert structure_pnl_problems(rows) == []


def test_columns_declared_for_a_later_slice_are_null_never_zero() -> None:
    rows = _rows([_trade("EQ:A", 2)])
    for column in ("regt_margin", "quoted_otm_prob", "dividend_forgone", "leg_entry_iv"):
        assert rows[column].isna().all(), column
    assert structure_pnl_problems(rows) == []
