import plistlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.config_files import MemoryConfigStore
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.quality import run_quality
from algotrade_ingestion.schedule import LABEL, nightly_plist
from algotrade_ingestion.settings import SourcesSettings, load_sources
from tests.storage_helpers import stamped, universe_rows

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
CLOCK = lambda: datetime(2026, 10, 2, 23, tzinfo=UTC)  # noqa: E731


def test_sources_settings_defaults_and_overrides() -> None:
    assert load_sources(MemoryConfigStore({})) == SourcesSettings()
    doc = {
        "raw_retention_days": 30,
        "cboe": {"workers": 8},
        "nasdaq_earnings": {"enabled": False, "days": 20},
        "massive": {"min_interval_s": 0.5, "corporate_actions_window": [-3, 10]},
        "quality": {"max_universe_change": 0.2},
        "sec_edgar": {"enabled": False, "min_interval_s": 0.5, "refresh_days": 7},
        "nasdaq_trader": "not a table",
    }
    s = load_sources(MemoryConfigStore({("site", "settings", "sources"): doc}))
    assert (s.raw_retention_days, s.cboe_workers, s.earnings_enabled, s.earnings_days) == (
        30,
        8,
        False,
        20,
    )
    assert (s.massive_min_interval_s, s.actions_window, s.max_universe_change) == (
        0.5,
        (-3, 10),
        0.2,
    )
    assert (s.sec_enabled, s.sec_min_interval_s, s.sec_refresh_days) == (False, 0.5, 7)
    assert s.universe_enabled  # a malformed section falls back to defaults


def bars(day: date, n: int) -> pd.DataFrame:
    ts = pd.Timestamp(day, tz="UTC")
    return stamped(
        [
            {
                "instrument_id": f"EQ:S{i}",
                "ts": ts,
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
            for i in range(n)
        ],
        day,
        f"b{day.day}",
    )


def seed(
    bars_d1: int, bars_d2: int | None, universe_d1: int, universe_d2: int, chain_ok: float = 1.0
) -> StoreReader:
    backend = MemoryBackend()
    w = StoreWriter(backend)
    w.write_table("bars/1d", D1, "b1", bars(D1, bars_d1))
    if bars_d2 is not None:
        w.write_table("bars/1d", D2, "b2", bars(D2, bars_d2))
    for day, n in ((D1, universe_d1), (D2, universe_d2)):
        rows = universe_rows([f"S{i}" for i in range(n)])
        w.write_table("universe", day, f"u{day.day}", stamped(rows, day, f"u{day.day}"))
    ok = int(chain_ok * 10)
    status = [
        {"instrument_id": f"EQ:S{i}", "status": "OK" if i < ok else "FETCH_ERROR: x"}
        for i in range(10)
    ]
    w.write_table("chains/status", D2, "c", stamped(status, D2, "c"))
    earnings = [{"instrument_id": "EQ:S1", "ts": pd.Timestamp(D2 + timedelta(5), tz="UTC")}]
    w.write_table("events/earnings", D2, "e", stamped(earnings, D2, "e"))
    return StoreReader(backend)


def checks(reader: StoreReader) -> dict[str, str]:
    record = run_quality(reader, StoreWriter(MemoryBackend()), D2, SourcesSettings(), CLOCK)
    return {c["name"]: c["status"] for c in record.stats["checks"]}


def test_quality_passes_on_healthy_data() -> None:
    assert set(checks(seed(1000, 990, 100, 101)).values()) == {"PASS"}


@pytest.mark.parametrize(
    ("args", "check"),
    [
        ((1000, None, 100, 100), "bars_fresh"),
        ((1000, 800, 100, 100), "bars_count"),
        ((1000, 1000, 100, 120), "universe_size"),
        ((1000, 1000, 100, 100, 0.8), "chains_coverage"),
    ],
)
def test_quality_failures(args: tuple, check: str) -> None:  # type: ignore[type-arg]
    reader = seed(*args)
    assert checks(reader)[check] == "FAIL"
    record = run_quality(reader, StoreWriter(MemoryBackend()), D2, SourcesSettings(), CLOCK)
    assert record.status is RunStatus.PARTIAL and check in record.stats["failed"]


def test_quality_on_an_empty_store() -> None:
    result = checks(StoreReader(MemoryBackend()))
    assert result == {
        "universe_present": "FAIL",
        "bars_present": "WARN",
        "chains_present": "WARN",
        "earnings_present": "WARN",
    }


def test_nightly_plist() -> None:
    plist = plistlib.loads(nightly_plist(Path("/repo"), 23, 30, Path("/repo/out")))
    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [
        "/repo/.venv/bin/algotrade-ingest",
        "nightly",
        "--export-dir",
        "/repo/out",
    ]
    assert [d["Weekday"] for d in plist["StartCalendarInterval"]] == [1, 2, 3, 4, 5]
    assert plist["StartCalendarInterval"][0]["Hour"] == 23
    with pytest.raises(ValueError, match="invalid time"):
        nightly_plist(Path("/repo"), 25, 0)
