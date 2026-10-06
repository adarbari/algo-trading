"""Feature values by catalogue name for exactly the session: a value, or UNKNOWN with the
reason (NO_PARTITION, NO_ROW, NULL), never an older partition's value."""

from datetime import date, timedelta

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.instruments.catalogue import (
    FeatureFormat,
    UnknownFeatureError,
    feature_infos,
)
from algotrade.services.read.instruments.features import (
    FeatureValue,
    _absence,
    cell_codes,
    load_feature_values,
)
from algotrade.services.read.values import NullReason, Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

D2 = D1 + timedelta(days=1)
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


IV30 = "rollup.iv30@v1.iv30"
IV_HISTORY = "rollups/instrument/iv_history@v2"
IV_STATUS = "rollups/instrument/iv30@v1"


def _chain_rows(status: str, history: float | None = None) -> StoreReader:
    """AAA has an iv30 row on D1 with ``status`` (iv30 null unless OK) and an iv_history row."""

    def write(writer: StoreWriter) -> None:
        iv = 0.3 if status == "OK" else None
        write_rows(writer, IV_STATUS, D1, [{"instrument_id": "EQ:AAA", "iv30": iv,
                                            "iv30_status": status}])  # fmt: skip
        write_rows(writer, IV_HISTORY, D1, [{"instrument_id": "EQ:AAA", "iv30": iv}])

    return store_with(write)


def test_a_non_optionable_instrument_is_not_applicable_not_unknown() -> None:
    ctx = context(_chain_rows("WIDE_SPREADS"))
    [etf] = load_feature_values(ctx, ["EQ:ETFX"], [IV30])["EQ:ETFX"]  # no row in iv30@v1
    assert etf.unknown is not None and etf.unknown.code is UnknownCode.NOT_APPLICABLE
    assert "EQ:ETFX is not optionable (reference snapshot 2026-09-30)" in etf.unknown.detail
    aaa = values(ctx, "EQ:AAA", FROM_HIGH)
    assert aaa[FROM_HIGH][1] is None  # a feature that applies to every instrument is unaffected


def test_an_etf_has_no_earnings_but_a_stock_with_none_is_unknown(reader: StoreReader) -> None:
    earlier = open_context(reader, MemoryConfigStore({}), UserContext("local"), D0)
    assert values(earlier, "EQ:ETFX", NEXT)[NEXT] == (None, UnknownCode.NOT_APPLICABLE)
    [etf] = load_feature_values(earlier, ["EQ:ETFX"], [NEXT])["EQ:ETFX"]
    assert etf.unknown is not None and "ETF" in etf.unknown.detail
    assert values(earlier, "EQ:AAA", NEXT)[NEXT] == (D1.isoformat(), None)  # a value always wins


def test_a_thin_chain_is_illiquid_and_inherited_by_expressions() -> None:
    ctx = context(_chain_rows("WIDE_SPREADS"))
    [value] = load_feature_values(ctx, ["EQ:AAA"], [IV30])["EQ:AAA"]
    assert value.unknown is not None and value.unknown.code is UnknownCode.ILLIQUID
    assert value.unknown.detail.startswith("iv30_status is WIDE_SPREADS for EQ:AAA on 2026-10-01")
    got = values(ctx, "EQ:AAA", "feature.iv_hv_ratio")
    assert got["feature.iv_hv_ratio"] == (None, UnknownCode.ILLIQUID)


def test_a_real_gap_stays_unknown() -> None:
    ctx = context(_chain_rows("NO_CHAIN"))  # no chain at all: not "too thin"
    assert values(ctx, "EQ:AAA", IV30)[IV30] == (None, UnknownCode.NULL)
    ok = context(_chain_rows("OK"))
    assert values(ok, "EQ:AAA", IV30)[IV30][0] == pytest.approx(0.3)  # a value always wins


def test_not_applicable_wins_over_illiquid_for_an_expression() -> None:
    ctx = context(_chain_rows("WIDE_SPREADS"))
    got = values(ctx, "EQ:ETFX", "feature.iv_hv_ratio")
    assert got["feature.iv_hv_ratio"][1] is not UnknownCode.ILLIQUID


