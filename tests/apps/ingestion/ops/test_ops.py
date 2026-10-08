import plistlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings, load_sources
from algotrade.data import StoreReader
from algotrade.data.chains import chain_status, tolerated_stale
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.ops.schedule import LABEL, MONTHLY_LABEL, monthly_fill_plist, nightly_plist
from algotrade_ingestion.tasks.maintenance.quality import check_chains, run_quality
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import chain_status_rows, stamped, universe_rows

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
CLOCK = lambda: datetime(2026, 10, 2, 23, tzinfo=UTC)  # noqa: E731
CIRCUIT = "FETCH_ERROR: cboe: circuit open after 10 consecutive 403/5xx"


def test_sources_settings_defaults_and_overrides() -> None:
    assert load_sources(MemoryConfigStore({})) == SourcesSettings()
    doc = {
        "raw_retention_days": 30,
        "staging_retention_days": 3,
        "cboe": {"workers": 8},
        "nasdaq_earnings": {"enabled": False, "days": 20},
        "massive": {"min_interval_s": 0.5, "corporate_actions_window": [-3, 10]},
        "quality": {"max_universe_change": 0.2},
        "sec_edgar": {"enabled": False, "min_interval_s": 0.5, "refresh_days": 7},
        "tiingo": {"monthly_symbol_budget": 300},
    }
    s = load_sources(MemoryConfigStore({("site", "settings", "sources"): doc}))
    earnings = s.vendor("nasdaq_earnings")
    assert (s.raw_retention_days, s.cboe_workers, earnings.enabled, s.earnings_days) == (
        30,
        8,
        False,
        20,
    )
    assert (s.vendor("massive").min_interval_s, s.actions_window, s.max_universe_change) == (
        0.5,
        (-3, 10),
        0.2,
    )
    sec = s.vendor("sec_edgar")
    assert (sec.enabled, sec.min_interval_s, s.sec_refresh_days) == (False, 0.5, 7)
    assert s.staging_retention_days == 3
    assert (s.tiingo_monthly_symbol_budget, SourcesSettings().tiingo_monthly_symbol_budget) == (
        300,
        450,
    )
    assert s.vendor("nasdaq_trader").enabled  # a malformed section falls back to defaults
    assert s.vendor("cboe").min_interval_s is None  # unset: the registry's default applies
    assert (s.http_max_retry_s, s.http_breaker_failures) == (300.0, 10)


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
    bars_d1: int,
    bars_d2: int | None,
    universe_d1: int,
    universe_d2: int,
    chains: list[str] | None = None,
    unresolved: int | None = None,
    status_rows: list[dict[str, str]] | None = None,
) -> StoreReader:
    backend = MemoryBackend()
    w = StoreWriter(backend)
    if unresolved is not None:  # the bars run for D2 and how many tickers it could not resolve
        run = RunRecord("daily_bars-x", "daily_bars", D2, CLOCK(), RunStatus.COMPLETE, CLOCK())
        run.stats = {"unresolved": unresolved}
        w.save_run(run)
    w.write_table("bars/1d", D1, "b1", bars(D1, bars_d1))
    if bars_d2 is not None:
        w.write_table("bars/1d", D2, "b2", bars(D2, bars_d2))
    for day, n in ((D1, universe_d1), (D2, universe_d2)):
        rows = universe_rows([f"S{i}" for i in range(n)])
        w.write_table("universe", day, f"u{day.day}", stamped(rows, day, f"u{day.day}"))
    chains = chains if chains is not None else ["OK"] * 20
    status = status_rows or [
        {"instrument_id": f"EQ:S{i}", "status": s} for i, s in enumerate(chains)
    ]
    w.write_table("chains/status", D2, "c", stamped(status, D2, "c"))
    earnings = [
        {
            "instrument_id": "EQ:S1",
            "ts": pd.Timestamp(D2 + timedelta(5), tz="UTC"),
            "known_from": D2,
        }
    ]
    w.write_table("events/earnings", D2, "e", stamped(earnings, D2, "e"))
    return StoreReader(backend)


def checks(reader: StoreReader) -> dict[str, str]:
    record = run_quality(task_ctx(StoreWriter(MemoryBackend()), reader, CLOCK), D2)
    # coverage (test_coverage.py) needs rollups and a reference snapshot these stores lack
    return {
        c["name"]: c["status"]
        for c in record.stats["checks"]
        if not c["name"].startswith("coverage")
    }


