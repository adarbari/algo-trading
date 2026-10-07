"""``services.events.fill``: the usefulness order of the universe for a budgeted history fill."""

from datetime import date

from algotrade.data import StoreReader
from algotrade.services.events.fill import IV_HISTORY, PRICE_STATS, fill_order
from algotrade.services.events.scope import LIQUIDITY
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)
IDS = {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC", "DDD", "EEE")}


def store(day: date = D2) -> StoreWriter:
    """Optionable CCC and EEE; IV30 on EEE (50) and CCC (80) and BBB (99, not optionable); dollar
    volume on AAA (5e6), BBB (9e6) and CCC (1e6); DDD nowhere."""
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, D1, IDS)
    tables = {
        LIQUIDITY: [{"instrument_id": "EQ:CCC"}, {"instrument_id": "EQ:EEE"}],
        IV_HISTORY: [
            {"instrument_id": "EQ:EEE", "iv30": 50.0},
            {"instrument_id": "EQ:CCC", "iv30": 80.0},
            {"instrument_id": "EQ:BBB", "iv30": 99.0},
        ],
        PRICE_STATS: [
            {"instrument_id": "EQ:AAA", "adv_usd_20d": 5e6},
            {"instrument_id": "EQ:BBB", "adv_usd_20d": 9e6},
            {"instrument_id": "EQ:CCC", "adv_usd_20d": 1e6},
        ],
    }
    for table, rows in tables.items():
        writer.write_table(table, day, "t", stamped(rows, day, "t"))
    return writer


def symbols(writer: StoreWriter, session: date) -> list[str]:
    return [c.symbol for c in fill_order(StoreReader(writer._backend), session)]


def test_optionable_first_then_iv30_then_dollar_volume_then_symbol() -> None:
    # CCC (80) before EEE (50): both optionable; then BBB (iv 99, adv 9e6) before AAA (adv 5e6)
    # among the rest; DDD has neither
    assert symbols(store(), D2) == ["CCC", "EEE", "BBB", "AAA", "DDD"]


def test_a_name_without_iv_ranks_by_dollar_volume_after_the_ones_with_iv() -> None:
    first = fill_order(StoreReader(store()._backend), D2)[0]
    assert (first.optionable, first.iv30, first.adv_usd_20d) == (True, 80.0, 1e6)
    last = fill_order(StoreReader(store()._backend), D2)[-1]
    assert (last.optionable, last.iv30, last.adv_usd_20d) == (False, None, None)


def test_rollups_are_read_as_of_the_session_never_a_later_one() -> None:
    writer = store(D3)  # every rollup is stored only on D3
    # as of D2 nothing is stored: the order is by symbol alone
    assert symbols(writer, D2) == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    assert symbols(writer, D3) == ["CCC", "EEE", "BBB", "AAA", "DDD"]