IV_RANK = "rollup.iv_history@v2.iv_rank_252d"


def test_a_null_optionable_is_not_not_applicable() -> None:
    ctx = context(_chain_rows("OK"))  # EQ:NOOPT: optionable unknown, no iv30 row
    assert values(ctx, "EQ:NOOPT", IV30)[IV30] == (None, UnknownCode.NO_ROW)


def test_a_null_rank_with_an_ok_status_is_null_not_illiquid() -> None:
    ctx = context(_chain_rows("OK"))
    assert values(ctx, "EQ:AAA", IV_RANK)[IV_RANK] == (None, UnknownCode.NULL)


def _kinds(writer: StoreWriter) -> None:
    """A D1 reference snapshot with a preferred, a SPAC (SIC 6770, company snapshot on D1) and
    a stock with no company row (null sic), beside AAA."""
    base = {"asset_class": "EQ", "exchange": "NYSE", "multiplier": 1.0, "status": "ACTIVE",
            "is_etf": False, "optionable": True}  # fmt: skip
    kinds = {"AAA": "COMMON_STOCK", "PREF": "PREFERRED", "SPAC": "COMMON_STOCK",
             "NOSIC": "COMMON_STOCK"}  # fmt: skip
    rows = [{"instrument_id": f"EQ:{s}", "symbol": s, "name": s, "security_type": t, **base}
            for s, t in kinds.items()]  # fmt: skip
    write_rows(writer, "instruments/reference", D1, rows)
    company = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "cik": "1", "name": s, "sic": sic,
         "sector": None, "fetched_on": D1}
        for s, sic in (("AAA", "3571"), ("SPAC", "6770"))
    ]  # fmt: skip
    write_rows(writer, "instruments/company", D1, company)
    earnings = {"instrument_id": "EQ:AAA", "next_earnings_date": D1, "days_to_earnings": 0}
    write_rows(writer, "rollups/instrument/earnings@v1", D1, [earnings])


def test_earnings_apply_only_to_operating_companies() -> None:
    ctx = context(store_with(_kinds))
    assert values(ctx, "EQ:AAA", NEXT)[NEXT] == (D1.isoformat(), None)
    assert values(ctx, "EQ:PREF", NEXT)[NEXT] == (None, UnknownCode.NOT_APPLICABLE)
    assert values(ctx, "EQ:SPAC", NEXT)[NEXT] == (None, UnknownCode.NOT_APPLICABLE)
    [spac] = load_feature_values(ctx, ["EQ:SPAC"], [NEXT])["EQ:SPAC"]
    assert spac.unknown is not None and "blank-check" in spac.unknown.detail
    assert values(ctx, "EQ:NOSIC", NEXT)[NEXT] == (None, UnknownCode.NO_ROW)  # never a false n/a


def test_a_company_snapshot_after_the_session_does_not_make_a_spac() -> None:
    def later(writer: StoreWriter) -> None:
        _kinds(writer)
        company = {"instrument_id": "EQ:NOSIC", "symbol": "NOSIC", "cik": "2", "name": "NOSIC",
                   "sic": "6770", "sector": None, "fetched_on": D2}  # fmt: skip
        write_rows(writer, "instruments/company", D2, [company])

    ctx = context(store_with(later), D1)
    assert values(ctx, "EQ:NOSIC", NEXT)[NEXT] == (None, UnknownCode.NO_ROW)


PRICE_STATS = "rollups/instrument/price_stats@v2"
BAR_STATUS = "rollup.price_history@v1.bar_status"  # a status field (ADR 0046)
STATS_ROW = "rollup.price_stats@v2.instrument_id"


def _why(row: dict[str, object], applies: frozenset[str] = frozenset(), *rules: object) -> Unknown:
    """``_absence`` of the close of EQ:AAA on D1 with ``row`` and these status rules."""
    ctx = context(_chain_rows("OK"))
    info = feature_infos(ctx.features, [CLOSE])[CLOSE]
    return _absence(info, (PRICE_STATS,), row, ctx, "EQ:AAA", (applies, tuple(rules)))  # type: ignore[arg-type]


