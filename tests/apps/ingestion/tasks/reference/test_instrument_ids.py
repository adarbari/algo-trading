"""FIGI-based ids in the universe build (ADR 0018): fallback, stability, upgrades."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import resolver
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.instrument_ids import (
    assign_ids,
    cumulative_map,
    figi_review_rows,
    match_perma,
    rename_ids,
)
from algotrade_ingestion.tasks.reference.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
)
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as mfx
from tests.helpers.payloads import universe as fx

D1 = date(2026, 10, 1)
D2, D3 = D1 + timedelta(days=1), D1 + timedelta(days=2)
NOW = datetime(2026, 10, 2, 22, tzinfo=UTC)


def listed(rows: dict[str, str | None]) -> pd.DataFrame:
    return pd.DataFrame({"symbol": list(rows), "figi": list(rows.values()), "status": "ACTIVE"})


def snapshot(rows: dict[str, tuple[str, str | None]], status: str = "ACTIVE") -> pd.DataFrame:
    """symbol -> (id, figi)"""
    return pd.DataFrame(
        {
            "symbol": list(rows),
            "instrument_id": [i for i, _ in rows.values()],
            "figi": [f for _, f in rows.values()],
            "status": status,
        }
    )


def test_figi_ids_with_symbol_fallback() -> None:
    out = assign_ids(listed({"AAPL": "BBG1", "NOFIGI": None}), None, D1)
    ids = dict(zip(out.reference["symbol"], out.reference["instrument_id"], strict=True))
    assert ids == {"AAPL": "EQ:BBG1", "NOFIGI": "EQ:NOFIGI"}
    assert (out.stats["ids_by_figi"], out.stats["ids_by_symbol"]) == (1, 1)
    assert out.upgrades.empty


def test_figi_id_carries_forward_when_the_vendor_omits_it() -> None:
    previous = snapshot({"AAPL": ("EQ:BBG1", "BBG1"), "XYZ": ("EQ:XYZ", None)})
    out = assign_ids(listed({"AAPL": None, "XYZ": None}), previous, D2)
    rows = out.reference.set_index("symbol")
    assert (rows.loc["AAPL", "instrument_id"], rows.loc["AAPL", "figi"]) == ("EQ:BBG1", "BBG1")
    assert rows.loc["XYZ", "instrument_id"] == "EQ:XYZ"
    assert out.stats["ids_carried"] == 1


def test_shared_figi_keeps_the_holder_and_counts_a_conflict() -> None:
    previous = snapshot({"BRK.B": ("EQ:BBG2", "BBG2")})
    out = assign_ids(listed({"BRK.A": "BBG2", "BRK.B": "BBG2"}), previous, D2)
    ids = dict(zip(out.reference["symbol"], out.reference["instrument_id"], strict=True))
    assert ids == {"BRK.B": "EQ:BBG2", "BRK.A": "EQ:BRK.A"}
    assert out.stats["figi_conflicts"] == 1


def test_symbol_id_upgrades_to_a_figi_id_once() -> None:
    previous = snapshot(
        {
            "AAPL": ("EQ:AAPL", None),  # phase 1.2 store: no FIGI
            "MSFT": ("EQ:MSFT", "BBG3"),  # phase 1.5 store: FIGI known, symbol id
            "REUSE": ("EQ:REUSE", "OLDFIGI"),  # the ticker now belongs to another company
        }
    )
    out = assign_ids(listed({"AAPL": "BBG1", "MSFT": "BBG3", "REUSE": "NEWFIGI"}), previous, D2)
    assert out.upgrades[["old_id", "new_id"]].values.tolist() == [
        ["EQ:AAPL", "EQ:BBG1"],
        ["EQ:MSFT", "EQ:BBG3"],
    ]
    assert out.stats["ids_upgraded"] == 2
    renamed = rename_ids(previous, out.upgrades)
    assert renamed is not None
    assert list(renamed["instrument_id"]) == ["EQ:BBG1", "EQ:BBG3", "EQ:REUSE"]
    again = assign_ids(listed({"AAPL": "BBG1"}), snapshot({"AAPL": ("EQ:BBG1", "BBG1")}), D3)
    assert again.upgrades.empty  # a FIGI id never changes


def test_a_held_figi_id_survives_a_different_vendor_figi() -> None:
    previous = snapshot({"DFAC": ("EQ:BBGA", "BBGA")})
    out = assign_ids(listed({"DFAC": "BBGB"}), previous, D2)
    row = out.reference.iloc[0]
    assert (row["instrument_id"], row["figi"], row["vendor_figi"]) == ("EQ:BBGA", "BBGA", "BBGB")
    assert row["figi_review_since"] == D2 and out.upgrades.empty
    assert (out.stats["figi_changes_held"], out.stats["figi_review"]) == (1, 1)
    agreed = assign_ids(listed({"DFAC": "BBGA"}), out.reference, D3)
    assert agreed.reference.iloc[0]["vendor_figi"] is None and agreed.stats["figi_review"] == 0
    assert figi_review_rows(agreed.reference) == []


def test_a_blank_override_gives_a_symbol_id_and_records_the_change() -> None:
    previous = snapshot({"MMEDV": ("EQ:BBGM", "BBGM"), "MMED": ("EQ:MMED", None)})
    out = assign_ids(listed({"MMED": "BBGM", "MMEDV": "BBGM"}), previous, D2, {"MMEDV": None})
    ids = dict(zip(out.reference["symbol"], out.reference["instrument_id"], strict=True))
    assert ids == {"MMED": "EQ:BBGM", "MMEDV": "EQ:MMEDV"}
    changes = out.upgrades[["old_id", "new_id"]].values.tolist()
    # only the forced change: EQ:BBGM was another listing's id, so MMED's is no upgrade
    assert changes == [["EQ:BBGM", "EQ:MMEDV"]]
    assert (out.stats["ids_upgraded"], out.stats["ids_overridden"]) == (0, 1)
    assert out.stats["figi_review"] == 0  # the owner resolved it


def test_rename_ids_keeps_the_active_row_when_two_meet() -> None:
    previous = pd.concat(
        [
            snapshot({"DFAC": ("EQ:BBGA", "BBGA")}),
            snapshot({"DFAC": ("EQ:BBGB", "BBGB")}, "DELISTED"),
        ],
        ignore_index=True,
    )
    moved = pd.DataFrame({"old_id": ["EQ:BBGA"], "new_id": ["EQ:BBGB"]})
    renamed = rename_ids(previous, moved)
    assert renamed is not None and renamed[["instrument_id", "status"]].values.tolist() == [
        ["EQ:BBGB", "ACTIVE"]
    ]


def test_cumulative_map_keeps_the_first_record() -> None:
    first = cumulative_map(None, assign_ids(
        listed({"AAPL": "BBG1"}), snapshot({"AAPL": ("EQ:AAPL", None)}), D1
    ).upgrades, NOW)  # fmt: skip
    later = NOW + timedelta(days=1)
    rerun = assign_ids(listed({"AAPL": "BBG1"}), snapshot({"AAPL": ("EQ:AAPL", None)}), D2)
    merged = cumulative_map(first, rerun.upgrades, later)
    assert len(merged) == 1
    assert (merged.at[0, "effective"], merged.at[0, "known_at"]) == (D1, pd.Timestamp(NOW))
    assert cumulative_map(None, rerun.upgrades.iloc[:0], NOW).empty


def _sources(names: list[str], tickers: list[dict[str, object]] | None) -> UniverseSources:
    files = {
        "nasdaqlisted": fx.nasdaq([(s, f"{s} Corp Common Stock", "N", "N") for s in names]),
        "otherlisted": fx.other([("ZZZ", "Zed Common Stock", "N", "N")]),  # never has a FIGI
        "options": fx.options(names),
    }

    def transport(url: str) -> bytes:
        if "massive" in url:
            return mfx.page(tickers or [])
        return next((v for k, v in files.items() if k in url), fx.spy([names[0]]))

    return UniverseSources(
        NasdaqTraderSource(http_for(transport, RetryPolicy(tries=1))),
        SpyHoldingsSource(http_for(transport)),
        MassiveTickers(http_for(transport)) if tickers else None,
    )


def test_universe_build_upgrades_ids_and_records_the_map() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    names = ["AAPL"]

    def build(day: date, tickers: list[dict[str, object]] | None, hour: int) -> dict:  # type: ignore[type-arg]
        clock = lambda: datetime(day.year, day.month, day.day, hour, tzinfo=UTC)  # noqa: E731
        return build_universe(
            task_ctx(writer, reader, clock), _sources(names, tickers), UniverseSettings(), day
        ).stats

    build(D1, None, 22)  # no Massive key: symbol ids
    assert set(reader.table("universe", D1)["instrument_id"]) == {"EQ:AAPL", "EQ:ZZZ"}  # type: ignore[index]
    stats = build(D2, [{"ticker": "AAPL", "type": "CS", "composite_figi": "BBG1"}], 22)
    assert stats["identifiers"]["ids_upgraded"] == 1
    assert stats["events"]["reference_change"] == {"id_changed": 1}  # no removed / added
    id_map = reader.table("instruments/id_map", D2)
    assert id_map is not None
    assert (id_map.at[0, "old_id"], id_map.at[0, "new_id"]) == ("EQ:AAPL", "EQ:BBG1")
    reference = reader.table("instruments/reference", D2)
    assert reference is not None and set(reference["instrument_id"]) == {"EQ:BBG1", "EQ:ZZZ"}
    rerun = build(D2, [{"ticker": "AAPL", "type": "CS", "composite_figi": "BBG1"}], 23)
    assert rerun["events"]["reference_change"] == {"id_changed": 1}  # same as the first run
    assert len(reader.table("instruments/id_map", D2)) == 1  # type: ignore[arg-type]
    stats = build(D3, None, 22)  # the key is gone again: the FIGI id stays
    assert stats["identifiers"]["ids_carried"] == 1
    assert resolver(reader, D3).id_for("AAPL") == "EQ:BBG1"
    assert reader.table("instruments/id_map", D3) is not None  # the full map, every snapshot


def test_first_build_upgrades_an_earlier_run_of_the_same_session() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    first = lambda: datetime(2026, 10, 1, 20, tzinfo=UTC)  # noqa: E731
    second = lambda: datetime(2026, 10, 1, 21, tzinfo=UTC)  # noqa: E731
    build_universe(
        task_ctx(writer, reader, first), _sources(["AAPL"], None), UniverseSettings(), D1
    )
    tickers = [{"ticker": "AAPL", "type": "CS", "composite_figi": "BBG1"}]
    stats = build_universe(
        task_ctx(writer, reader, second), _sources(["AAPL"], tickers), UniverseSettings(), D1
    ).stats
    assert stats["identifiers"]["ids_upgraded"] == 1


def test_rename_ids_follows_a_same_session_chain_in_recorded_order() -> None:
    """DFAC on 2026-10-02: upgraded to A, moved to B, then the owner's override back to A."""
    previous = pd.DataFrame({"instrument_id": ["EQ:DFAC", "EQ:KEEP"], "status": "ACTIVE"})
    chain = pd.DataFrame({
        "old_id": ["EQ:B", "EQ:DFAC", "EQ:A"], "new_id": ["EQ:A", "EQ:A", "EQ:B"],
        "known_at": pd.to_datetime(["2026-10-03T16:23Z", "2026-10-03T05:05Z",
                                    "2026-10-03T09:30Z"]),
    })  # fmt: skip
    renamed = rename_ids(previous, chain)
    assert renamed is not None and renamed["instrument_id"].tolist() == ["EQ:A", "EQ:KEEP"]
    halfway = rename_ids(previous, chain.iloc[1:])  # before the override: on B
    assert halfway is not None and halfway["instrument_id"].tolist() == ["EQ:B", "EQ:KEEP"]


