"""Feature values by catalogue name for exactly the session: a value, or UNKNOWN with the
reason (NO_PARTITION, NO_ROW, NULL), never an older partition's value."""

from datetime import date

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.instruments.catalogue import FeatureFormat, UnknownFeatureError
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.unit.services.read.instruments.conftest import D0, D1

CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"
NEXT = "rollup.earnings@v1.next_earnings_date"
FROM_HIGH = "feature.pct_from_high_52w"
SECTOR = "instrument.sector"
SYMBOL = "instrument.symbol"


def values(ctx: ReadContext, iid: str, *names: str) -> dict[str, tuple[object, object]]:
    found = load_feature_values(ctx, [iid], names)[iid]
    return {v.name: (v.value, v.unknown.code if v.unknown else None) for v in found}


def test_values_for_exactly_the_session(ctx: ReadContext) -> None:
    got = values(ctx, "EQ:AAA", CLOSE, FROM_HIGH, SECTOR, SYMBOL)
    assert got[CLOSE] == (51.0, None)  # D1's close, not D0's
    assert got[FROM_HIGH][1] is None and got[FROM_HIGH][0] == pytest.approx(51 / 60 - 1)
    assert got[SECTOR] == ("Technology", None)  # company snapshot (D0) the session sees
    assert got[SYMBOL] == ("AAA", None)


def test_an_older_partition_is_never_shown(ctx: ReadContext) -> None:
    [value] = load_feature_values(ctx, ["EQ:AAA"], [NEXT])["EQ:AAA"]
    assert value.value is None  # earnings@v1 has a D0 partition only
    assert value.unknown is not None and value.unknown.code is UnknownCode.NO_PARTITION
    assert value.unknown.detail == "rollups/instrument/earnings@v1 has no partition for 2026-10-01"
    assert value.info.format is FeatureFormat.DATE


def test_no_row_and_stored_null_are_told_apart(ctx: ReadContext) -> None:
    aaa = values(ctx, "EQ:AAA", HV20)
    assert aaa[HV20] == (None, UnknownCode.NULL)
    etf = values(ctx, "EQ:ETFX", CLOSE, FROM_HIGH, SECTOR)
    assert etf[CLOSE] == (None, UnknownCode.NO_ROW)  # in D0's price_stats, not D1's
    assert etf[FROM_HIGH] == (None, UnknownCode.NO_ROW)
    assert etf[SECTOR] == (None, UnknownCode.NULL)  # no company row: not known
    gone = values(ctx, "EQ:GONE", CLOSE)
    assert gone[CLOSE] == (None, UnknownCode.NO_ROW)  # not in the reference snapshot


def test_an_earlier_session_reads_its_own_partitions(reader: StoreReader) -> None:
    earlier = open_context(reader, MemoryConfigStore({}), UserContext("local"), D0)
    got = values(earlier, "EQ:AAA", CLOSE, NEXT)
    assert got[CLOSE] == (50.0, None)
    assert got[NEXT] == (D1.isoformat(), None)


def test_names_keep_their_order_once_each_with_their_info(ctx: ReadContext) -> None:
    found = load_feature_values(ctx, ["EQ:AAA"], [SECTOR, CLOSE, SECTOR])["EQ:AAA"]
    assert [v.name for v in found] == [SECTOR, CLOSE]
    assert [v.info.format for v in found] == [FeatureFormat.TEXT, FeatureFormat.CURRENCY]


def test_a_name_outside_the_catalogue_is_an_error(ctx: ReadContext) -> None:
    with pytest.raises(UnknownFeatureError, match=r"rollup\.nope@v1\.x"):
        load_feature_values(ctx, ["EQ:AAA"], ["rollup.nope@v1.x"])


def test_a_session_with_nothing_stored_is_unknown_everywhere() -> None:
    empty = open_context(
        StoreReader(MemoryBackend()), MemoryConfigStore({}), UserContext("u"), date(2026, 1, 2)
    )
    got = values(empty, "EQ:AAA", CLOSE, SECTOR)
    assert got == {
        CLOSE: (None, UnknownCode.NO_PARTITION),
        SECTOR: (None, UnknownCode.NO_PARTITION),
    }


def test_company_facts_from_a_later_snapshot_are_not_known(reader: StoreReader) -> None:
    before = open_context(reader, MemoryConfigStore({}), UserContext("local"), date(2026, 9, 29))
    got = load_feature_values(before, ["EQ:AAA"], [SECTOR])["EQ:AAA"][0]
    assert got.unknown is not None and got.unknown.code is UnknownCode.NO_PARTITION
    assert got.unknown.detail == "instruments/company has no snapshot on or before 2026-09-29"


def test_an_expression_names_the_inputs_without_a_row(reader: StoreReader) -> None:
    writer = StoreWriter(reader._backend)
    write_rows(
        writer, "rollups/instrument/iv_history@v2", D1, [{"instrument_id": "EQ:ETFX", "iv30": 0.3}]
    )
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"))
    [value] = load_feature_values(ctx, ["EQ:AAA"], ["feature.iv_hv_ratio"])["EQ:AAA"]
    assert value.unknown is not None and value.unknown.code is UnknownCode.NO_ROW
    assert value.unknown.detail.startswith("rollups/instrument/iv_history@v2 has no row")
