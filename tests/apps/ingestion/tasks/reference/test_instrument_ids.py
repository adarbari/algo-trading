"""FIGI-based ids in the universe build (ADR 0018): fallback, stability, upgrades."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.core.model.instruments import equity_id
from algotrade.data import StoreReader
from algotrade.data.reference import resolver
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.instrument_ids import (
    assign_ids,
    assign_listing_ids,
    assign_listing_ids_counted,
    cumulative_map,
    figi_review_rows,
    match_perma,
    match_perma_reasons,
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
    # the open one is not asked for, but its permaTicker is known: the twin stays unambiguous
    assert list(perma) == ["US000000041372", "US000000101493"] and stats["perma_matched"] == 1


def test_single_delisted_listing_never_takes_active_row() -> None:
    perma, stats = match_perma(_listings(("OLD", date(2012, 1, 3))), _meta(("OLD", "US9", True)))
    assert list(perma) == [""] and stats["perma_ambiguous"] == 1
    perma, _ = match_perma(_listings(("LIVE", None)), _meta(("LIVE", "US8", False)))
    assert list(perma) == [""]  # an open listing never takes an inactive row either


def test_match_perma_says_why_a_listing_has_none() -> None:
    listings = _listings(("AAC", date(2021, 4, 19)), ("AAC", date(2023, 11, 6)), ("ZZZ", None))
    meta = _meta(("AAC", "US1", False), ("AAC", "US2", False))
    perma, why, stats = match_perma_reasons(listings, meta)
    assert list(perma) == ["", "", ""]
    assert list(why) == ["perma_ambiguous", "perma_ambiguous", "perma_no_meta"]
    assert stats["perma_ambiguous"] == 2 and stats["perma_no_meta"] == 1


# ------------------------------------------------------- listing ids (ADR 0087, the id order)


def _listing_rows(*rows: dict[str, object]) -> pd.DataFrame:
    base: dict[str, object] = {
        "source": "tiingo", "exchange": "NASDAQ", "asset_type": "Stock",
        "start_date": date(2005, 1, 3), "end_date": date(2015, 1, 2), "perma_ticker": "",
        "figi": None, "scope_reason": None,
    }  # fmt: skip
    return pd.DataFrame([{**base, **row} for row in rows])


def _history(*rows: tuple[str, str, date, date | None]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["instrument_id", "symbol", "valid_from", "valid_to"])


def test_the_figi_step_runs_only_after_symbol_history_and_the_perma_ticker_fail() -> None:
    listings = _listing_rows(
        {"ticker": "HIST", "figi": "BBG000HIST"},  # symbol_history first: its figi is not used
        {"ticker": "PERM", "perma_ticker": "US1", "figi": "BBG000PERM"},  # the perma next
        {"ticker": "FIGI", "figi": "BBG000FIGI"},  # neither: the figi
        {"ticker": "TWIN1", "figi": "BBG000TWIN"},  # one figi on two listings: none of them
        {"ticker": "TWIN2", "figi": "BBG000TWIN"},
        {"ticker": "HELD", "figi": "BBG000HELD"},  # its id is symbol_history's for another symbol
        {"ticker": "MAPPED", "figi": "BBG000MAP"},  # its id is an id_map new_id
    )
    history = _history(
        ("EQ:BBG000HIST", "HIST", date(2000, 1, 3), None),
        ("EQ:BBG000HELD", "RENAMED", date(2000, 1, 3), None),
    )
    out, stats = assign_listing_ids_counted(listings, history, None, {"EQ:BBG000MAP"})
    by = out.set_index("ticker")
    pairs = ["instrument_id", "id_source"]
    assert by.loc["HIST", pairs].tolist() == ["EQ:BBG000HIST", "symbol_history"]
    assert by.loc["PERM", pairs].tolist() == ["EQ:TIINGO:US1", "perma"]
    assert by.loc["FIGI", pairs].tolist() == ["EQ:BBG000FIGI", "figi"]
    assert by.loc[["TWIN1", "TWIN2"], "instrument_id"].isna().all()
    assert set(by.loc[["TWIN1", "TWIN2"], "no_id_reason"]) == {"figi_shared"}
    assert by.loc["HELD", "no_id_reason"] == "figi_held" and pd.isna(
        by.loc["HELD", "instrument_id"]
    )
    assert by.loc["MAPPED", "no_id_reason"] == "figi_held"
    assert stats["ids_by_figi"] == 1 and stats["no_id_figi_shared"] == 2


def test_a_perma_id_another_listing_holds_is_not_given_twice() -> None:
    listings = _listing_rows(
        {"ticker": "FIRST", "perma_ticker": "US7"},
        {
            "ticker": "SECOND",
            "perma_ticker": "US7",
            "start_date": date(2016, 1, 4),
            "end_date": None,
        },
    )
    out = assign_listing_ids(listings, None).set_index("ticker")
    assert out.loc["FIRST", "instrument_id"] == "EQ:TIINGO:US7"  # the first in order keeps it
    assert out.loc["SECOND", "no_id_reason"] == "perma_held"


def test_a_carried_id_is_never_upgraded_even_when_the_rules_now_give_another() -> None:
    previous = _listing_rows(
        {"ticker": "KEEP", "instrument_id": "EQ:TIINGO:US5", "id_source": "perma"},
        {"ticker": "OLDSTYLE", "instrument_id": "EQ:TIINGO:US6"},  # a partition before id_source
        {"ticker": "GONE", "source": "massive", "exchange": "NYSE",
         "instrument_id": "EQ:BBG000GONE", "id_source": "figi", "end_date": date(2020, 5, 1)},
    )  # fmt: skip
    listings = _listing_rows(
        {"ticker": "KEEP", "figi": "BBG000KEEP"},  # the rule would now give the symbol_history id
        {"ticker": "OLDSTYLE", "perma_ticker": "US6"},
        {"ticker": "GONE", "source": "massive", "exchange": "NYSE", "end_date": date(2020, 5, 1),
         "figi": "BBG000GONE"},
    )  # fmt: skip
    history = _history(("EQ:BBG000KEEP", "KEEP", date(2000, 1, 3), None))
    out, stats = assign_listing_ids_counted(listings, history, previous)
    by = out.set_index("ticker")
    assert by.loc["KEEP", "instrument_id"] == "EQ:TIINGO:US5"  # not EQ:BBG000KEEP
    assert by.loc["KEEP", "id_source"] == "perma"
    assert by.loc["OLDSTYLE", "id_source"] == "perma"  # inferred for an older partition
    assert by.loc["GONE", "instrument_id"] == "EQ:BBG000GONE"  # a Massive row: (ticker, end)
    assert stats["ids_carried"] == 3 and stats["ids_held"] == 1  # only KEEP differs


def test_no_id_is_ever_the_symbol_id_and_a_null_start_or_an_out_of_scope_row_has_none() -> None:
    listings = _listing_rows(
        {"ticker": "NONE"},  # nothing to build an id from
        {"ticker": "UNDATED", "start_date": None, "perma_ticker": "US2", "figi": "BBG000UND",
         "no_id_reason": "perma_ambiguous"},
        {"ticker": "OTC", "scope_reason": "other_exchange", "perma_ticker": "US3"},
        {"ticker": "OK", "perma_ticker": "US4"},
    )  # fmt: skip
    out = assign_listing_ids(listings, None).set_index("ticker")
    assert out["instrument_id"].dropna().tolist() == ["EQ:TIINGO:US4"]
    assert out.loc["NONE", "no_id_reason"] == "no_perma"
    assert out.loc["UNDATED", "no_id_reason"] == "perma_ambiguous"  # the reason it was given
    assert out.loc["OTC", "no_id_reason"] == "out_of_scope"
    assert not any(i == equity_id(t) for t, i in out["instrument_id"].dropna().items())
