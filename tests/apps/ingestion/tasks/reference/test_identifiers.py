from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.symbol_history import update_history
from algotrade_ingestion.tasks.reference.universe_build import (
    UniverseSettings,
    UniverseSources,
    apply_identifiers,
    build_universe,
)
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.massive.tickers import MassiveTickers, parse_tickers
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as mfx
from tests.helpers.payloads import universe as fx

D1 = date(2026, 10, 1)
D2 = D1 + timedelta(days=1)
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731


def ticker(symbol: str, kind: str, figi: str) -> dict[str, object]:
    return {
        "ticker": symbol,
        "type": kind,
        "composite_figi": figi,
        "share_class_figi": f"S{figi}",
        "cik": "0000000001",
    }


def test_parse_tickers_maps_vendor_types() -> None:
    frame = parse_tickers(
        [
            ticker("AAPL", "CS", "F1"),
            ticker("KIMpL", "PFD", "F2"),
            ticker("PDI", "FUND", "F3"),
            ticker("ODD", "XYZ", "F4"),
            {"ticker": ""},
        ]
    )
    rows = frame.set_index("symbol")
    assert rows.loc["AAPL", "vendor_security_type"] == "COMMON_STOCK"
    assert rows.loc["KIM$L", "vendor_security_type"] == "PREFERRED"
    assert rows.loc["PDI", "vendor_security_type"] == "CEF"  # closed-end funds are not common stock
    assert pd.isna(rows.loc["ODD", "vendor_security_type"])


def test_vendor_type_wins_and_disagreements_are_counted() -> None:
    reference = pd.DataFrame(
        {
            "symbol": ["AAPL", "PDI", "NEW"],
            "security_type": ["COMMON_STOCK", "COMMON_STOCK", "COMMON_STOCK"],
        }
    )
    tickers = parse_tickers([ticker("AAPL", "CS", "F1"), ticker("PDI", "FUND", "F3")])
    enriched, disagreements = apply_identifiers(reference, tickers)
    rows = enriched.set_index("symbol")
    assert disagreements == 1
    assert (rows.loc["PDI", "security_type"], rows.loc["PDI", "security_type_source"]) == (
        "CEF",
        "vendor",
    )
    assert (rows.loc["NEW", "security_type"], rows.loc["NEW", "security_type_source"]) == (
        "COMMON_STOCK",
        "name_rule",
    )
    assert rows.loc["AAPL", "figi"] == "F1"
    plain, none = apply_identifiers(reference, None)
    assert none == 0 and plain["figi"].isna().all()


def type_after_precedence(name: str, vendor: str, is_etf: bool = False) -> tuple[str, str]:
    from algotrade_ingestion.tasks.reference.classify import security_type  # noqa: PLC0415

    reference = pd.DataFrame({"symbol": ["X"], "security_type": [security_type(name, "X", is_etf)]})
    enriched, _ = apply_identifiers(reference, parse_tickers([ticker("X", vendor, "F1")]))
    row = enriched.iloc[0]
    return row["security_type"], row["security_type_source"]


def test_a_generic_vendor_type_yields_to_a_specific_name_rule() -> None:
    adamg = "Adamas Trust, Inc. - 9.125% Senior Notes Due 2030"
    acgln = "Arch Capital Group Ltd. - Depositary Shares, each Representing a 1/1,000th "
    acgln += "Interest in a 4.550% Non-Cumulative Preferred Share, Series G"
    adaml = "Adamas Trust, Inc. - 6.875% Series F Cumulative Redeemable Preferred Stock"
    assert type_after_precedence(adamg, "CS") == ("NOTE", "name_over_vendor")
    assert type_after_precedence(acgln, "CS") == ("PREFERRED", "name_over_vendor")
    assert type_after_precedence(adaml, "OS") == ("PREFERRED", "name_over_vendor")


def test_operating_companies_adrs_and_spacs_keep_their_type() -> None:
    assert type_after_precedence("Acme Corp. - Common Stock", "CS") == ("COMMON_STOCK", "vendor")
    adr = "Toyota Motor Corp American Depositary Shares"
    assert type_after_precedence(adr, "ADRC") == ("ADR", "vendor")
    spac = "Harvard Ave Acquisition Corporation - Class A Ordinary Shares"
    assert type_after_precedence(spac, "CS") == ("COMMON_STOCK", "vendor")
    # the ADR name rule is loose ("ADS-TEC"): it does not override a generic vendor type
    assert type_after_precedence("ADS-TEC ENERGY PLC - Ordinary Shares", "CS") == (
        "COMMON_STOCK",
        "vendor",
    )