def test_quality_passes_on_healthy_data() -> None:
    assert set(checks(seed(1000, 990, 100, 101)).values()) == {"PASS"}


@pytest.mark.parametrize(
    ("args", "check"),
    [
        ((1000, None, 100, 100), "bars_fresh"),
        ((1000, 800, 100, 100), "bars_count"),
        ((1000, 1000, 100, 120), "universe_size"),
        ((1000, 1000, 100, 100, ["OK"] * 18 + ["FETCH_ERROR: x"] * 2), "chains_fetch"),
        ((1000, 1000, 100, 100, ["OK"] * 18 + [CIRCUIT, "NOT_ATTEMPTED"]), "chains_fetch"),
    ],
)
def test_quality_failures(args: tuple, check: str) -> None:  # type: ignore[type-arg]
    reader = seed(*args)
    assert checks(reader)[check] == "FAIL"
    record = run_quality(task_ctx(StoreWriter(MemoryBackend()), reader, CLOCK), D2)
    assert record.status is RunStatus.PARTIAL and check in record.stats["failed"]


def chain_check(chains: list[str], name: str) -> dict[str, str]:
    reader = seed(1000, 1000, 100, 100, chains)
    record = run_quality(task_ctx(StoreWriter(MemoryBackend()), reader, CLOCK), D2)
    check = next(c for c in record.stats["checks"] if c["name"] == name)
    return {**check, "run": record.status.value}


def test_chain_fetch_failures_up_to_the_threshold_pass() -> None:
    check = chain_check(["OK"] * 49 + [CIRCUIT], "chains_fetch")  # 2%: not over 2%
    assert check["status"] == "PASS"  # (the run is PARTIAL here: this store has no coverage data)
    assert chain_check(["OK"] * 19 + [CIRCUIT], "chains_fetch")["status"] == "FAIL"  # 5%


def test_stale_chains_over_the_share_fail() -> None:
    chains = ["OK"] * 13 + ["STALE_DATA: chain is for 2026-10-01"] * 5 + ["NO_CHAIN"] * 2
    check = chain_check(chains, "chains_stale_rest")  # 25% stale > 20%
    assert check["status"] == "FAIL" and check["run"] == RunStatus.PARTIAL.value
    assert (
        "OK 13, STALE_DATA 5, NO_CHAIN 2, NO_STANDARD_SERIES 0, fetch failures 0"
        in (check["detail"])
    )
    assert chain_check(chains, "chains_fetch")["status"] == "PASS"
    four = ["OK"] * 16 + ["STALE_DATA: x"] * 4  # 20%: not over 20%
    assert chain_check(four, "chains_stale_rest")["status"] == "PASS"


def tiered_checks(rows: list[tuple[str, str, str]], **quality: float) -> dict[str, dict[str, str]]:
    """(symbol, tier, status) rows stored as chains/status -> the quality checks by name."""
    status = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "tier": t, "status": st} for s, t, st in rows
    ]
    reader = seed(1000, 1000, 100, 100, status_rows=status)
    settings = SourcesSettings.from_document({"quality": quality})
    ctx = task_ctx(StoreWriter(MemoryBackend()), reader, CLOCK, settings=settings)
    return {c["name"]: c for c in run_quality(ctx, D2).stats["checks"]}


def test_core_chains_have_a_stricter_stale_limit_than_the_rest() -> None:
    core = [(f"C{i}", "core", "OK") for i in range(48)]
    core += [("AAPL", "core", "STALE_DATA: x"), ("MSFT", "core", "STALE_DATA: x")]  # 4% > 2%
    rest = [(f"R{i}", "rest", "OK") for i in range(80)] + [
        (f"S{i}", "rest", "STALE_DATA: x")
        for i in range(10)  # 11% < 20%
    ]
    result = tiered_checks([*core, *rest])
    assert result["chains_stale_core"]["status"] == "FAIL"
    assert (
        "2 of 50 core chains stale (4.0%, max 2%); stale: AAPL, MSFT"
        in (result["chains_stale_core"]["detail"])
    )
    assert result["chains_stale_rest"]["status"] == "PASS"
    one = [*core[:48], ("AAPL", "core", "STALE_DATA: x"), ("MSFT", "core", "OK")]  # 1 of 50: 2%
    assert tiered_checks(one)["chains_stale_core"]["status"] == "PASS"
    loose = tiered_checks(
        [*core, *rest], max_chain_stale_share_core=0.10, max_chain_stale_share=0.05
    )
    assert (loose["chains_stale_core"]["status"], loose["chains_stale_rest"]["status"]) == (
        "PASS",
        "FAIL",
    )


