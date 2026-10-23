"""``analyst-backfill`` (ADR 0080 amendment 2026-10-23b): Yahoo's data of the whole stock
population, one resumable batch a run, quiet until the nightly is complete, stopped by a 429; and
the nightly's Yahoo step reading its items (every name Yahoo answered, at its own cadence)."""

import dataclasses
from datetime import timedelta

from algotrade.config.site.vendors.yahoo import YahooSettings
from algotrade.core.time.calendar import last_closed_session
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus, start_run
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.analyst import backfill
from algotrade_ingestion.tasks.analyst.snapshot import run as nightly_run
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.yahoo.analyst import YahooAnalyst
from algotrade_sources.vendors.yahoo.client import refused
from tests.apps.ingestion.tasks.analyst.test_snapshot import (
    D1,
    REFERENCE_DAY,
    context,
    seed_caps,
)
from tests.apps.ingestion.tasks.analyst.test_snapshot_yahoo import ARX, NOT_FOUND, yahoo_calls
from tests.helpers.ingest_fakes import http_for
from tests.helpers.stored_frames import stamped

AFTER_CLOSE = 22  # UTC hour: the session of D1 has closed


def seed_types(writer: StoreWriter, types: dict[str, str], sp500: tuple[str, ...] = ()) -> None:
    """A reference snapshot of ``symbol -> security_type``; ``sp500`` members are in the index."""
    rows = [
        {
            "instrument_id": f"EQ:{s}",
            "symbol": s,
            "asset_class": "EQ",
            "security_type": t,
            "multiplier": 1.0,
            "status": "ACTIVE",
            "in_sp500": s in sp500,
        }
        for s, t in types.items()
    ]
    writer.write_table(
        "instruments/reference", REFERENCE_DAY, "ref", stamped(rows, REFERENCE_DAY, "ref")
    )


def finish_nightly(writer: StoreWriter, ctx: TaskContext) -> None:
    """The nightly workflow of D1 is complete: a COMPLETE ``nightly`` run record."""
    record = start_run(backfill.NIGHTLY, D1, ctx.clock())
    writer.save_run(record.finish(ctx.clock()))


def yahoo_ctx(
    base: TaskContext,
    calls: list[str],
    unknown: frozenset[str] = frozenset(),
    limited: frozenset[str] = frozenset(),
    broken: frozenset[str] = frozenset(),
    **settings: float,
) -> TaskContext:
    """``base`` plus Yahoo answering ARX's payload (404 for ``unknown``, 429 for ``limited``,
    500 for ``broken``) and settings with no pacing wait unless given."""

    def get(url: str) -> bytes:
        calls.append(url)
        symbol = url.split("quoteSummary/")[1].split("?", maxsplit=1)[0]
        if symbol in unknown:
            raise HttpError(404, body=NOT_FOUND)
        if symbol in limited:
            raise HttpError(429)
        if symbol in broken:
            raise HttpError(500, body=b"boom")
        return ARX

    source = YahooAnalyst(http_for(get, RetryPolicy(rejected=refused, tries=1)))
    sources = {**base.sources, "yahoo_analyst": source}
    yahoo = YahooSettings(**{"backfill_min_interval_s": 0.0, **settings})  # type: ignore[arg-type]
    return dataclasses.replace(
        base, sources=sources, settings=dataclasses.replace(base.settings, yahoo=yahoo)
    )


def world(types: dict[str, str], sp500: tuple[str, ...] = ()) -> tuple[StoreWriter, list[str]]:
    writer = StoreWriter(MemoryBackend())
    seed_types(writer, types, sp500)
    return writer, []


def test_the_population_is_the_operating_companies_whether_or_not_fmp_or_scope_has_them() -> None:
    types = {"AAPL": "COMMON_STOCK", "SMALL": "COMMON_STOCK", "ADRX": "ADR", "SPY": "ETF"}
    types["CEFX"] = "CEF"
    writer, calls = world(types, sp500=("AAPL",))
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls)
    finish_nightly(writer, ctx)
    record = backfill.run(ctx, {"session": D1})
    assert record.status is RunStatus.COMPLETE
    assert yahoo_calls(calls) == ["AAPL", "ADRX", "SMALL"]  # no ETF, no closed-end fund
    assert record.stats["population"] == 3 and record.stats["due_remaining"] == 0
    assert record.stats["licence"] == {"yahoo": "yahoo"}
    assert record.items["yahoo:SMALL"].startswith("OK: fp=")