def test_banks_named_preferred_and_common_ordinary_shares_are_not_preferred() -> None:
    assert type_after_precedence("Preferred Bank - Common Stock", "CS") == (
        "COMMON_STOCK",
        "vendor",
    )
    bns = "Bank of Nova Scotia Pfd 3 Ordinary Shares"
    assert type_after_precedence(bns, "CS") == ("COMMON_STOCK", "vendor")


def test_a_specific_vendor_type_beats_the_name_rules() -> None:
    assert type_after_precedence("Acme Income Fund Preferred", "FUND") == ("CEF", "vendor")


def test_symbol_history_tracks_ticker_changes() -> None:
    day1 = pd.DataFrame(
        {"symbol": ["FB", "AAPL", "OLD"], "figi": ["F_META", "F_AAPL", "F_OLD"], "status": "ACTIVE"}
    )
    day1["instrument_id"] = "EQ:" + day1["figi"]
    history1, changes1 = update_history(None, day1, D1)
    assert changes1 == [] and history1["valid_to"].isna().all()
    day2 = pd.DataFrame(
        {
            "symbol": ["META", "AAPL", "NEW"],
            "figi": ["F_META", "F_AAPL", "F_NEW"],
            "status": "ACTIVE",
        }
    )
    day2["instrument_id"] = "EQ:" + day2["figi"]
    history2, changes2 = update_history(history1, day2, D2)
    assert changes2 == [
        {
            "instrument_id": "EQ:F_META",  # the id survives the ticker change
            "symbol": "META",
            "change": "ticker_changed",
            "old": "FB",
            "new": "META",
        }
    ]
    rows = {(r["figi"], r["symbol"]): r for r in history2.to_dict("records")}
    assert rows[("F_META", "FB")]["valid_to"] == D2
    assert rows[("F_META", "META")]["valid_from"] == D2 and pd.isna(
        rows[("F_META", "META")]["valid_to"]
    )
    assert rows[("F_OLD", "OLD")]["valid_to"] == D2
    assert pd.isna(rows[("F_AAPL", "AAPL")]["valid_to"])
    assert ("F_NEW", "NEW") in rows
    assert rows[("F_META", "FB")]["instrument_id"] == rows[("F_META", "META")]["instrument_id"]


def test_universe_build_with_identifiers_and_a_rename() -> None:
    def sources(names: list[tuple[str, str]], tickers: list[dict[str, object]]) -> UniverseSources:
        files = {
            "nasdaqlisted": fx.nasdaq([(s, f"{s} Corp Common Stock", "N", "N") for s, _ in names]),
            "otherlisted": fx.other([("ZZZ", "Zed Common Stock", "N", "N")]),
            "options": fx.options([s for s, _ in names]),
        }

        def transport(url: str) -> bytes:
            if "massive" in url:
                return mfx.page(tickers)
            return next((v for k, v in files.items() if k in url), fx.spy([names[0][0]]))

        return UniverseSources(
            NasdaqTraderSource(http_for(transport, RetryPolicy(tries=1))),
            SpyHoldingsSource(http_for(transport)),
            MassiveTickers(http_for(transport)),
        )

    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    first = build_universe(
        task_ctx(writer, reader, CLOCK),
        sources(
            [("FB", "F_META"), ("AAPL", "F_AAPL")],
            [ticker("FB", "CS", "F_META"), ticker("AAPL", "CS", "F_AAPL")],
        ),
        UniverseSettings(),
        D1,
    )
    assert first.stats["identifiers"]["with_figi"] == 2
    second = build_universe(
        task_ctx(writer, reader, CLOCK),
        sources(
            [("META", "F_META"), ("AAPL", "F_AAPL")],
            [ticker("META", "CS", "F_META"), ticker("AAPL", "CS", "F_AAPL")],
        ),
        UniverseSettings(),
        D2,
    )
    assert second.stats["events"]["reference_change"]["ticker_changed"] == 1
    history = reader.table("instruments/symbol_history", D2)
    assert history is not None and set(history["symbol"]) == {"FB", "META", "AAPL"}
    reference = reader.table("instruments/reference", D2).set_index("symbol")  # type: ignore[union-attr]
    assert reference.loc["META", "figi"] == "F_META"
    assert reference.loc["META", "instrument_id"] == "EQ:F_META"  # same id as FB on D1
    assert "FB" not in reference.index  # a rename, not a delisting
    assert reference.loc["ZZZ", "instrument_id"] == "EQ:ZZZ"  # no FIGI: symbol id
    assert second.stats["identifiers"]["ids_by_figi"] == 2
    assert second.stats["identifiers"]["ids_by_symbol"] == 1
    assert reference.loc["ZZZ", "security_type_source"] == "name_rule"  # not in the vendor list
