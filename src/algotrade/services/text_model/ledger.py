"""``UsageLedger``: what every text-model attempt cost, and whether the budget allows the next
one (ADR 0057). The chain (``chain.py``) tells it each ``Attempt`` and asks it before asking a
provider.

Cost per attempt: a ``free`` provider costs 0 (basis ``free``); a ``reported`` one (the Claude
Code login) the notional ``total_cost_usd`` it reported (basis ``reported``); a ``price`` one
tokens x its ``[[price]]`` per million (basis ``price``); a call whose tokens or reported cost
are missing, a failed attempt of a paid provider and a skipped one have ``cost_usd`` null and
basis ``unknown``: never ``$0``, and not counted against the budget either (the Admin usage
page counts them). The budget counters (today's and this month's spend, by exchange calendar
date) live in this process and are authoritative: seeded once at startup from the store (``seed``,
``store_seed``), then kept by ``record``. One API process is assumed: a second would count only
its own calls. Each row is handed to the ``sink`` (the background recorder) after the counters
move; neither the sink nor the seed can fail a call.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime

from algotrade.config.site.llm import FREE, PRICED, REPORTED, LlmSettings, Rate
from algotrade.core.model.completion import FAILED, SKIPPED_BUDGET, Attempt
from algotrade.core.time.calendar import exchange_date
from algotrade.services.text_model.usage import Seed, UsageSink

log = logging.getLogger(__name__)
UNKNOWN = "unknown"


class UsageLedger:
    def __init__(
        self,
        settings: LlmSettings,
        sink: UsageSink | None = None,
        seed: Seed | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._rates = {p.id: settings.rate(p) for p in settings.providers}
        self._budget, self._sink, self._clock = settings.budget, sink, clock
        self._lock = threading.Lock()
        today = exchange_date(clock())
        self._day, self._daily, self._monthly = today, 0.0, 0.0
        if seed is not None:
            self._seed(seed, today)

    # ---------------------------------------------------------------- what the chain asks

    @property
    def spent_today(self) -> float:
        with self._lock:
            self._roll()
            return self._daily

    @property
    def spent_this_month(self) -> float:
        with self._lock:
            self._roll()
            return self._monthly

    def exceeded(self) -> bool:
        """Today's or this month's spend has reached its cap (a cap that is absent never)."""
        with self._lock:
            self._roll()
            b = self._budget
            return (b.daily_usd is not None and self._daily >= b.daily_usd) or (
                b.monthly_usd is not None and self._monthly >= b.monthly_usd
            )

    def refuses(self) -> bool:
        return self._budget.over == "refuse" and self.exceeded()

    def skips(self, provider: str) -> bool:
        rate = self._rates.get(provider)
        return self._budget.over == "free" and (rate is None or rate.spends) and self.exceeded()

    def record(self, attempt: Attempt) -> None:
        cost, basis = self._cost(attempt)
        with self._lock:
            self._roll()
            if cost is not None and basis in (PRICED, REPORTED):
                self._daily += cost
                self._monthly += cost
        if self._sink is not None:
            self._sink.submit(
                {
                    "ts": attempt.at, "provider": attempt.provider, "model": attempt.model,
                    "use_case": attempt.use_case, "user": attempt.user,
                    "input_tokens": attempt.input_tokens, "output_tokens": attempt.output_tokens,
                    "latency_s": attempt.latency_s, "cost_usd": cost, "cost_basis": basis,
                    "outcome": attempt.outcome, "fell_back_from": attempt.fell_back_from,
                }
            )  # fmt: skip

    # ---------------------------------------------------------------- inside

    def _cost(self, a: Attempt) -> tuple[float | None, str]:
        rate: Rate | None = self._rates.get(a.provider)
        if rate is None:
            return None, UNKNOWN
        if rate.basis == FREE:
            return 0.0, FREE
        if a.outcome in (FAILED, SKIPPED_BUDGET):
            return None, UNKNOWN
        cost = a.reported_cost_usd if rate.basis == REPORTED else _priced(rate, a)
        return (cost, rate.basis) if cost is not None else (None, UNKNOWN)

    def _roll(self) -> None:
        """A new exchange date zeroes today's spend, a new month the month's (lock held)."""
        today = exchange_date(self._clock())
        if today == self._day:
            return
        if (today.year, today.month) != (self._day.year, self._day.month):
            self._monthly = 0.0
        self._day, self._daily = today, 0.0

    def _seed(self, seed: Seed, today: date) -> None:
        try:
            by_day = seed(today.replace(day=1), today)
        except Exception:
            log.exception("text-model budget: the store could not be read, counting from zero")
            return
        self._daily = by_day.get(today, 0.0)
        self._monthly = sum(by_day.values())


def _priced(rate: Rate, a: Attempt) -> float | None:
    """Tokens x the model's price per million; ``None`` when the provider did not report them."""
    if a.input_tokens is None or a.output_tokens is None:
        return None
    return (a.input_tokens * rate.input_per_mtok + a.output_tokens * rate.output_per_mtok) / 1e6
