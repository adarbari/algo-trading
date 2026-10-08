"""``load_llm_usage``: the Admin usage page's read of the usage log over a date range (ADR 0058):
windows with their caps, breakdowns, the daily series, reliability and the recent calls; an empty
store, mixed cost bases (a notional ``reported`` cost never merged into the billed one), no
budget, a broken ``llm.toml`` and tokens a provider did not report (never 0)."""

from datetime import date

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data.usage import LLM_CALLS
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.ops.usage import load_llm_usage
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

TODAY = date(2026, 10, 8)
LLM = ("site", "settings", "llm")


def row(day: date, second: int, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ts": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=14, seconds=second),
        "provider": "claude", "model": "haiku", "use_case": "screener-draft", "user": "abhi",
        "input_tokens": 100, "output_tokens": 50, "latency_s": 1.5, "cost_usd": 0.25,
        "cost_basis": "price", "outcome": "ok", "fell_back_from": None,
    }  # fmt: skip
    return {**base, **over}


def stores(rows: dict[date, list[dict[str, object]]], llm: dict | None = None) -> StoreContext:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day, items in rows.items():
        writer.write_table(LLM_CALLS, day, "r1", stamped(items, day, "r1"))
    docs = {LLM: llm} if llm is not None else {}
    return open_stores(StoreReader(backend), MemoryConfigStore(docs), UserContext("local"))


BUDGET = {"budget": {"daily_usd": 1.0, "monthly_usd": 10.0}}


def mixed() -> StoreContext:
    return stores(
        {
            TODAY: [
                row(TODAY, 0),
                row(
                    TODAY,
                    1,
                    provider="cli",
                    model="sonnet",
                    cost_usd=0.5,
                    cost_basis="reported",
                    input_tokens=None,
                    output_tokens=None,
                    use_case="regime",
                ),
                row(
                    TODAY,
                    2,
                    provider="gemini",
                    model="flash",
                    cost_usd=0.0,
                    cost_basis="free",
                    outcome="fell_back",
                    fell_back_from="claude",
                    user="bea",
                ),
                row(
                    TODAY,
                    3,
                    outcome="skipped_budget",
                    cost_usd=None,
                    cost_basis="unknown",
                    input_tokens=None,
                    output_tokens=None,
                ),
                row(
                    TODAY,
                    4,
                    outcome="failed",
                    cost_usd=0.1,
                    cost_basis="bound",
                    input_tokens=None,
                    output_tokens=None,
                ),
            ],
            date(2026, 10, 1): [row(date(2026, 10, 1), 0, cost_usd=1.0)],
            date(2026, 9, 1): [row(date(2026, 9, 1), 0, cost_usd=9.0)],  # before the 30 days
        },
        BUDGET,
    )


def test_an_empty_store_has_nothing_recorded_and_no_cap_when_none_is_set() -> None:
    usage = load_llm_usage(stores({}), TODAY)
    assert usage.recorded is False and usage.recent == ()
    assert [w.tally.calls for w in usage.windows] == [0, 0, 0, 0]
    assert usage.budget.daily_usd is None and usage.windows[0].cap is not None
    assert usage.windows[0].cap.limit_usd is None and usage.windows[0].cap.used_share is None
    assert len(usage.daily) == 30 and usage.reliability.failure_rate is None


def test_windows_sum_what_counts_against_the_budget_and_show_the_share_of_the_cap() -> None:
    by_key = {w.key: w for w in load_llm_usage(mixed(), TODAY).windows}
    today, week, month, cal = by_key["today"], by_key["7d"], by_key["30d"], by_key["month"]
    assert today.tally.spent_usd == 0.25 + 0.5 + 0.1  # price + reported + bound; free, unknown: 0
    assert today.cap is not None and today.cap.kind == "daily"
    assert today.cap.used_share == 0.85 and today.cap.limit_usd == 1.0
    assert week.tally.calls == 5 and week.cap is None  # 10-01 is outside the 7 days
    assert month.tally.calls == 6 and month.cap is None
    assert cal.tally.calls == 6 and cal.cap is not None and cal.cap.kind == "monthly"
    assert cal.cap.used_share == (0.85 + 1.0) / 10.0  # September 1st is another month