NO_TRADE = (BAR_STATUS, frozenset(), frozenset({"NO_TRADE"}), PRICE_STATS)


def test_an_explained_status_names_its_reason() -> None:
    why = _why({BAR_STATUS: "NO_TRADE"}, frozenset(), NO_TRADE)  # no price_stats row either
    assert (why.code, why.reason) == (UnknownCode.EXPLAINED, NullReason.NO_TRADE)
    assert why.detail == "bar_status is NO_TRADE for EQ:AAA on 2026-10-01: no bar on the session"


def test_a_status_that_explains_nothing_leaves_the_gap() -> None:
    traded = _why({BAR_STATUS: "TRADED"}, frozenset(), NO_TRADE)
    assert (traded.code, traded.reason) == (UnknownCode.NO_ROW, None)  # a real gap stays one
    unstatused = _why({BAR_STATUS: None, STATS_ROW: "EQ:AAA"}, frozenset(), NO_TRADE)
    assert unstatused.code is UnknownCode.NULL


def test_an_explained_input_never_hides_a_gap_in_another_input() -> None:
    elsewhere = (BAR_STATUS, frozenset(), frozenset({"NOT_ANNOUNCED"}), "rollups/x/earnings@v2")
    gap = _why({BAR_STATUS: "NOT_ANNOUNCED"}, frozenset(), elsewhere)  # no price_stats row
    assert (gap.code, gap.reason) == (UnknownCode.NO_ROW, None)
    covered = _why({BAR_STATUS: "NOT_ANNOUNCED", STATS_ROW: "EQ:AAA"}, frozenset(), elsewhere)
    assert covered.reason is NullReason.NOT_ANNOUNCED  # every input has its row: explained


def test_absence_precedence_not_applicable_then_illiquid_then_explained() -> None:
    thin = ("rollup.iv30@v1.iv30_status", frozenset({"WIDE_SPREADS"}), frozenset(), IV_STATUS)
    row = {BAR_STATUS: "NO_TRADE", thin[0]: "WIDE_SPREADS", "instrument.optionable": False}
    assert _why(row, frozenset(), NO_TRADE, thin).code is UnknownCode.ILLIQUID
    assert _why(row, frozenset({"optionable"}), NO_TRADE, thin).code is UnknownCode.NOT_APPLICABLE
    first = (BAR_STATUS, frozenset(), frozenset({"NO_TRADE", "FEW_BARS"}), PRICE_STATS)
    assert _why(row, frozenset(), first).reason is NullReason.NO_TRADE


def test_cell_codes_carry_the_reason_of_explained_cells() -> None:
    ctx = context(_chain_rows("OK"))
    info = feature_infos(ctx.features, [CLOSE])[CLOSE]
    explained = Unknown(UnknownCode.EXPLAINED, "x", NullReason.NEW_LISTING)
    cells = {
        "A": (FeatureValue(CLOSE, None, explained, info), FeatureValue(CLOSE, 1.0, None, info)),
        "B": (FeatureValue(CLOSE, None, Unknown(UnknownCode.NULL, "y"), info),) * 2,
    }
    unknown, reasons = cell_codes(cells, ["A", "B", "C"])
    assert unknown == ((UnknownCode.EXPLAINED, None), (UnknownCode.NULL, UnknownCode.NULL), ())
    assert reasons == ((NullReason.NEW_LISTING, None), (None, None), ())


HISTORY = "rollups/instrument/price_history@v1"


