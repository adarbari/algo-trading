"""FIGI-based ids in the universe build (ADR 0018): fallback, stability, upgrades."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import resolver
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.http import RetryPolicy
from algotrade_ingestion.sources.massive import MassiveTickers
from algotrade_ingestion.sources.nasdaq_trader import NasdaqTraderSource
from algotrade_ingestion.sources.spy_holdings import SpyHoldingsSource
from algotrade_ingestion.tasks.instrument_ids import assign_ids, cumulative_map, rename_ids
from algotrade_ingestion.tasks.universe_build import (
    UniverseSettings,
    UniverseSources,
    build_universe,
)
from tests import massive_fixture as mfx
from tests import universe_fixture as fx
from tests.ingest_helpers import http_for, task_ctx

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
