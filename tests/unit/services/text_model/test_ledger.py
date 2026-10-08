"""``UsageLedger``: what an attempt cost (price, reported, free; an unknown cost is charged the
reserved upper bound, never $0), the budget (reserve before asking, settle after: concurrent calls
cannot pass a cap), the roll-over at midnight and month end in New York, and fail-closed for a
provider that spends when the store cannot be read; a free provider always answers."""

import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import Attempt
from algotrade.services.text_model.ledger import UsageLedger

DAY = datetime(2026, 10, 8, 15, tzinfo=UTC)
CHARS = 300  # a prompt: 100 tokens at the assumed 3 characters each
PAID_BOUND = (100 * 1.0 + 8000 * 5.0) / 1e6  # that, x $1, plus the 8,000-token answer limit x $5


def settings(**budget: Any) -> LlmSettings:
    cli = {"id": "cli", "kind": "claude-cli", "command": "/x/claude", "model": "haiku",
           "only_users": ["a"]}  # fmt: skip
    return LlmSettings.from_document(
        {
            "enabled": True,
            "price": [
                {"model": "paid", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
                {"model": "tier", "free": True},
            ],
            "provider": [
                cli,
                {"id": "paid", "base_url": "https://a.io/v1", "model": "paid"},
                {"id": "tier", "base_url": "https://b.io/v1", "model": "tier"},
            ],
            "budget": budget,
        }
    )


class Sink:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.closed = False

    def submit(self, row: Any) -> bool:
        self.rows.append(dict(row))
        return True

    def close(self) -> None:
        self.closed = True


def attempt(provider: str, **over: Any) -> Attempt:
    base: dict[str, Any] = {"at": DAY, "provider": provider, "model": provider, "use_case": "u",
                            "user": "a", "outcome": "ok", "latency_s": 0.2,
                            "input_tokens": 1_000_000, "output_tokens": 100_000}  # fmt: skip
    return Attempt(**(base | over))


def test_cost_is_the_price_or_the_reported_total_and_an_unknown_one_is_its_bound() -> None:
    sink = Sink()
    ledger = UsageLedger(settings(), sink)
    ledger.record(attempt("paid"))  # 1M x $1 + 0.1M x $5
    ledger.record(attempt("cli", reported_cost_usd=0.02, input_tokens=None, output_tokens=None))
    ledger.record(attempt("tier"))
    nothing = {"input_tokens": None, "output_tokens": None}
    ledger.record(attempt("paid", **nothing), PAID_BOUND)  # answered, no usage: the bound
    ledger.record(attempt("cli"), 0.25)  # no reported cost: reported_call_usd
    ledger.record(attempt("paid", outcome="failed"), PAID_BOUND)  # it may have billed
    ledger.record(attempt("paid", outcome="skipped_budget"))  # never asked: nothing
    ledger.record(attempt("paid", **nothing))  # no reservation to charge: unknown, not $0
    got = [(r["cost_usd"], r["cost_basis"]) for r in sink.rows]
    assert got == [(1.5, "price"), (0.02, "reported"), (0.0, "free"), (PAID_BOUND, "bound"),
                   (0.25, "bound"), (PAID_BOUND, "bound"), (None, "unknown"),
                   (None, "unknown")]  # fmt: skip
    assert sink.rows[1]["input_tokens"] is None  # unknown stays None
    assert ledger.spent_today == pytest.approx(1.5 + 0.02 + 2 * PAID_BOUND + 0.25)


def test_a_call_that_could_pass_the_cap_is_not_made_and_settling_frees_the_room() -> None:
    ledger = UsageLedger(settings(daily_usd=0.05))
    first = ledger.admit("paid", CHARS)
    assert first is not None and first == pytest.approx(PAID_BOUND)
    assert ledger.admit("paid", CHARS) is None  # 2 x the bound would pass $0.05
    assert ledger.admit("cli", CHARS) is None  # a login's assumed $0.25 does not fit either
    cheap = {"input_tokens": 1000, "output_tokens": 1000}
    ledger.record(attempt("paid", **cheap), first)  # actual $0.006
    assert ledger.spent_today == pytest.approx(0.006)
    assert ledger.admit("paid", CHARS) is not None  # the reservation was released


def test_free_providers_are_always_admitted_and_over_refuse_stops_everyone_at_the_cap() -> None:
    ledger = UsageLedger(settings(daily_usd=0.01))
    assert ledger.admit("paid", CHARS) is None and ledger.admit("tier", CHARS) == 0.0
    assert not ledger.refuses()  # over = "free" is the default
    strict = UsageLedger(settings(monthly_usd=1.0, over="refuse"))
    strict.record(attempt("paid"))  # $1.50, no reservation
    assert strict.refuses() and strict.exceeded()
    assert not UsageLedger(settings()).refuses()  # no cap: never


def test_concurrent_calls_cannot_pass_the_cap_by_even_one_call() -> None:
    cap = 4.5 * PAID_BOUND  # room for exactly four calls
    ledger = UsageLedger(settings(daily_usd=cap))
    admitted: list[float | None] = []
    start = threading.Barrier(24)

    def ask() -> None:
        start.wait()
        admitted.append(ledger.admit("paid", CHARS))

    threads = [threading.Thread(target=ask) for _ in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([a for a in admitted if a is not None]) == 4


def test_counters_roll_over_at_midnight_in_new_york_and_at_the_month_end() -> None:
    now = [datetime(2026, 10, 31, 20, tzinfo=UTC)]
    ledger = UsageLedger(settings(daily_usd=2.0), clock=lambda: now[0])
    ledger.record(attempt("paid", at=now[0]))  # $1.50
    now[0] = datetime(2026, 11, 1, 3, 59, tzinfo=UTC)  # still Oct 31 in New York
    assert ledger.spent_today == pytest.approx(1.5)
    now[0] = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)  # Nov 1 in New York
    assert ledger.spent_today == 0.0 and ledger.spent_this_month == 0.0


def test_the_counters_are_seeded_from_the_store_at_startup() -> None:
    seen: list[tuple[date, date]] = []

    def seed(start: date, end: date) -> dict[date, float]:
        seen.append((start, end))
        return {date(2026, 10, 2): 3.0, date(2026, 10, 8): 0.4}

    ledger = UsageLedger(settings(daily_usd=1.0, monthly_usd=5.0), seed=seed, clock=lambda: DAY)
    assert seen == [(date(2026, 10, 1), date(2026, 10, 8))] and ledger.seeded
    assert ledger.spent_today == 0.4 and ledger.spent_this_month == pytest.approx(3.4)


def test_an_unreadable_store_refuses_every_paying_provider_until_it_can_be_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now, calls, readable = [DAY], [0], [False]

    def seed(start: date, end: date) -> dict[date, float]:
        calls[0] += 1
        if not readable[0]:
            raise OSError("gone")
        return {date(2026, 10, 8): 0.4}

    ledger = UsageLedger(settings(), seed=seed, clock=lambda: now[0])  # no cap at all
    assert not ledger.seeded and "could not be read" in caplog.text
    assert ledger.admit("paid", CHARS) is None and ledger.admit("cli", CHARS) is None
    assert ledger.admit("tier", CHARS) == 0.0  # a free provider keeps answering
    assert calls[0] == 1  # not retried at once: it backs off
    now[0] += timedelta(seconds=31)
    assert ledger.admit("paid", CHARS) is None and calls[0] == 2  # tried again, still down
    now[0] += timedelta(seconds=45)
    assert ledger.admit("paid", CHARS) is None and calls[0] == 2  # the pause doubled to 60 s
    readable[0] = True
    now[0] += timedelta(seconds=30)
    assert ledger.admit("paid", CHARS) is not None
    assert ledger.spent_today == 0.4


def test_a_ledger_that_breaks_while_admitting_skips_the_provider(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ledger = UsageLedger(settings(daily_usd=1.0))
    ledger._bound = None  # type: ignore[assignment,method-assign]  # breaks the arithmetic
    assert ledger.admit("paid", CHARS) is None and "ledger failed" in caplog.text
    assert ledger.admit("tier", CHARS) == 0.0


def test_close_closes_the_sink() -> None:
    sink = Sink()
    UsageLedger(settings(), sink).close()
    UsageLedger(settings()).close()  # no sink: nothing to do
    assert sink.closed
