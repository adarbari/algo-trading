"""``analyst-snapshot``: the nightly slice of analyst data appended to
``analyst/estimate_snapshots`` (point in time: ``ts`` = fetch, never replaced by a later session),
rotated within ``[fmp] daily_budget``, a refused name asked once and then held back."""

import json
import zlib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from itertools import count

import pandas as pd
import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.schemas import validate_frame
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.snapshot import ACCESS, TABLE, run
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.quality import check_analyst_snapshot
from algotrade_ingestion.workflows.nightly.nightly import EDGE_SIGNALS, NIGHTLY
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
    broken: frozenset[str] = frozenset(),
    empty: frozenset[str] = frozenset(),
    finnhub_days: int = 7,
    run_budget_s: int = 1500,
    dup: frozenset[str] = frozenset(),
) -> TaskContext:
    def get(url: str) -> bytes:
        calls.append(url)
        symbol = url.split("symbol=")[1].split("&", maxsplit=1)[0]
        if symbol in broken:
            raise HttpError(500, body=b"boom")
        if symbol in empty:
            return b"[]"
        if "finnhub" in url:
            return RECOMMENDATION.replace(b"AAPL", symbol.encode())
        if symbol == "CHWY":
            raise HttpError(402, body=PREMIUM)
        for fragment, payload in FMP_PAYLOADS.items():
            if fragment in url:
                body = payload
                if symbol in dup and "analyst-estimates" in fragment:
                    rows = json.loads(payload)
                    body = json.dumps([*rows, rows[0]]).encode()  # a repeated fiscal date
                return body.replace(b"AAPL", symbol.encode())
        raise AssertionError(url)

    fmp, finnhub = http_for(get, RetryPolicy(rejected=refused)), http_for(get)
    sources = {
        "fmp_targets": FmpPriceTargets(fmp),
        "fmp_ratings": FmpRatings(fmp),
        "fmp_estimates": FmpAnalystEstimates(fmp),
        "finnhub_recommendations": FinnhubRecommendations(finnhub),
    }
    settings = SourcesSettings(
        fmp_daily_budget=budget,
        finnhub_per_night=per_night,
        finnhub_refresh_days=finnhub_days,
        fmp_run_budget_s=run_budget_s,
    )
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
    data = got[got["kind"] != "coverage"]
    kinds = data.groupby(["instrument_id", "source"])["kind"].agg(lambda k: sorted(set(k)))
    assert kinds["EQ:AAPL", "fmp"] == ["estimates_annual", "grades", "price_target"]
    assert kinds["EQ:NVDA", "finnhub"] == ["recommendation"]
    assert "EQ:CHWY" in set(data["instrument_id"])
    assert not (
        (data["instrument_id"] == "EQ:CHWY") & (data["source"] == "fmp")
    ).any()  # Finnhub only
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
    kinds = set(stored(context(writer, D1, []), D1)["kind"])
    assert kinds == {"estimates_annual", "price_target", "coverage"}


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


def markers(ctx: TaskContext, day: date) -> dict[tuple[str, str], str]:
    """(instrument_id, source) -> the coverage status stored for the session."""
    got = stored(ctx, day)
    rows = got[got["kind"] == "coverage"]
    assert (rows["period"] == "current").all()
    ids, sources, statuses = rows["instrument_id"], rows["source"], rows["status"]
    return {(i, s): st for i, s, st in zip(ids, sources, statuses, strict=True)}


def test_a_refused_name_stores_a_not_covered_marker_and_an_answered_one_ok() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    ctx = context(writer, D1, [])
    run(ctx, {"session": D1})
    assert markers(ctx, D1) == {
        ("EQ:AAPL", "fmp"): "OK",
        ("EQ:AAPL", "finnhub"): "OK",
        ("EQ:NVDA", "fmp"): "OK",
        ("EQ:NVDA", "finnhub"): "OK",
        ("EQ:CHWY", "fmp"): "NOT_COVERED",
        ("EQ:CHWY", "finnhub"): "OK",
    }
    got = stored(ctx, D1)
    validate_frame(TABLE, got)
    fmp_chwy = got[(got["instrument_id"] == "EQ:CHWY") & (got["source"] == "fmp")]
    assert list(fmp_chwy["kind"]) == ["coverage"]  # a marker and no estimate rows


def test_a_failed_or_empty_attempt_is_not_read_as_not_covered() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL", "NVDA", "MSFT"))
    ctx = context(writer, D1, [], broken=frozenset({"NVDA"}), empty=frozenset({"MSFT"}))
    run(ctx, {"session": D1})
    got = markers(ctx, D1)
    assert got["EQ:NVDA", "fmp"] == got["EQ:NVDA", "finnhub"] == "FAILED"
    assert got["EQ:MSFT", "fmp"] == got["EQ:MSFT", "finnhub"] == "EMPTY"
    assert got["EQ:AAPL", "fmp"] == "OK"
    validate_frame(TABLE, stored(ctx, D1))


def test_markers_are_point_in_time_and_merge_within_a_session() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL", "NVDA"))
    run(context(writer, D1, [], broken=frozenset({"NVDA"})), {"session": D1})
    again = context(writer, D1, [], hour=15)  # the same session, a later run: NVDA works now
    run(again, {"session": D1})
    got = stored(again, D1)
    mine = got[got["kind"] == "coverage"]
    assert not mine.duplicated(["instrument_id", "source", "period"]).any()
    assert markers(again, D1)["EQ:NVDA", "fmp"] == "OK"  # the retry replaced the FAILED marker
    assert (mine["knowledge_ts"] >= mine["ts"]).all() and (mine["ts"].dt.date == D1).all()


