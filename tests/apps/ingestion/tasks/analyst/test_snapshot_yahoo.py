"""``analyst-snapshot``'s Yahoo step (ADR 0080): only names FMP refuses are asked, one call each,
largest market cap first, within ``[yahoo] per_night`` and its own run budget, fail-soft, and its
rows are stored with source ``yahoo`` and read back by ``stored_snapshots``."""

import dataclasses
from datetime import timedelta

from algotrade.config.site.vendors.yahoo import YahooSettings
from algotrade.data.analyst.reading import stored_snapshots
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.schemas import validate_frame
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst.snapshot import TABLE, run
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.yahoo.analyst import YahooAnalyst
from algotrade_sources.vendors.yahoo.client import refused
from tests.apps.ingestion.tasks.analyst.test_snapshot import (
    D1,
    FIXTURES,
    context,
    fmp_calls,
    markers,
    seed,
    seed_caps,
    stored,
)
from tests.helpers.ingest_fakes import http_for

ARX = (FIXTURES / "yahoo" / "quote_summary_arx.json").read_bytes()
NOT_FOUND = (FIXTURES / "yahoo" / "not_found_404.json").read_bytes()
HOLD = timedelta(days=4 * 14)


def with_yahoo(
    ctx: TaskContext,
    calls: list[str],
    broken: frozenset[str] = frozenset(),
    unknown: frozenset[str] = frozenset(),
    **settings: int,
) -> TaskContext:
    """``ctx`` plus the Yahoo source: every symbol answers ARX's recorded payload except the
    ``unknown`` ones (404) and the ``broken`` ones (500)."""

    def get(url: str) -> bytes:
        calls.append(url)
        symbol = url.split("quoteSummary/")[1].split("?", maxsplit=1)[0]
        if symbol in unknown:
            raise HttpError(404, body=NOT_FOUND)
        if symbol in broken:
            raise HttpError(500, body=b"boom")
        return ARX

    source = YahooAnalyst(http_for(get, RetryPolicy(rejected=refused, tries=1)))
    sources = {**ctx.sources, "yahoo_analyst": source}
    yahoo = YahooSettings(**settings)
    return dataclasses.replace(
        ctx, sources=sources, settings=dataclasses.replace(ctx.settings, yahoo=yahoo)
    )


def yahoo_calls(calls: list[str]) -> list[str]:
    return sorted(c.split("quoteSummary/")[1].split("?")[0] for c in calls if "yahoo" in c)


def world(*symbols: str) -> tuple[StoreWriter, list[str]]:
    writer, calls = StoreWriter(MemoryBackend()), []
    seed(writer, symbols or ("AAPL", "NVDA", "CHWY"))
    return writer, calls


def test_a_name_fmp_refuses_is_asked_of_yahoo_and_its_rows_are_read_back() -> None:
    """The gap: FMP's free plan refuses most names and nothing else served them."""
    writer, calls = world()
    ctx = with_yahoo(context(writer, D1, calls), calls)
    record = run(ctx, {"session": D1})
    assert record.status is RunStatus.COMPLETE
    assert yahoo_calls(calls) == ["CHWY"]  # never AAPL or NVDA, which FMP answers
    got = stored(ctx, D1)
    validate_frame(TABLE, got)
    mine = got[(got["source"] == "yahoo") & (got["instrument_id"] == "EQ:CHWY")]
    assert sorted(set(mine["kind"])) == [
        "coverage",
        "estimates_annual",
        "price_target",
        "recommendation",
    ]
    assert not (got[got["source"] == "yahoo"]["instrument_id"] != "EQ:CHWY").any()
    assert markers(ctx, D1)["EQ:CHWY", "yahoo"] == "OK"
    read = stored_snapshots(
        ctx.reader, None, ("price_target", "estimates_annual", "recommendation"), ["EQ:CHWY"]
    )
    yahoo = read[read["source"] == "yahoo"]
    assert yahoo[yahoo["kind"] == "price_target"].iloc[0]["target_consensus"] == 20.25
    estimates = yahoo[yahoo["kind"] == "estimates_annual"]
    assert set(estimates["period"]) == {"2026-12-31", "2027-12-31"}
    assert set(estimates["currency"]) == {"USD"}
    assert record.items["yahoo:CHWY"] == "OK"
    assert record.stats["licence"]["yahoo"] == "yahoo"