def test_a_status_without_a_tier_column_counts_as_rest() -> None:
    result = {c["name"]: c for c in run_quality(
        task_ctx(StoreWriter(MemoryBackend()), seed(1000, 1000, 100, 100, ["OK"] * 20), CLOCK), D2
    ).stats["checks"]}  # fmt: skip
    assert result["chains_stale_core"]["status"] == "PASS"  # legacy partition: nothing to grade
    assert "0 of 0 core" in result["chains_stale_core"]["detail"]


def test_a_tiered_status_with_no_core_name_fails_and_does_not_wait() -> None:
    check = tiered_checks(
        [("A", "rest", "OK")],
    )["chains_stale_core"]
    assert (check["status"], check["pending"]) == ("FAIL", False)
    assert "no core names" in check["detail"]


def test_stale_chains_are_pending_but_fetch_failures_never_are() -> None:
    """ADR 0043: Cboe not rolled yet may wait for the deadline; a failed fetch may not."""
    chains = ["OK"] * 10 + ["STALE_DATA: x"] * 10 + [CIRCUIT] * 2
    stale, fetch = (
        {
            c.name: c
            for c in check_chains(seed(1000, 1000, 100, 100, chains), D2, SourcesSettings())
        }[n]
        for n in ("chains_stale_rest", "chains_fetch")
    )
    assert (stale.status, stale.pending) == ("FAIL", True)
    assert (fetch.status, fetch.pending) == ("FAIL", False)


def test_chain_thresholds_come_from_sources_toml() -> None:
    settings = SourcesSettings.from_document(
        {"quality": {"max_chain_fetch_failures": 0.2, "max_chain_stale_share": 0.01}}
    )
    reader = seed(1000, 1000, 100, 100, ["OK"] * 18 + ["FETCH_ERROR: x", "STALE_DATA: x"])
    ctx = task_ctx(StoreWriter(MemoryBackend()), reader, CLOCK, settings=settings)
    result = {c["name"]: c["status"] for c in run_quality(ctx, D2).stats["checks"]}
    assert (result["chains_fetch"], result["chains_stale_rest"]) == ("PASS", "FAIL")


def test_unresolved_bars_over_the_share_fail() -> None:
    assert checks(seed(1000, 1000, 100, 100, unresolved=10))["bars_resolved"] == "PASS"  # 1%
    assert checks(seed(1000, 1000, 100, 100, unresolved=11))["bars_resolved"] == "FAIL"
    assert "bars_resolved" not in checks(seed(1000, 1000, 100, 100))  # no bars run recorded


def test_quality_on_an_empty_store() -> None:
    result = checks(StoreReader(MemoryBackend()))
    assert result == {
        "universe_present": "FAIL",
        "bars_present": "FAIL",
        "chains_present": "FAIL",
        "earnings_present": "FAIL",
    }


def test_nightly_plist() -> None:
    plist = plistlib.loads(nightly_plist(Path("/repo"), 15, 0, Path("/repo/out")))
    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [
        "/repo/.venv/bin/algotrade-ingest",
        "nightly",
        "--export-dir",
        "/repo/out",
    ]
    assert [d["Weekday"] for d in plist["StartCalendarInterval"]] == [1, 2, 3, 4, 5]
    assert {(d["Hour"], d["Minute"]) for d in plist["StartCalendarInterval"]} == {(15, 0)}
    assert plist["RunAtLoad"] is True  # login / boot catches up what was missed while off
    assert plist["StartInterval"] == 3600  # hourly watchdog; repeats are quiet no-ops
    assert plist["WorkingDirectory"] == "/repo"
    assert plist["StandardOutPath"] == "/repo/var/logs/nightly.log"
    assert plist["StandardErrorPath"] == "/repo/var/logs/nightly.err.log"
    custom = plistlib.loads(nightly_plist(Path("/repo"), 15, 0, watchdog_s=900))
    assert custom["StartInterval"] == 900 and custom["ProgramArguments"][-1] == "nightly"
    assert "StartInterval" not in plistlib.loads(nightly_plist(Path("/repo"), 15, 0, watchdog_s=0))
    with pytest.raises(ValueError, match="invalid time"):
        nightly_plist(Path("/repo"), 25, 0)
    with pytest.raises(ValueError, match="invalid watchdog"):
        nightly_plist(Path("/repo"), 15, 0, watchdog_s=-1)


