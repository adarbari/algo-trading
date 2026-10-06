from datetime import date, timedelta

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.market.tiers import CORE, REST, load_tiers
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 2)
PRICE_STATS = "rollups/instrument/price_stats@v2"
OPTION_LIQ = "rollups/instrument/option_liquidity@v1"


def test_core_is_sp500_priority_symbols_and_high_liquidity() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    symbols = ["MSFT", "SPY", "HIGH", "MED", "OTHER"]
    reference = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE", "in_sp500": s == "MSFT"}
        for s in symbols
    ]  # fmt: skip
    writer.write_table("instruments/reference", DAY, "ref", stamped(reference, DAY, "ref"))
    yesterday = DAY - timedelta(days=1)
    big, mid = {"adv_usd_20d": 2e8, "close": 50.0}, {"adv_usd_20d": 2e7, "close": 20.0}
    tier_a = {"liq_status": "OK", "put_tier": "A", "call_tier": "A", "chain_volume": 9000}
    tier_b = {"liq_status": "OK", "put_tier": "B", "call_tier": "B", "chain_volume": 100}
    prices = [{"instrument_id": "EQ:HIGH", **big}, {"instrument_id": "EQ:MED", **mid}]
    options = [
        {"instrument_id": "EQ:HIGH", **tier_a, "chain_oi": 60_000},
        {"instrument_id": "EQ:MED", **tier_b, "chain_oi": 6_000},
    ]
    writer.write_table(PRICE_STATS, yesterday, "r1", stamped(prices, yesterday, "r1"))
    writer.write_table(OPTION_LIQ, yesterday, "r1", stamped(options, yesterday, "r1"))
    tiers = load_tiers(reader, DAY, ["spy"])
    got = {s: tiers.tier(f"EQ:{s}", s) for s in symbols}
    assert got == {"MSFT": CORE, "SPY": CORE, "HIGH": CORE, "MED": REST, "OTHER": REST}


def test_an_empty_store_leaves_only_the_pinned_symbols_core() -> None:
    tiers = load_tiers(StoreReader(MemoryBackend()), DAY, ["SPY"])
    assert (tiers.tier("EQ:SPY", "spy"), tiers.tier("EQ:AAA", "AAA")) == (CORE, REST)


def _reference(writer: StoreWriter, day: date, members: set[str]) -> None:
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "multiplier": 1.0,
         "security_type": "COMMON_STOCK", "status": "ACTIVE", "in_sp500": s in members}
        for s in ("OLD", "NEW")
    ]  # fmt: skip
    writer.write_table("instruments/reference", day, "ref", stamped(rows, day, "ref"))


def test_membership_never_comes_from_a_later_snapshot() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    _reference(writer, DAY + timedelta(days=30), {"NEW"})  # a backfill of DAY: only a later one
    assert load_tiers(reader, DAY).tier("EQ:NEW", "NEW") == REST
    _reference(writer, DAY - timedelta(days=1), {"OLD"})
    tiers = load_tiers(reader, DAY)
    assert (tiers.tier("EQ:OLD", "OLD"), tiers.tier("EQ:NEW", "NEW")) == (CORE, REST)
    assert tiers.sources()["reference"] == (DAY - timedelta(days=1)).isoformat()


def test_liquidity_comes_from_the_session_strictly_before() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    big = {"adv_usd_20d": 2e8, "close": 50.0}
    tier_a = {"liq_status": "OK", "put_tier": "A", "call_tier": "A", "chain_volume": 9000}
    for day, run in ((DAY, "r2"),):  # the session's own rollups exist (a later re-run)
        prices = [{"instrument_id": "EQ:HIGH", **big}]
        options = [{"instrument_id": "EQ:HIGH", **tier_a, "chain_oi": 60_000}]
        writer.write_table(PRICE_STATS, day, run, stamped(prices, day, run))
        writer.write_table(OPTION_LIQ, day, run, stamped(options, day, run))
    tiers = load_tiers(reader, DAY)
    assert tiers.tier("EQ:HIGH", "HIGH") == REST and tiers.sources()["liquidity"] is None
    before = DAY - timedelta(days=1)
    writer.write_table(PRICE_STATS, before, "r1", stamped(prices, before, "r1"))
    writer.write_table(OPTION_LIQ, before, "r1", stamped(options, before, "r1"))
    tiers = load_tiers(reader, DAY)
    assert (
        tiers.tier("EQ:HIGH", "HIGH") == CORE and tiers.sources()["liquidity"] == before.isoformat()
    )