def test_a_refused_name_is_asked_again_after_four_refresh_windows() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("CHWY",))
    run(context(writer, D1, []), {"session": D1})
    held, calls = D1 + timedelta(days=27), []
    run(context(writer, held, calls), {"session": held})
    assert not any("financialmodelingprep" in c for c in calls)
    due, calls = D1 + timedelta(days=28), []
    ctx = context(writer, due, calls)
    run(ctx, {"session": due})
    assert sum("symbol=CHWY" in c and "financialmodelingprep" in c for c in calls) == 1
    assert markers(ctx, due)["EQ:CHWY", "fmp"] == "NOT_COVERED"


def test_finnhub_rotates_on_its_own_refresh_days() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL",))
    run(context(writer, D1, [], finnhub_days=3), {"session": D1})
    d2 = D1 + timedelta(days=3)  # past Finnhub's 3 days, inside FMP's 7
    record = run(context(writer, d2, [], finnhub_days=3), {"session": d2})
    assert record.stats["finnhub"]["names"] == ["AAPL"] and record.stats["fmp"]["asked"] == 0


def test_a_spent_run_budget_stops_the_calls_and_the_next_night_continues() -> None:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer, ("AAPL", "NVDA", "MSFT", "AMD"))
    first = run(context(writer, D1, calls, run_budget_s=8), {"session": D1})  # the clock ticks 1 s
    over = [k for k, v in first.items.items() if v.startswith("OVER_BUDGET: [fmp] run_budget_s")]
    assert over and 0 < first.stats["fmp"]["fetched"] < 4
    assert first.status is RunStatus.COMPLETE
    assert any(k.startswith("finnhub:") for k in over) or len(calls) < 16  # no call after it
    d2 = D1 + timedelta(days=1)
    second = run(context(writer, d2, [], budget=200), {"session": d2})
    fmp_first = {k.split(":")[1] for k, v in first.items.items() if v == "OK" and "fmp" in k[:4]}
    assert set(second.stats["fmp"]["names"]) >= {"AAPL", "AMD", "MSFT", "NVDA"} - fmp_first


def test_the_rotation_advances_when_the_probe_denies_price_targets() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL", "NVDA", "MSFT", "AMD", "CHWY"), denied=("fmp:price_targets",))
    first = run(context(writer, D1, [], budget=8), {"session": D1})  # 2 calls a name: 4 names
    assert first.stats["fmp"]["names"] == ["AAPL", "AMD", "CHWY", "MSFT"]
    d2, calls = D1 + timedelta(days=1), []
    second = run(context(writer, d2, calls), {"session": d2})
    assert second.stats["fmp"]["names"][0] == "NVDA"  # the new name first, not AAPL again
    assert "CHWY" not in second.stats["fmp"]["names"]
    assert second.stats["fmp"]["held_not_covered"] == 1
    assert not any("symbol=CHWY" in c and "financialmodelingprep" in c for c in calls)


def test_the_refresh_cadence_counts_from_the_session_not_the_start_date() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL",))
    slot = zlib.crc32(b"AAPL") % 7
    slot_day = next(
        d for d in (D1 + timedelta(days=n) for n in range(7)) if d.toordinal() % 7 == slot
    )
    # the nightly for session slot_day - 1 starts after midnight UTC, on the slot day itself
    run(context(writer, slot_day, []), {"session": slot_day - timedelta(days=1)})
    record = run(context(writer, slot_day, [], hour=12), {"session": slot_day})
    assert record.stats["fmp"]["names"] == ["AAPL"]  # fetched before its slot day: due again


def test_a_session_before_the_last_closed_one_is_refused() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer)
    old = D1 - timedelta(days=30)
    with pytest.raises(ValueError, match="before the last closed session"):
        run(context(writer, D1, []), {"session": old})
    assert not writer.runs_for("analyst-snapshot")


def test_a_repeated_fiscal_date_is_deduplicated_and_the_night_publishes() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL",))
    ctx = context(writer, D1, [], dup=frozenset({"AAPL"}))
    assert run(ctx, {"session": D1}).status is RunStatus.COMPLETE
    got = stored(ctx, D1)
    validate_frame(TABLE, got)
    assert not got.duplicated(["instrument_id", "source", "kind", "period"]).any()


def test_the_acceptance_warns_when_nothing_returned_data_even_with_markers_stored() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL",))
    ctx = context(writer, D1, [], empty=frozenset({"AAPL"}))
    run(ctx, {"session": D1})
    assert not stored(ctx, D1).empty  # the coverage markers are rows
    checks = check_analyst_snapshot(ctx, D1)
    assert [c.status for c in checks] == ["WARN"] and "refused or empty" in checks[0].detail


def test_the_acceptance_warns_when_too_many_calls_failed() -> None:
    writer = StoreWriter(MemoryBackend())
    seed(writer, ("AAPL", "NVDA", "MSFT"))
    ctx = context(writer, D1, [], broken=frozenset({"NVDA", "MSFT"}))
    run(ctx, {"session": D1})
    checks = check_analyst_snapshot(ctx, D1)
    assert [c.status for c in checks] == ["WARN"] and "vendor calls failed" in checks[0].detail


def test_the_nightly_step_runs_after_the_screens_and_edge_signals() -> None:
    names = [step.name for step in NIGHTLY]
    assert names.index("analyst-snapshot") > names.index(EDGE_SIGNALS) > names.index("screens")