def _listings(*rows: tuple[str, date | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": [t for t, _ in rows],
            "start_date": [date(2000 + 3 * i, 1, 3) for i in range(len(rows))],
            "end_date": [e for _, e in rows],
        }
    )


def _meta(*rows: tuple[str, str, bool]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["ticker", "perma_ticker", "is_active"])


def test_prm_matches_primedia_and_perimeter() -> None:
    listings = _listings(("PRM", date(2008, 5, 1)), ("PRM", None), ("AAPL", None), ("ZZZ", None))
    meta = _meta(
        ("PRM", "US000000041372", False),  # PRIMEDIA
        ("PRM", "US000000101493", True),  # Perimeter
        ("AAPL", "US000000000033", True),
    )
    perma, stats = match_perma(listings, meta)
    assert list(perma) == ["US000000041372", "US000000101493", "US000000000033", ""]
    assert stats == {"perma_matched": 3, "perma_no_meta": 1, "perma_ambiguous": 0}


def test_recycled_ticker_two_inactive_rows_stays_unmatched() -> None:
    listings = _listings(("AAC", date(2021, 4, 19)), ("AAC", date(2023, 11, 6)), ("AAC", None))
    meta = _meta(("AAC", "US1", False), ("AAC", "US2", False), ("AAC", "US3", True))
    perma, stats = match_perma(listings, meta)
    assert list(perma) == ["", "", "US3"]  # the open listing still matches the one active row
    assert stats["perma_ambiguous"] == 2 and stats["perma_matched"] == 1
    extra = _meta(("AAC", "US1", False), ("AAC", "US2", False))  # one delisted listing, two rows
    perma, stats = match_perma(_listings(("AAC", date(2021, 4, 19))), extra)
    assert list(perma) == [""] and stats["perma_ambiguous"] == 1


def test_a_listing_that_already_has_an_id_is_not_matched_but_still_counts() -> None:
    listings = _listings(("PRM", date(2008, 5, 1)), ("PRM", None))
    meta = _meta(("PRM", "US000000041372", False), ("PRM", "US000000101493", True))
    perma, stats = match_perma(listings, meta, pd.Series([True, False]))
    assert list(perma) == ["US000000041372", ""] and stats["perma_matched"] == 1