def test_yahoo_calls_are_not_fmp_calls() -> None:
    writer, calls = world()
    first = run(with_yahoo(context(writer, D1, calls), calls), {"session": D1})
    assert len(yahoo_calls(calls)) == 1 and first.stats["yahoo"]["asked"] == 1
    again = with_yahoo(context(writer, D1, calls, hour=15), calls)
    second = run(again, {"session": D1})
    assert second.stats["fmp"]["calls_before"] == len(fmp_calls(calls))  # no Yahoo call in it


def test_a_name_refused_before_and_held_by_fmp_is_asked_without_fmp() -> None:
    writer, calls = world("AAPL", "CHWY")
    run(context(writer, D1, calls), {"session": D1})  # CHWY refused by FMP, no Yahoo yet
    later = D1 + timedelta(days=1)
    calls.clear()
    ctx = with_yahoo(context(writer, later, calls), calls)
    run(ctx, {"session": later})
    assert yahoo_calls(calls) == ["CHWY"]
    assert not any("symbol=CHWY" in c for c in fmp_calls(calls))  # FMP holds it for 90 days


def test_due_names_are_asked_largest_market_cap_first_within_per_night() -> None:
    writer, calls = world("AAPL", "BIG", "MID", "SMALL")
    seed_caps(writer, {"BIG": 9e9, "MID": 5e9, "SMALL": 1e9})
    base = context(writer, D1, calls, refused_names=frozenset({"BIG", "MID", "SMALL"}))
    ctx = with_yahoo(base, calls, per_night=2)
    record = run(ctx, {"session": D1})
    assert record.stats["yahoo"]["names"] == ["BIG", "MID"]
    assert yahoo_calls(calls) == ["BIG", "MID"]
    assert record.stats["yahoo"]["due"] == 3


def test_an_answered_name_is_asked_once_a_window_and_an_unknown_one_after_four() -> None:
    writer, calls = world("AAPL", "BAD", "CHWY")
    refuse = frozenset({"BAD", "CHWY"})
    kwargs = {"unknown": frozenset({"BAD"})}
    first = with_yahoo(context(writer, D1, calls, refused_names=refuse), calls, **kwargs)
    run(first, {"session": D1})
    assert yahoo_calls(calls) == ["BAD", "CHWY"]
    asked: dict[str, list[int]] = {"BAD": [], "CHWY": []}
    for offset in range(1, 4 * 14 + 1):  # FMP's 90-day hold keeps both out of its own rotation
        calls.clear()
        day = D1 + timedelta(days=offset)
        ctx = with_yahoo(context(writer, day, calls, refused_names=refuse), calls, **kwargs)
        run(ctx, {"session": day})
        for symbol in yahoo_calls(calls):
            asked[symbol].append(offset)
    assert len(asked["CHWY"]) in (3, 4) and min(asked["CHWY"]) > 0  # every 14 days, by slot
    assert all(b - a >= 1 for a, b in zip(asked["CHWY"], asked["CHWY"][1:], strict=False))
    assert asked["BAD"] == [4 * 14]  # unknown: held four windows, then asked once