def test_monthly_fill_plist() -> None:
    plist = plistlib.loads(monthly_fill_plist(Path("/repo")))
    assert plist["Label"] == MONTHLY_LABEL
    assert plist["ProgramArguments"] == [
        "/repo/.venv/bin/algotrade-ingest",
        "bars-history",
        "--fill",
        "450",
        "--wait",
    ]
    assert plist["StartCalendarInterval"] == {
        "Day": 2,
        "Hour": 19,
        "Minute": 0,
    }  # after the 15:00 nightly
    assert "RunAtLoad" not in plist and "StartInterval" not in plist  # monthly only
    assert plist["WorkingDirectory"] == "/repo"
    assert plist["StandardOutPath"] == "/repo/var/logs/bars-history-monthly.log"
    assert plist["StandardErrorPath"] == "/repo/var/logs/bars-history-monthly.err.log"
    for bad in ({"fill": 0}, {"day": 29}, {"hour": 24}):
        with pytest.raises(ValueError, match="invalid"):
            monthly_fill_plist(Path("/repo"), **bad)


# The chains acceptance check and the screens read one share (ADR 0054): whatever
# ``check_chains`` PASSes, ``tolerated_stale`` tolerates, and whatever it FAILs it does not.
CHAINS_DAY = date(2026, 10, 2)
SOURCES_DEFAULT = SourcesSettings()


@pytest.mark.parametrize(
    ("core_stale", "rest_stale", "fetch_errors", "chain_day", "passes"),
    [
        (0, 0, 0, "2026-10-01", True),
        (1, 10, 0, "2026-10-01", True),  # exactly 2% of core and 20% of rest
        (2, 10, 0, "2026-10-01", False),
        (1, 11, 0, "2026-10-01", False),
        (0, 0, 5, "2026-10-01", False),  # fetch failures over 2%
        (1, 10, 1, "2026-10-01", True),
        # stale for more than max_chain_stale_sessions (5): fetch failures, 11 of 100 over 2%
        (1, 10, 0, "2026-09-24", False),
        (1, 10, 0, "2026-09-25", True),  # exactly 5 sessions old: still stale, tolerated
    ],
)
def test_the_check_and_the_tolerance_agree(
    core_stale: int, rest_stale: int, fetch_errors: int, chain_day: str, passes: bool
) -> None:
    rows = chain_status_rows(50, core_stale, 50, rest_stale, fetch_errors, chain_day=chain_day)
    backend = MemoryBackend()
    StoreWriter(backend).write_table(
        "chains/status", CHAINS_DAY, "c", stamped(rows, CHAINS_DAY, "c")
    )
    reader = StoreReader(backend)
    assert (
        all(c.status == "PASS" for c in check_chains(reader, CHAINS_DAY, SOURCES_DEFAULT)) is passes
    )
    tolerated = tolerated_stale(chain_status(reader, CHAINS_DAY), CHAINS_DAY, SOURCES_DEFAULT)
    assert len(tolerated) == (core_stale + rest_stale if passes else 0)


def test_the_check_names_chronically_stale_chains_among_the_fetch_failures() -> None:
    rows = chain_status_rows(50, 0, 50, 3, chain_day="2026-09-23")
    backend = MemoryBackend()
    StoreWriter(backend).write_table(
        "chains/status", CHAINS_DAY, "c", stamped(rows, CHAINS_DAY, "c")
    )
    fetch = check_chains(StoreReader(backend), CHAINS_DAY, SOURCES_DEFAULT)[0]
    assert fetch.status == "FAIL"
    assert "STALE_DATA 0" in fetch.detail
    assert "fetch failures 3 (3 STALE_CHRONIC: stale over 5 sessions)" in fetch.detail
