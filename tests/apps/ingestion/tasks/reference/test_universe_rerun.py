"""Same-session re-runs of the universe build keep cumulative state (2026-10-03).

The 2026-10-02 store: built at 04:08Z with symbol ids, rebuilt at 05:05Z with FIGIs (10,817
upgrades), re-run at 09:30Z by the nightly. The re-run started from nothing, so its id map
held 3 upgrades and hid the 10,817; ``migrate-ids`` then mapped 3 ids. These tests replay
that on both backends.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.sources.framework.http import RetryPolicy
from algotrade_ingestion.sources.vendors.massive.tickers import MassiveTickers
from algotrade_ingestion.sources.vendors.nasdaq.symbol_directory import NasdaqTraderSource
from algotrade_ingestion.sources.vendors.ssga.spy_holdings import SpyHoldingsSource
from algotrade_ingestion.tasks.maintenance.migrate_ids import load_id_map, migrate_ids
from algotrade_ingestion.tasks.reference.instrument_ids import ID_MAP
from algotrade_ingestion.tasks.reference.universe_build import (
    HISTORY,
    REFERENCE,
    UniverseSettings,
    UniverseSources,
    build_universe,
)
from tests import massive_fixture as mfx
from tests import universe_fixture as fx
from tests.ingest_helpers import http_for, task_ctx
from tests.storage_helpers import T0, stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
CHANGES = "events/reference_change"


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Backend:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    return factories[request.param]()


def figis(*symbols: str) -> dict[str, str]:
    return {s: f"BBG_{s}" for s in symbols}


def sources(names: list[str], figi: dict[str, str] | None) -> UniverseSources:
    files = {
        "nasdaqlisted": fx.nasdaq([(s, f"{s} Corp Common Stock", "N", "N") for s in names]),
        "otherlisted": fx.other([("ZZZ", "Zed Common Stock", "N", "N")]),  # never has a FIGI
        "options": fx.options(names),
    }
    tickers = [{"ticker": s, "type": "CS", "composite_figi": f} for s, f in (figi or {}).items()]

    def transport(url: str) -> bytes:
        if "massive" in url:
            return mfx.page(tickers)
        return next((v for k, v in files.items() if k in url), fx.spy(names[:1]))

    return UniverseSources(
        NasdaqTraderSource(http_for(transport, RetryPolicy(tries=1))),
        SpyHoldingsSource(http_for(transport)),
        MassiveTickers(http_for(transport)) if figi is not None else None,
    )


class Store:
    def __init__(self, backend: Backend) -> None:
        self.writer, self.reader = StoreWriter(backend), StoreReader(backend)

    def build(
        self, day: date, at: datetime, names: list[str], figi: dict[str, str] | None
    ) -> dict[str, Any]:
        ctx = task_ctx(self.writer, self.reader, lambda: at)
        return build_universe(ctx, sources(names, figi), UniverseSettings(), day).stats

    def table(self, name: str, day: date) -> pd.DataFrame:
        frame = self.reader.table(name, day)
        assert frame is not None, name
        return frame


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, tzinfo=UTC)


NAMES = ["AAPL", "KO", "MSFT", "NEWF"]


def replay(store: Store) -> None:
    """04:08 symbol ids; 05:05 FIGIs for three; 09:30 the nightly, one more FIGI."""
    store.build(D2, at(4, 8), NAMES, None)
    store.build(D2, at(5, 5), NAMES, figis("AAPL", "KO", "MSFT"))
    store.build(D2, at(9, 30), NAMES, figis("AAPL", "KO", "MSFT", "NEWF"))


def test_a_same_session_rerun_keeps_the_id_map(backend: Backend) -> None:
    store = Store(backend)
    replay(store)
    id_map = store.table(ID_MAP, D2).set_index("old_id")
    assert sorted(id_map.index) == ["EQ:AAPL", "EQ:KO", "EQ:MSFT", "EQ:NEWF"]
    known = pd.to_datetime(id_map["known_at"], utc=True)
    assert known["EQ:AAPL"] == pd.Timestamp(at(5, 5))  # first recorded, not re-stamped
    assert known["EQ:NEWF"] == pd.Timestamp(at(9, 30))
    # the 09:30 run itself holds the whole map, not only its own upgrade
    latest = store.reader.table(ID_MAP, D2, as_of=at(9, 31))
    assert latest is not None and len(latest) == 4
    assert set(latest["run_id"]) == {"universe_build-2026-10-02-20261003T093000Z"}
    stats = store.build(D2, at(11, 1), NAMES, figis("AAPL", "KO", "MSFT", "NEWF"))
    assert stats["identifiers"]["ids_upgraded"] == 0 and len(store.table(ID_MAP, D2)) == 4


def test_the_id_map_merges_so_a_partial_run_cannot_hide_history(backend: Backend) -> None:
    """A run written the old way (only its own upgrades) no longer hides earlier ones."""
    store = Store(backend)
    store.build(D2, at(4, 8), NAMES, None)
    store.build(D2, at(5, 5), NAMES, figis("AAPL", "KO", "MSFT"))
    partial = store.table(ID_MAP, D2).iloc[:1].copy()
    partial["run_id"], partial["knowledge_ts"] = "partial", pd.Timestamp(at(9, 30))
    store.writer.write_table(ID_MAP, D2, "partial", partial)
    assert len(store.table(ID_MAP, D2)) == 3
    assert len(load_id_map(store.reader)) == 3


def test_a_rerun_keeps_history_first_seen_and_delistings(backend: Backend) -> None:
    store = Store(backend)
    store.build(D1, at(1), ["AAPL", "OLD"], figis("AAPL", "OLD"))
    store.build(D2, at(4), ["AAPL", "OLD", "BRIEF"], figis("AAPL", "OLD", "BRIEF"))
    store.build(D2, at(9), ["AAPL"], figis("AAPL"))  # OLD and BRIEF are gone in the re-run
    reference = store.table(REFERENCE, D2).set_index("symbol")
    assert reference.loc["AAPL", "first_seen"] == D1
    assert reference.loc["OLD", "status"] == "DELISTED"
    assert reference.loc["OLD", "delisted_on"] == D2 and reference.loc["OLD", "first_seen"] == D1
    assert reference.loc["BRIEF", "status"] == "DELISTED"  # seen by the earlier run
    history = store.table(HISTORY, D2).set_index("symbol")
    assert set(history.index) == {"AAPL", "OLD", "BRIEF"}
    assert history.loc["OLD", "valid_to"] == D2 and history.loc["BRIEF", "valid_to"] == D2
    assert pd.isna(history.loc["AAPL", "valid_to"]) and history.loc["AAPL", "valid_from"] == D1


def test_a_rerun_does_not_duplicate_events(backend: Backend) -> None:
    store = Store(backend)
    store.build(D1, at(1), ["AAPL", "OLD"], None)
    first = store.build(D2, at(4), ["AAPL", "NEWC"], figis("AAPL"))
    events = store.table(CHANGES, D2)
    again = store.build(D2, at(9), ["AAPL", "NEWC"], figis("AAPL"))
    assert again["events"] == first["events"]
    assert first["events"]["reference_change"] == {"added": 1, "removed": 1, "id_changed": 1}
    after = store.table(CHANGES, D2)
    assert len(after) == len(events) == 3
    assert not after.duplicated(["instrument_id", "change"]).any()
    assert set(after["run_id"]) == {"universe_build-2026-10-02-20261003T090000Z"}


def test_an_upgrade_between_runs_of_a_session_is_not_a_delisting(backend: Backend) -> None:
    store = Store(backend)
    store.build(D1, at(1), ["AAPL"], None)
    store.build(D2, at(4), ["AAPL"], None)  # still symbol ids
    stats = store.build(D2, at(5), ["AAPL"], figis("AAPL"))
    assert stats["events"]["reference_change"] == {"id_changed": 1}
    reference = store.table(REFERENCE, D2)
    assert list(reference["status"]) == ["ACTIVE", "ACTIVE"]  # EQ:BBG_AAPL, EQ:ZZZ


def test_migrate_ids_after_a_rerun_maps_every_upgrade(backend: Backend) -> None:
    store = Store(backend)
    dividends = [
        {"instrument_id": f"EQ:{s}", "ts": pd.Timestamp(D2 - timedelta(days=91 * q), tz="UTC"),
         "cash_amount": 0.25}
        for s in NAMES for q in range(4)
    ]  # fmt: skip
    store.writer.write_table("events/dividend", D2, "ca1", stamped(dividends, D2, "ca1", T0))
    replay(store)
    record = migrate_ids(task_ctx(store.writer, store.reader, lambda: at(12)))
    assert record.stats["mapped_ids"] == 4
    assert record.stats["tables"]["events/dividend"] == {"partitions": 1, "rows": 16}
    merged = store.table("events/dividend", D2)
    assert len(merged) == 16
    assert set(merged["instrument_id"]) == {f"EQ:BBG_{s}" for s in NAMES}
