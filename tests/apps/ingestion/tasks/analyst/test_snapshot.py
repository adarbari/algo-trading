"""``analyst-snapshot``: the nightly slice of analyst data appended to
``analyst/estimate_snapshots`` (point in time: ``ts`` = fetch, never replaced by a later session),
rotated within ``[fmp] daily_budget``, a refused name asked once and then held back."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from itertools import count

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.schemas import validate_frame
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.snapshot import ACCESS, TABLE, run
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.quality import check_analyst_snapshot
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.finnhub.recommendations import FinnhubRecommendations
from algotrade_sources.vendors.fmp.client import refused
from algotrade_sources.vendors.fmp.estimates import FmpAnalystEstimates
from algotrade_sources.vendors.fmp.targets import FmpPriceTargets, FmpRatings
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import stamped

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources"
FMP_PAYLOADS = {
    "analyst-estimates": (FIXTURES / "fmp" / "analyst_estimates_annual_aapl.json").read_bytes(),
    "price-target-consensus": (FIXTURES / "fmp" / "price_target_consensus_aapl.json").read_bytes(),
    "grades-consensus": (FIXTURES / "fmp" / "grades_consensus_aapl.json").read_bytes(),
}
RECOMMENDATION = (FIXTURES / "finnhub" / "recommendation_aapl.json").read_bytes()
PREMIUM = (FIXTURES / "fmp" / "premium_402_symbol.txt").read_bytes()
D1 = date(2026, 10, 16)
REFERENCE_DAY = date(2026, 10, 15)
SP500 = ("AAPL", "NVDA", "CHWY")  # CHWY: the free FMP plan refuses it (recorded 2026-10-16)


def clock(day: date, hour: int = 9) -> Callable[[], datetime]:
    ticks = count()
    return lambda: (
        datetime(day.year, day.month, day.day, hour, tzinfo=UTC) + timedelta(seconds=next(ticks))
    )


def seed(
    writer: StoreWriter, symbols: tuple[str, ...] = SP500, denied: tuple[str, ...] = ()
) -> None:
    rows = [
        {
            "instrument_id": f"EQ:{s}",
            "symbol": s,
            "asset_class": "EQ",
            "security_type": "COMMON_STOCK",
            "multiplier": 1.0,
            "status": "ACTIVE",
            "in_sp500": True,
        }
        for s in symbols
    ]
    writer.write_table(
        "instruments/reference", REFERENCE_DAY, "ref", stamped(rows, REFERENCE_DAY, "ref")
    )
    if denied:
        access = [
            {"endpoint": e, "status": "DENIED", "http_code": 402, "checked_ts": pd.Timestamp(D1)}
            for e in denied
        ]
        frame = pd.DataFrame(access).assign(note="x", rows=0)
        frame["source"] = [d.split(":")[0] for d in denied]
        frame["endpoint"] = [d.split(":")[1] for d in denied]
        frame = frame.assign(session_date=REFERENCE_DAY, knowledge_ts=pd.Timestamp(D1), run_id="p")
        writer.write_table(ACCESS, REFERENCE_DAY, "p", frame)


def context(
    writer: StoreWriter,
    day: date,
    calls: list[str],
    budget: int = 200,
    per_night: int = 300,
    hour: int = 9,
) -> TaskContext:
    def get(url: str) -> bytes:
        calls.append(url)
        symbol = url.split("symbol=")[1].split("&", maxsplit=1)[0]
        if "finnhub" in url:
            return RECOMMENDATION.replace(b"AAPL", symbol.encode())
        if symbol == "CHWY":
            raise HttpError(402, body=PREMIUM)
        for fragment, payload in FMP_PAYLOADS.items():
            if fragment in url:
                return payload.replace(b"AAPL", symbol.encode())
        raise AssertionError(url)

    fmp, finnhub = http_for(get, RetryPolicy(rejected=refused)), http_for(get)
    sources = {
        "fmp_targets": FmpPriceTargets(fmp),
        "fmp_ratings": FmpRatings(fmp),
        "fmp_estimates": FmpAnalystEstimates(fmp),
        "finnhub_recommendations": FinnhubRecommendations(finnhub),
    }
    settings = SourcesSettings(fmp_daily_budget=budget, finnhub_per_night=per_night)
    return task_ctx(writer, clock=clock(day, hour), sources=sources, settings=settings)


def stored(ctx: TaskContext, day: date) -> pd.DataFrame:
    frame = ctx.reader.table(TABLE, day)
    assert frame is not None
    return frame


def test_a_night_stores_every_kind_and_asks_a_refused_name_once() -> None:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer)
    ctx = context(writer, D1, calls)
    record = run(ctx, {"session": D1})
    assert record.status is RunStatus.COMPLETE
    got = stored(ctx, D1)
    validate_frame(TABLE, got)
    kinds = got.groupby(["instrument_id", "source"])["kind"].agg(lambda k: sorted(set(k)))
    assert kinds["EQ:AAPL", "fmp"] == ["estimates_annual", "grades", "price_target"]
    assert kinds["EQ:NVDA", "finnhub"] == ["recommendation"]
    assert (
        "EQ:CHWY" in set(got["instrument_id"])
        and not ((got["instrument_id"] == "EQ:CHWY") & (got["source"] == "fmp")).any()
    )  # only Finnhub served CHWY
    assert sum("symbol=CHWY" in c and "financialmodelingprep" in c for c in calls) == 1
    target = got[(got["instrument_id"] == "EQ:AAPL") & (got["kind"] == "price_target")].iloc[0]
    assert target["period"] == "current" and target["target_consensus"] > 0
    estimate = got[(got["instrument_id"] == "EQ:AAPL") & (got["kind"] == "estimates_annual")]
    assert "2030-09-27" in set(estimate["period"]) and estimate["eps_avg"].notna().all()
    assert record.items["fmp:CHWY:price_target"].startswith("NOT_COVERED")
    assert record.stats["fmp"]["not_covered"] == 1 and record.stats["fmp"]["fetched"] == 2
    assert record.stats["licence"] == {"fmp": "personal", "finnhub": "personal"}


def test_ts_is_the_fetch_instant_and_knowledge_is_not_before_it() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1})
    got = stored(ctx, D1)
    assert (got["ts"].dt.date == D1).all()
    assert (got["knowledge_ts"] >= got["ts"]).all()
    assert got["ts"].nunique() > 1  # each call is stamped when it was made


def test_a_later_night_appends_and_never_replaces_the_earlier_session() -> None:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer)
    run(context(writer, D1, calls), {"session": D1})
    first = stored(context(writer, D1, []), D1).sort_values(["instrument_id", "kind"])
    d2 = D1 + timedelta(days=8)  # past the 7-day refresh; CHWY is held for four windows
    calls.clear()
    ctx = context(writer, d2, calls)
    record = run(ctx, {"session": d2})
    assert record.status is RunStatus.COMPLETE
    again = stored(ctx, D1).sort_values(["instrument_id", "kind"])
    pd.testing.assert_frame_equal(first.reset_index(drop=True), again.reset_index(drop=True))
    assert not stored(ctx, d2).empty
    assert not any("symbol=CHWY" in c and "financialmodelingprep" in c for c in calls)
    assert record.stats["fmp"]["held_not_covered"] == 1


def test_names_rotate_within_the_daily_budget_new_names_first() -> None:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer, ("AAPL", "NVDA", "MSFT", "AMD"))
    ctx = context(writer, D1, calls, budget=7, per_night=2)  # 7 calls: two names of three calls
    first = run(ctx, {"session": D1})
    assert first.stats["fmp"]["names"] == ["AAPL", "AMD"]
    assert first.stats["finnhub"]["names"] == ["AAPL", "AMD"]
    d2 = D1 + timedelta(days=1)
    second = run(context(writer, d2, [], budget=7, per_night=2), {"session": d2})
    assert second.stats["fmp"]["names"] == ["MSFT", "NVDA"]  # the ones not yet fetched
    assert second.stats["finnhub"]["names"] == ["MSFT", "NVDA"]


def test_the_budget_counts_the_probe_and_earlier_runs_of_the_day() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL", "NVDA"))
    first = run(context(writer, D1, [], budget=3), {"session": D1})
    assert first.stats["fmp"]["asked"] == 1
    again = run(context(writer, D1, [], budget=3, hour=15), {"session": D1})  # same UTC day: spent
    assert again.stats["fmp"]["asked"] == 0 and again.stats["fmp"]["calls_before"] == 3


def test_a_kind_the_probe_denied_is_not_asked() -> None:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer, ("AAPL",), denied=("fmp:ratings_summary", "finnhub:recommendation"))
    record = run(context(writer, D1, calls), {"session": D1})
    assert not any("grades-consensus" in c or "finnhub" in c for c in calls)
    assert record.stats["denied"] == ["finnhub/recommendation", "fmp/ratings_summary"]
    assert set(stored(context(writer, D1, []), D1)["kind"]) == {"estimates_annual", "price_target"}


def test_no_configured_vendor_fails_the_run() -> None:
    writer = StoreWriter(MemoryBackend())
    ctx = task_ctx(writer, clock=clock(D1))
    assert run(ctx, {"session": D1}).status is RunStatus.FAILED


def test_the_task_is_registered_and_its_check_warns_only_on_failures() -> None:
    assert TASKS["analyst-snapshot"].tables == (TABLE,)
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL",))
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1})
    assert [c.status for c in check_analyst_snapshot(ctx, D1)] == ["PASS"]
    assert check_analyst_snapshot(ctx, D1 + timedelta(days=3)) == []