def test_a_name_yahoo_refused_is_held_and_one_it_answered_is_not_asked_again() -> None:
    writer, calls = world({"AAA": "COMMON_STOCK", "BAD": "COMMON_STOCK", "CCC": "COMMON_STOCK"})
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls, unknown=frozenset({"BAD"}))
    finish_nightly(writer, ctx)
    first = backfill.run(ctx, {"session": D1})
    assert first.items["yahoo:BAD"].startswith("NOT_COVERED")
    assert first.stats["not_covered"] == 1 and first.stats["progress"] == 3
    calls.clear()
    again = backfill.run(ctx, {"session": D1})
    assert calls == [] and again.stats["due"] == 0 and again.stats["due_remaining"] == 0


def test_a_batch_takes_the_largest_caps_and_the_next_run_resumes() -> None:
    names = ("SML", "BIG", "MID", "TNY")
    writer, calls = world(dict.fromkeys(names, "COMMON_STOCK"))
    seed_caps(writer, {"BIG": 9e9, "MID": 5e9, "SML": 1e9})  # TNY has no cap: last
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls, backfill_batch=3)
    finish_nightly(writer, ctx)
    first = backfill.run(ctx, {"session": D1})
    assert yahoo_calls(calls) == ["BIG", "MID", "SML"]
    assert first.stats["due"] == 4 and first.stats["due_remaining"] == 1
    calls.clear()
    second = backfill.run(ctx, {"session": D1})
    assert yahoo_calls(calls) == ["TNY"]  # resumed: the answered three are not due
    assert second.stats["due_remaining"] == 0
    calls.clear()
    limited = backfill.run(ctx, {"session": D1, "limit": 1})
    assert calls == [] and limited.stats["progress"] == 0  # all answered: nothing left


def test_the_limit_param_caps_the_batch_below_the_setting() -> None:
    writer, calls = world(dict.fromkeys(("AAA", "BBB", "CCC"), "COMMON_STOCK"))
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls)
    finish_nightly(writer, ctx)
    record = backfill.run(ctx, {"session": D1, "limit": 2})
    assert len(yahoo_calls(calls)) == 2 and record.stats["due_remaining"] == 1


def test_it_does_nothing_quietly_until_the_nightly_of_the_last_closed_session_is_complete() -> None:
    writer, calls = world({"AAA": "COMMON_STOCK"})
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls)
    assert last_closed_session(ctx.clock(), timedelta(0)) == D1
    record = backfill.run(ctx, {"session": D1})  # no nightly record at all
    assert calls == [] and record.status is RunStatus.COMPLETE  # exit 0, not an error
    assert "is not complete" in record.stats["waiting"] and record.stats["due_remaining"] is None
    assert ctx.reader.runs(backfill.TASK) == []  # not saved: a loop would bury the real runs
    earlier = start_run(backfill.NIGHTLY, D1 - timedelta(days=1), ctx.clock())
    writer.save_run(earlier.finish(ctx.clock()))  # another session's nightly does not count
    assert backfill.run(ctx, {"session": D1}).stats["waiting"]
    running = start_run(backfill.NIGHTLY, D1, ctx.clock())
    writer.save_run(running)  # still running
    assert backfill.run(ctx, {"session": D1}).stats["waiting"] and calls == []
    finish_nightly(writer, ctx)
    assert "waiting" not in backfill.run(ctx, {"session": D1}).stats and calls != []


def test_the_first_429_stops_the_batch_and_the_names_left_stay_due() -> None:
    names = ("N1", "N2", "N3", "N4")
    writer, calls = world(dict.fromkeys(names, "COMMON_STOCK"))
    seed_caps(writer, {"N1": 4e9, "N2": 3e9, "N3": 2e9, "N4": 1e9})
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls, limited=frozenset({"N2"}))
    finish_nightly(writer, ctx)
    record = backfill.run(ctx, {"session": D1})
    assert yahoo_calls(calls) == ["N1", "N2"]  # one 429, not three
    assert record.stats["rate_limited"] is True and "429" in record.stats["stopped"]
    assert record.stats["progress"] == 1 and record.stats["due_remaining"] == 3
    assert record.items["yahoo:N2"].startswith("FETCH_ERROR")
    assert "yahoo:N3" not in record.items and record.status is not RunStatus.FAILED
    calls.clear()  # a later batch asks N2 again (a failed name is due), then the rest
    clear = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls)
    assert backfill.run(clear, {"session": D1}).stats["due_remaining"] == 0