def test_the_notional_seat_cost_is_never_merged_into_the_billed_cost() -> None:
    today = load_llm_usage(mixed(), TODAY).windows[0].tally
    assert (today.billed_usd, today.reported_usd, today.bound_usd) == (0.25, 0.5, 0.1)
    assert today.free_calls == 1


def test_tokens_not_reported_are_counted_apart_never_as_zero() -> None:
    today = load_llm_usage(mixed(), TODAY).windows[0].tally
    assert (today.input_tokens, today.output_tokens) == (200, 100)  # the two that reported
    assert today.calls_without_tokens == 2  # the skipped attempt asked nothing: not counted
    assert today.unknown is None
    silent = load_llm_usage(stores({TODAY: [row(TODAY, 0, input_tokens=None)]}), TODAY)
    unknown = silent.windows[0].tally.unknown
    assert unknown is not None and unknown.code is UnknownCode.NULL
    call = silent.recent[0]
    assert call.input_tokens is None and "input_tokens" in call.unknown_fields
    assert call.unknown is not None


def test_a_call_shows_every_column_newest_first() -> None:
    recent = load_llm_usage(mixed(), TODAY, recent=3).recent
    assert [c.ts.second for c in recent] == [4, 3, 2]
    skipped = recent[1]
    assert skipped.outcome == "skipped_budget" and skipped.cost_usd is None
    assert set(skipped.unknown_fields) == {"input_tokens", "output_tokens", "cost_usd"}
    fell = recent[2]
    assert (fell.fell_back_from, fell.provider, fell.user) == ("claude", "gemini", "bea")
    assert fell.run_id == "r1" and fell.latency_s == 1.5


def test_breakdowns_group_the_30_days_most_spent_first() -> None:
    by = {b.by: b for b in load_llm_usage(mixed(), TODAY).breakdowns}
    models = by["model"].rows
    assert [(s.provider, s.key) for s in models][:2] == [("claude", "haiku"), ("cli", "sonnet")]
    assert by["cost_basis"].rows[0].key == "price"
    assert {s.key for s in by["outcome"].rows} == {"ok", "fell_back", "failed", "skipped_budget"}
    total = sum(s.tally.spent_usd for s in by["user"].rows)
    assert total == 0.85 + 1.0  # 30 days: September 1st is out
    assert abs(sum(s.cost_share or 0 for s in by["user"].rows) - 1.0) < 1e-9


def test_the_daily_series_has_a_point_per_day_with_nothing_recorded_as_no_calls() -> None:
    daily = load_llm_usage(mixed(), TODAY).daily
    assert daily[0].day == date(2026, 9, 9) and daily[-1].day == TODAY
    by_day = {p.day: p.tally for p in daily}
    assert by_day[date(2026, 10, 1)].spent_usd == 1.0 and by_day[date(2026, 10, 3)].calls == 0


def test_reliability_counts_how_attempts_ended() -> None:
    r = load_llm_usage(mixed(), TODAY).reliability
    assert (r.attempts, r.ok, r.fell_back, r.failed, r.skipped_budget) == (6, 3, 1, 1, 1)
    assert r.fallback_rate == 1 / 6 and r.failure_rate == 1 / 6


def test_a_broken_llm_toml_reports_its_error_and_no_caps() -> None:
    usage = load_llm_usage(stores({TODAY: [row(TODAY, 0)]}, {"budget": {"bogus": 1}}), TODAY)
    assert usage.budget.error is not None and usage.budget.daily_usd is None
    assert usage.windows[0].tally.calls == 1  # the spend is still read
