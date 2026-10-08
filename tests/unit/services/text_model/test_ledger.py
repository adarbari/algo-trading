"""``UsageLedger``: what an attempt cost (price, reported, free, unknown: never an invented $0),
the budget counters (a spent budget skips the paying providers or refuses), the roll-over at
midnight and month end in New York, the seed from the store, and a sink that cannot fail a call."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import Attempt
from algotrade.services.text_model.ledger import UsageLedger

DAY = datetime(2026, 10, 8, 15, tzinfo=UTC)


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

    def submit(self, row: Any) -> bool:
        self.rows.append(dict(row))
        return True


def attempt(provider: str, **over: Any) -> Attempt:
    base: dict[str, Any] = {"at": DAY, "provider": provider, "model": provider,
            "use_case": "u", "user": "a",
            "outcome": "ok", "latency_s": 0.2, "input_tokens": 1_000_000,
            "output_tokens": 100_000}  # fmt: skip
    return Attempt(**(base | over))


def test_cost_is_the_price_the_reported_total_free_or_unknown_never_zero() -> None:
    sink = Sink()
    ledger = UsageLedger(settings(), sink)
    ledger.record(attempt("paid"))  # 1M x $1 + 0.1M x $5
    ledger.record(attempt("cli", reported_cost_usd=0.02, input_tokens=None, output_tokens=None))
    ledger.record(attempt("tier"))
    ledger.record(attempt("paid", input_tokens=None, output_tokens=None))  # tokens not reported
    ledger.record(attempt("cli"))  # no reported cost
    ledger.record(attempt("paid", outcome="failed"))
    ledger.record(attempt("paid", outcome="skipped_budget"))
    got = [(r["cost_usd"], r["cost_basis"]) for r in sink.rows]
    assert got == [(1.5, "price"), (0.02, "reported"), (0.0, "free"), (None, "unknown"),
                   (None, "unknown"), (None, "unknown"), (None, "unknown")]  # fmt: skip
    assert sink.rows[1]["input_tokens"] is None  # unknown stays None
    assert ledger.spent_today == pytest.approx(1.52)  # free and unknown add nothing


def test_a_spent_daily_budget_skips_the_paying_providers_but_not_the_free_ones() -> None:
    ledger = UsageLedger(settings(daily_usd=1.0))
    assert not ledger.exceeded() and not ledger.skips("paid")
    ledger.record(attempt("paid"))  # $1.50
    assert ledger.exceeded() and ledger.skips("paid") and ledger.skips("cli")
    assert not ledger.skips("tier") and not ledger.refuses()  # over = "free" is the default


def test_over_refuse_refuses_every_call_and_no_cap_never_exceeds() -> None:
    ledger = UsageLedger(settings(monthly_usd=1.0, over="refuse"))
    ledger.record(attempt("paid"))
    assert ledger.refuses() and not ledger.skips("tier")
    unlimited = UsageLedger(settings())
    unlimited.record(attempt("paid"))
    assert not unlimited.exceeded() and not unlimited.refuses()


def test_counters_roll_over_at_midnight_in_new_york_and_at_the_month_end() -> None:
    now = [datetime(2026, 10, 31, 20, tzinfo=UTC)]
    ledger = UsageLedger(settings(daily_usd=1.0), clock=lambda: now[0])
    ledger.record(attempt("paid", at=now[0]))
    assert ledger.exceeded()
    now[0] = datetime(2026, 11, 1, 3, 59, tzinfo=UTC)  # still Oct 31 in New York (DST ends Nov 1)
    assert ledger.exceeded()
    now[0] = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)  # Nov 1 in New York
    assert not ledger.exceeded() and ledger.spent_this_month == 0.0


def test_the_counters_are_seeded_from_the_store_at_startup() -> None:
    seen: list[tuple[date, date]] = []

    def seed(start: date, end: date) -> dict[date, float]:
        seen.append((start, end))
        return {date(2026, 10, 2): 3.0, date(2026, 10, 8): 0.4}

    ledger = UsageLedger(settings(daily_usd=1.0, monthly_usd=5.0), seed=seed, clock=lambda: DAY)
    assert seen == [(date(2026, 10, 1), date(2026, 10, 8))]
    assert ledger.spent_today == 0.4 and ledger.spent_this_month == pytest.approx(3.4)
    ledger.record(attempt("paid"))
    assert ledger.exceeded()


def test_an_unreadable_store_starts_from_zero_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def seed(start: date, end: date) -> dict[date, float]:
        raise OSError("gone")

    ledger = UsageLedger(settings(daily_usd=1.0), seed=seed, clock=lambda: DAY)
    assert ledger.spent_today == 0.0 and "counting from zero" in caplog.text