def test_errors_are_fail_soft_and_three_in_a_row_stop_the_night() -> None:
    names = ("AAPL", "N1", "N2", "N3", "N4", "N5")
    writer, calls = world(*names)
    seed_caps(writer, {"N1": 5e9, "N2": 4e9, "N3": 3e9, "N4": 2e9, "N5": 1e9})
    refuse = frozenset(names[1:])
    broken = frozenset(names[1:])
    ctx = with_yahoo(context(writer, D1, calls, refused_names=refuse), calls, broken=broken)
    record = run(ctx, {"session": D1})
    assert record.status is not RunStatus.FAILED
    assert yahoo_calls(calls) == ["N1", "N2", "N3"]
    assert record.items["yahoo:N1"].startswith("FETCH_ERROR")
    assert record.items["yahoo:N4"].startswith("OVER_BUDGET") and record.items[
        "yahoo:N5"
    ].startswith("OVER_BUDGET")
    assert record.stats["yahoo"]["failed"] == 3 and record.stats["yahoo"]["stopped"]
    assert markers(ctx, D1)["EQ:N1", "yahoo"] == "FAILED"
    assert ("EQ:N4", "yahoo") not in markers(ctx, D1)  # no call, no marker
    # a failed name is asked again the next night
    calls.clear()
    later = D1 + timedelta(days=1)
    run(with_yahoo(context(writer, later, calls, refused_names=refuse), calls), {"session": later})
    assert yahoo_calls(calls)[:3] == ["N1", "N2", "N3"]


def test_a_success_resets_the_failure_streak() -> None:
    names = ("AAPL", "N1", "N2", "N3", "N4")
    writer, calls = world(*names)
    seed_caps(writer, {"N1": 4e9, "N2": 3e9, "N3": 2e9, "N4": 1e9})
    refuse = frozenset(names[1:])
    ctx = with_yahoo(
        context(writer, D1, calls, refused_names=refuse),
        calls,
        broken=frozenset({"N1", "N2", "N4"}),
    )
    run(ctx, {"session": D1})
    assert yahoo_calls(calls) == ["N1", "N2", "N3", "N4"]


def test_yahoo_has_its_own_run_budget() -> None:
    writer, calls = world("AAPL", "N1", "N2", "N3")
    refuse = frozenset({"N1", "N2", "N3"})
    ctx = with_yahoo(context(writer, D1, calls, refused_names=refuse), calls, run_budget_s=1)
    record = run(ctx, {"session": D1})
    over = [
        k for k, v in record.items.items() if k.startswith("yahoo:") and v.startswith("OVER_BUDGET")
    ]
    assert over and "run_budget_s" in record.items[over[0]]
    assert record.stats["yahoo"]["stopped"] == "[yahoo] run_budget_s is spent"
    assert any(v == "OK" for k, v in record.items.items() if k.startswith("fmp:"))  # FMP unaffected


def test_a_404_is_not_covered_not_a_failure() -> None:
    writer, calls = world("AAPL", "CHWY")
    ctx = with_yahoo(context(writer, D1, calls), calls, unknown=frozenset({"CHWY"}))
    record = run(ctx, {"session": D1})
    assert record.items["yahoo:CHWY"].startswith("NOT_COVERED")
    assert markers(ctx, D1)["EQ:CHWY", "yahoo"] == "NOT_COVERED"
    got = stored(ctx, D1)
    assert list(got[(got["source"] == "yahoo")]["kind"]) == ["coverage"]
    assert record.stats["yahoo"]["not_covered"] == 1 and record.stats["yahoo"]["failed"] == 0


def test_with_no_fmp_built_yahoo_asks_the_names_fmp_never_answered() -> None:
    writer, calls = world("AAPL", "NVDA")
    ctx = with_yahoo(context(writer, D1, calls), calls)
    ctx = dataclasses.replace(
        ctx, sources={"yahoo_analyst": ctx.sources["yahoo_analyst"]}, unavailable={}
    )
    record = run(ctx, {"session": D1})
    assert record.status is RunStatus.COMPLETE
    assert yahoo_calls(calls) == ["AAPL", "NVDA"]
    assert "skipped" in record.stats["fmp"]


def test_the_limit_param_caps_yahoo_names_too() -> None:
    writer, calls = world("AAPL", "N1", "N2")
    refuse = frozenset({"N1", "N2"})
    run(context(writer, D1, calls, refused_names=refuse), {"session": D1})  # FMP refuses both
    later = D1 + timedelta(days=1)
    calls.clear()
    ctx = with_yahoo(context(writer, later, calls, refused_names=refuse), calls)
    run(ctx, {"session": later, "limit": 1})
    assert len(yahoo_calls(calls)) == 1