def test_no_bar_on_the_session_reads_no_trade_and_the_since_listing_high(
    reader: StoreReader,
) -> None:
    writer = StoreWriter(reader._backend)
    write_rows(writer, HISTORY, D1, [
        {"instrument_id": "EQ:ETFX", "bar_status": "NO_TRADE", "range_status": "FULL",
         "high_avail": 60.0},
        {"instrument_id": "EQ:AAA", "bar_status": "TRADED", "range_status": "NEW_LISTING",
         "high_avail": None},
    ])  # fmt: skip
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"))
    [close] = load_feature_values(ctx, ["EQ:ETFX"], [CLOSE])["EQ:ETFX"]  # no price_stats row
    assert close.unknown is not None and close.unknown.reason is NullReason.NO_TRADE
    assert close.unknown.detail.startswith("bar_status is NO_TRADE for EQ:ETFX on 2026-10-01")
    avail = values(ctx, "EQ:AAA", "feature.pct_from_high_avail", FROM_HIGH)
    assert avail["feature.pct_from_high_avail"] == (None, UnknownCode.EXPLAINED)  # NEW_LISTING
    assert avail[FROM_HIGH][1] is None  # the 52-week value is still served
    gone = values(ctx, "EQ:GONE", CLOSE)
    assert gone[CLOSE] == (None, UnknownCode.NO_ROW)  # no status: the gap stays a gap


def test_a_next_report_not_in_the_calendar_reads_not_announced(reader: StoreReader) -> None:
    writer = StoreWriter(reader._backend)
    write_rows(writer, "rollups/instrument/earnings@v1", D1, [
        {"instrument_id": "EQ:AAA", "next_earnings_date": None, "last_earnings_date": D0},
    ])  # fmt: skip
    write_rows(writer, "rollups/instrument/earnings_schedule@v1", D1, [
        {"instrument_id": "EQ:AAA", "next_status": "NOT_ANNOUNCED"},
    ])  # fmt: skip
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"))
    [nxt] = load_feature_values(ctx, ["EQ:AAA"], [NEXT])["EQ:AAA"]
    assert nxt.unknown is not None and nxt.unknown.reason is NullReason.NOT_ANNOUNCED
    assert nxt.unknown.detail.endswith("the next report date is not announced")
    assert values(ctx, "EQ:ETFX", NEXT)[NEXT] == (None, UnknownCode.NOT_APPLICABLE)  # still n/a


LINK = "rollup.fund_reference@v1.reference_instrument_id"


def _funds(writer: StoreWriter) -> None:
    """A D1 reference with a stock, a leveraged fund with a link, an inverse fund and an ETF
    whose leverage flags are unknown (null), and the group's partition with the funds' rows."""
    base = {"asset_class": "EQ", "exchange": "NYSE", "multiplier": 1.0, "status": "ACTIVE",
            "optionable": True}  # fmt: skip
    kinds = {  # symbol -> (security type, leveraged, inverse)
        "AAA": ("COMMON_STOCK", False, False), "TSLL": ("ETF", True, False),
        "TSLQ": ("ETF", False, True), "UNK": ("ETF", None, None),
    }  # fmt: skip
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "name": s, "security_type": t,
         "is_etf": t == "ETF", "is_leveraged": lev, "is_inverse": inv, **base}
        for s, (t, lev, inv) in kinds.items()
    ]  # fmt: skip
    write_rows(writer, "instruments/reference", D1, rows)
    link = [{"instrument_id": "EQ:TSLL", "reference_instrument_id": "EQ:AAA"},
            {"instrument_id": "EQ:TSLQ", "reference_instrument_id": None}]  # fmt: skip
    write_rows(writer, "rollups/instrument/fund_reference@v1", D1, link)


def test_fund_reference_applies_to_leveraged_and_inverse_funds_only() -> None:
    ctx = context(store_with(_funds))
    assert values(ctx, "EQ:TSLL", LINK)[LINK] == ("EQ:AAA", None)
    assert values(ctx, "EQ:TSLQ", LINK)[LINK] == (None, UnknownCode.NULL)  # a basket: a stored null
    assert values(ctx, "EQ:AAA", LINK)[LINK] == (None, UnknownCode.NOT_APPLICABLE)
    [stock] = load_feature_values(ctx, ["EQ:AAA"], [LINK])["EQ:AAA"]
    assert stock.unknown is not None and "not a leveraged or inverse fund" in stock.unknown.detail
    assert values(ctx, "EQ:UNK", LINK)[LINK] == (None, UnknownCode.NO_ROW)  # unknown: never n/a