def test_three_failures_in_a_row_stop_it_and_a_success_resets_the_streak() -> None:
    names = ("N1", "N2", "N3", "N4", "N5")
    writer, calls = world(dict.fromkeys(names, "COMMON_STOCK"))
    seed_caps(writer, {n: 9e9 - i for i, n in enumerate(names)})
    broken = frozenset({"N1", "N2", "N4", "N5"})
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls, broken=broken)
    finish_nightly(writer, ctx)
    record = backfill.run(ctx, {"session": D1})
    assert yahoo_calls(calls) == list(names)  # N3 answered between the failures
    assert record.stats["failed"] == 4 and record.stats["stopped"] is None
    calls.clear()
    worse = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls, broken=broken)
    again = backfill.run(worse, {"session": D1})
    assert yahoo_calls(calls) == ["N1", "N2", "N4"]  # N3 is answered; three failures stop it
    assert again.stats["stopped"] and not again.stats["rate_limited"]


def test_the_yahoo_source_is_built_with_the_backfill_pacing() -> None:
    from algotrade.config.site.settings import SourcesSettings  # noqa: PLC0415
    from algotrade_ingestion.cli.commands import task_sources  # noqa: PLC0415

    site = SourcesSettings.from_document({"yahoo": {"min_interval_s": 1.0}})
    spec = TASKS["analyst-backfill"]
    fast = backfill.paced(site)
    assert fast.vendor("yahoo").min_interval_s == 0.3  # the backfill's floor, below the nightly's
    assert fast.vendor("yahoo").max_interval_s == 3.0  # doubles up to 3 s on errors
    assert (fast.http_backoff_factor, fast.http_speedup_after) == (2.0, 50)  # halves after 50
    assert site.vendor("yahoo").min_interval_s == 1.0  # the nightly keeps its floor
    assert site.http_backoff_factor != 2.0  # other vendors' rules are untouched
    built = task_sources(spec, site, {})
    pacing = built.limiters["yahoo"].pacing
    assert (
        pacing.min_interval_s == 0.3 and pacing.ceiling == 3.0 and "yahoo_analyst" in built.sources
    )


def test_the_nightly_reads_the_backfills_items_and_asks_every_answered_name_by_cadence() -> None:
    """History spans both task names: a backfilled name is not asked again before its window; a
    name FMP does not answer comes due after refresh_days, one FMP answers (AAPL) after
    standby_days; and a name outside the scope list (SMALL) is asked: the candidates widened."""
    types = {"AAPL": "COMMON_STOCK", "SMALL": "COMMON_STOCK"}
    writer, calls = world(types, sp500=("AAPL",))
    ctx = yahoo_ctx(context(writer, D1, calls, hour=AFTER_CLOSE), calls)
    finish_nightly(writer, ctx)
    backfill.run(ctx, {"session": D1})
    assert yahoo_calls(calls) == ["AAPL", "SMALL"]
    asked: dict[str, list[int]] = {"AAPL": [], "SMALL": []}
    for offset in range(1, 47):
        calls.clear()
        day = D1 + timedelta(days=offset)
        night = yahoo_ctx(context(writer, day, calls), calls)
        record = nightly_run(night, {"session": day})
        assert record.status is not RunStatus.FAILED
        for symbol in yahoo_calls(calls):
            asked[symbol].append(offset)
    assert asked["SMALL"] and 1 <= min(asked["SMALL"]) <= 14  # refresh_days, a slot of the window
    assert len(asked["SMALL"]) >= 3  # 14-day cadence across 46 days
    assert asked["AAPL"] and min(asked["AAPL"]) > 14  # FMP answers it: only the standby asks
    assert len(asked["AAPL"]) == 1


def test_the_task_is_registered_with_yahoo_as_its_only_source() -> None:
    spec = TASKS["analyst-backfill"]
    assert spec.sources == ("yahoo_analyst",) and spec.tables == ("analyst/estimate_snapshots",)
    assert spec.skip is None  # in no workflow
