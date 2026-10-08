"""``UsageLedger``: what every text-model attempt cost, and whether the budget allows the next
one (ADR 0058). The chain (``chain.py``) asks it before each provider (``admit``) and tells it
each ``Attempt`` (``record``). Every ambiguity fails closed for a provider that spends; a free
provider keeps answering.

Cost per attempt: a ``free`` provider costs 0 (basis ``free``); a ``reported`` one (the Claude
Code login) the notional ``total_cost_usd`` it reported; a ``price`` one tokens x its ``[[price]]``
per million. When the cost is not known (tokens or reported cost missing, or an attempt that
failed: it may still have billed) a spending provider is charged the **upper bound** reserved
for the call (basis ``bound``): prompt characters / 3 x the input price + the provider's
``answer_limit`` x the output price, or ``[budget] reported_call_usd`` for a login. A skipped
attempt cost nothing (``unknown``, null). Never an invented $0.

The budget counters (today's and this month's spend, by exchange calendar date) live in this
process and are authoritative. ``admit`` checks and reserves atomically: it admits a spending
provider only when spent + reserved + this call's bound stays within every cap, and reserves the
bound until ``record`` settles it to the actual cost, so concurrent requests cannot together pass
a cap. The counters are seeded from the store at startup (``seed``, ``store_seed``); until a seed
succeeds (retried with a growing pause) every spending provider is refused. One API process is
assumed: a second would count only its own calls. Each row is handed to the ``sink`` (the
background recorder) after the counters move; the sink cannot fail a call.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from algotrade.config.site.llm import FREE, PRICED, REPORTED, LlmSettings, Rate
from algotrade.core.model.completion import FAILED, SKIPPED_BUDGET, Attempt
from algotrade.core.time.calendar import exchange_date
from algotrade.services.text_model.usage import Seed, UsageSink

log = logging.getLogger(__name__)
UNKNOWN, BOUND = "unknown", "bound"
SPENDING = (PRICED, REPORTED, BOUND)  # cost_basis values that count against the budget
CHARS_PER_TOKEN = 3  # a pessimistic prompt estimate: real text is ~4 characters a token
RETRY_FIRST_S, RETRY_MAX_S = 30.0, 300.0


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
        self._day = exchange_date(clock())
        self._daily = self._monthly = self._reserved = 0.0
        self._seed, self._seeded = seed, seed is None
        self._retry_at, self._pause = clock(), RETRY_FIRST_S
        self._seeding = False
        self._ensure_seeded()

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

    @property
    def seeded(self) -> bool:
        """The counters know what the store holds (else spending providers are refused)."""
        return self._ensure_seeded()

    def spends(self, provider: str) -> bool:
        rate = self._rates.get(provider)
        return rate is None or rate.spends

    def exceeded(self) -> bool:
        """Today's or this month's spend has reached its cap (a cap that is absent never)."""
        with self._lock:
            self._roll()
            b = self._budget
            return (b.daily_usd is not None and self._daily + self._reserved >= b.daily_usd) or (
                b.monthly_usd is not None and self._monthly + self._reserved >= b.monthly_usd
            )

    def refuses(self) -> bool:
        """``over = "refuse"`` and a cap is reached: no provider is asked."""
        return self._budget.over == "refuse" and self.exceeded()

    def admit(self, provider: str, prompt_chars: int) -> float | None:
        """``None``: do not ask ``provider`` (a spending one whose call could pass a cap, or
        while the counters are not seeded; any error here too). Else the USD reserved for the
        call (0 for a free provider), to be handed back to ``record``."""
        if not self.spends(provider):
            return 0.0
        try:
            if not self._ensure_seeded():
                return None
            with self._lock:
                self._roll()
                bound = self._bound(self._rates.get(provider), prompt_chars)
                if self._reached(self._reserved + bound):
                    return None
                self._reserved += bound
                return bound
        except Exception:
            log.exception("text-model ledger failed: %s is not asked", provider)
            return None

    def record(self, attempt: Attempt, reserved: float = 0.0) -> None:
        cost, basis = self._cost(attempt, reserved)
        with self._lock:  # one section: a concurrent admit never sees the room freed but unspent
            self._reserved = max(0.0, self._reserved - reserved)
            self._roll()
            if cost is not None and basis in SPENDING:
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

    def close(self) -> None:
        """Write what is queued (the recorder's shutdown)."""
        close = getattr(self._sink, "close", None)
        if close is not None:
            close()

    # ---------------------------------------------------------------- inside

    def _reached(self, extra: float) -> bool:
        """``spent + extra`` is past a cap (lock held)."""
        b = self._budget
        return (b.daily_usd is not None and self._daily + extra > b.daily_usd) or (
            b.monthly_usd is not None and self._monthly + extra > b.monthly_usd
        )

    def _bound(self, rate: Rate | None, chars: int) -> float:
        if rate is None or rate.basis == REPORTED:
            return self._budget.reported_call_usd
        tokens_in = chars / CHARS_PER_TOKEN
        return (tokens_in * rate.input_per_mtok + rate.answer_limit * rate.output_per_mtok) / 1e6

    def _cost(self, a: Attempt, bound: float) -> tuple[float | None, str]:
        rate = self._rates.get(a.provider)
        if rate is not None and rate.basis == FREE:
            return 0.0, FREE
        if a.outcome == SKIPPED_BUDGET:
            return None, UNKNOWN
        known = None if a.outcome == FAILED else _known(rate, a)
        if known is not None and rate is not None:
            return known, rate.basis
        return (bound, BOUND) if bound > 0 else (None, UNKNOWN)  # unknown cost: the bound

    def _roll(self) -> None:
        """A new exchange date zeroes today's spend, a new month the month's (lock held)."""
        today = exchange_date(self._clock())
        if today == self._day:
            return
        if (today.year, today.month) != (self._day.year, self._day.month):
            self._monthly = 0.0
        self._day, self._daily = today, 0.0

    def _ensure_seeded(self) -> bool:
        """Read the store into the counters once; after a failure, again only after a pause that
        doubles up to ``RETRY_MAX_S``. The read runs outside the lock (admits meanwhile still
        refuse spending providers: unseeded) and only one thread reads at a time."""
        with self._lock:
            if self._seeded:
                return True
            now = self._clock()
            if self._seed is None or self._seeding or now < self._retry_at:
                return False
            self._seeding = True
            today: date = exchange_date(now)
        try:
            by_day = self._seed(today.replace(day=1), today)
        except Exception:
            with self._lock:
                self._seeding = False
                self._retry_at = now + timedelta(seconds=self._pause)
                pause, self._pause = self._pause, min(self._pause * 2, RETRY_MAX_S)
            log.exception(
                "text-model budget: the store could not be read; paid providers are refused "
                "until it can (next try in %g s)", pause,
            )  # fmt: skip
            return False
        with self._lock:
            self._day = today
            self._daily, self._monthly = by_day.get(today, 0.0), sum(by_day.values())
            self._seeded, self._seeding = True, False
        return True


def _known(rate: Rate | None, a: Attempt) -> float | None:
    """The cost the provider reported, or tokens x price; ``None`` when it did not say."""
    if rate is None:
        return None
    if rate.basis == REPORTED:
        return a.reported_cost_usd
    if a.input_tokens is None or a.output_tokens is None:
        return None
    return (a.input_tokens * rate.input_per_mtok + a.output_tokens * rate.output_per_mtok) / 1e6
