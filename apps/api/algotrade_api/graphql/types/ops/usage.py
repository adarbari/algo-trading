"""``LlmUsage``: what the text model spent (tokens, cost, budget), read from the usage log over a
date range (ADR 0058), for the Admin "LLM usage & cost" page."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.ops import usage
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="The calls of a slice: tokens summed over the calls that reported them "
    "(`callsWithoutTokens` the others; `unknown` set when none did), `spentUsd` what counts "
    "against the budget = `billedUsd` (priced) + `reportedUsd` (the notional seat cost of a "
    "Claude Code login, not a bill) + `boundUsd` (an upper bound charged for an unknown cost)"
)
class UsageTally:
    calls: int
    input_tokens: int
    output_tokens: int
    calls_without_tokens: int
    spent_usd: float
    billed_usd: float
    reported_usd: float
    bound_usd: float
    free_calls: int
    unknown: Unknown | None

    @classmethod
    def of(cls, d: usage.Tally) -> Self:
        return cls(
            calls=d.calls,
            input_tokens=d.input_tokens,
            output_tokens=d.output_tokens,
            calls_without_tokens=d.calls_without_tokens,
            spent_usd=d.spent_usd,
            billed_usd=d.billed_usd,
            reported_usd=d.reported_usd,
            bound_usd=d.bound_usd,
            free_calls=d.free_calls,
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )


@strawberry.type(
    description="A budget cap: `kind` daily or monthly, `limitUsd` null when none is set, "
    "`usedShare` spent / limit (above 1: over the cap), null without a cap"
)
class UsageCap:
    kind: str
    limit_usd: float | None
    used_share: float | None

    @classmethod
    def of(cls, d: usage.Cap) -> Self:
        return cls(kind=d.kind, limit_usd=d.limit_usd, used_share=d.used_share)


@strawberry.type(
    description="`key` today, 7d, 30d or month over `start`..`end`; `cap` null for a window "
    "with no cap of its own (7d, 30d)"
)
class UsageWindow:
    key: str
    start: dt.date
    end: dt.date
    tally: UsageTally
    cap: UsageCap | None

    @classmethod
    def of(cls, d: usage.Window) -> Self:
        return cls(
            key=d.key,
            start=d.start,
            end=d.end,
            tally=UsageTally.of(d.tally),
            cap=UsageCap.of(d.cap) if d.cap is not None else None,
        )


@strawberry.type(
    description="One group of a breakdown (`key` null: stored null; `provider` set for the "
    "model breakdown); `costShare` its share of the 30 days' spend, null when none was spent"
)
class UsageSlice:
    key: str | None
    provider: str | None
    tally: UsageTally
    cost_share: float | None

    @classmethod
    def of(cls, d: usage.Slice) -> Self:
        return cls(
            key=d.key, provider=d.provider, tally=UsageTally.of(d.tally), cost_share=d.cost_share
        )


@strawberry.type(
    description="The 30 days by `by` (model, use_case, user, cost_basis, outcome), most spent first"
)
class UsageBreakdown:
    by: str
    rows: list[UsageSlice]

    @classmethod
    def of(cls, d: usage.Breakdown) -> Self:
        return cls(by=d.by, rows=[UsageSlice.of(r) for r in d.rows])


@strawberry.type(description="One day of the 30-day series (a day with no calls: zero calls)")
class UsageDay:
    day: dt.date
    tally: UsageTally

    @classmethod
    def of(cls, d: usage.DayPoint) -> Self:
        return cls(day=d.day, tally=UsageTally.of(d.tally))


@strawberry.type(
    description="Attempts of the 30 days and how they ended; a rate is null with no attempts"
)
class UsageReliability:
    attempts: int
    ok: int
    fell_back: int
    failed: int
    skipped_budget: int
    fallback_rate: float | None
    failure_rate: float | None

    @classmethod
    def of(cls, d: usage.Reliability) -> Self:
        return cls(
            attempts=d.attempts,
            ok=d.ok,
            fell_back=d.fell_back,
            failed=d.failed,
            skipped_budget=d.skipped_budget,
            fallback_rate=d.fallback_rate,
            failure_rate=d.failure_rate,
        )


@strawberry.type(
    description="One stored attempt; `unknownFields` names the values stored null (tokens a "
    "provider did not report, a cost not known), `unknown` says why"
)
class UsageCall:
    ts: dt.datetime
    provider: str
    model: str
    use_case: str
    user: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float | None
    cost_usd: float | None
    cost_basis: str
    outcome: str
    fell_back_from: str | None
    run_id: str
    unknown_fields: list[str]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: usage.Call) -> Self:
        return cls(
            ts=d.ts,
            provider=d.provider,
            model=d.model,
            use_case=d.use_case,
            user=d.user,
            input_tokens=d.input_tokens,
            output_tokens=d.output_tokens,
            latency_s=d.latency_s,
            cost_usd=d.cost_usd,
            cost_basis=d.cost_basis,
            outcome=d.outcome,
            fell_back_from=d.fell_back_from,
            run_id=d.run_id,
            unknown_fields=list(d.unknown_fields),
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )


@strawberry.type(
    description="`[budget]` of llm.toml (a cap null: not set); `error` the words of an "
    "unreadable file"
)
class UsageBudget:
    daily_usd: float | None
    monthly_usd: float | None
    over: str | None
    reported_call_usd: float | None
    error: str | None

    @classmethod
    def of(cls, d: usage.BudgetInfo) -> Self:
        return cls(
            daily_usd=d.daily_usd,
            monthly_usd=d.monthly_usd,
            over=d.over,
            reported_call_usd=d.reported_call_usd,
            error=d.error,
        )


@strawberry.type(
    description="The text model's usage and cost up to `today` (exchange date): windows with "
    "their caps, 30-day breakdowns, a daily series, reliability and the latest calls. A date "
    "range, not one session (ADR 0058); `recorded` false when the log is empty"
)
class LlmUsage:
    today: dt.date
    recorded: bool
    budget: UsageBudget
    windows: list[UsageWindow]
    breakdowns: list[UsageBreakdown]
    daily: list[UsageDay]
    reliability: UsageReliability
    recent: list[UsageCall]

    @classmethod
    def of(cls, d: usage.LlmUsage) -> Self:
        return cls(
            today=d.today,
            recorded=d.recorded,
            budget=UsageBudget.of(d.budget),
            windows=[UsageWindow.of(w) for w in d.windows],
            breakdowns=[UsageBreakdown.of(b) for b in d.breakdowns],
            daily=[UsageDay.of(p) for p in d.daily],
            reliability=UsageReliability.of(d.reliability),
            recent=[UsageCall.of(c) for c in d.recent],
        )
