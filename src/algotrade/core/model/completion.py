"""``Completion``: what one text-model call returned (ADR 0041, amended 2026-10-08): the text
and where it came from (the model and provider that answered, the provider the chain fell back
from, if any), what it cost (tokens as the provider reported them, ``None`` when it did not:
never ``0``) and how long it took; ``CallTag``: who asks and for what; ``Attempt``: one
provider asked once, what the usage log records (ADR 0058)."""

from dataclasses import dataclass
from datetime import datetime

OK, FAILED, FELL_BACK, SKIPPED_BUDGET = "ok", "failed", "fell_back", "skipped_budget"
REJECTED = "rejected"  # the provider answered but the caller could not use the answer (ADR 0058)
OUTCOMES = (OK, FAILED, FELL_BACK, SKIPPED_BUDGET, REJECTED)
PROVIDER, ANSWER = "provider", "answer"  # ``Attempt.stage``: where a failure happened
MAX_SENTENCE, MAX_ANSWER = 2000, 8000  # characters of a failure's prompt / answer kept


def clip(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters (a cut one ends with an ellipsis)."""
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


@dataclass(frozen=True)
class Completion:
    text: str
    model: str  # the model id that answered: what a cache of its answers is keyed by
    provider: str  # the ``llm.toml`` provider id that answered
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float = 0.0  # the whole call, retries and fall-backs included
    fell_back_from: str | None = None  # the first provider that failed before this one answered
    cost_usd: float | None = (
        None  # a notional cost the provider reported (a subscription's), else None
    )
    # ``input_tokens`` is the regular (uncached) input as the provider reported it; the prompt
    # served from or written to its cache is counted apart, ``None`` when not reported (ADR 0058
    # amended 2026-10-11): total input = input + cache read + cache write.
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    call_id: str | None = None  # one id per ``complete`` call, shared by its attempts


@dataclass(frozen=True)
class CallTag:
    """Who asks and for what, passed by keyword to ``TextModel.complete``: ``use_case``
    ("screener-draft", "regime-explain") and ``user`` (a registry user id). A provider restricted
    with ``only_users`` answers only a tagged call by one of them; no user is no one.
    ``prompt_version`` is the caller's version of its prompt, and ``stage`` where in its flow
    the call is (``first``, ``repair``, ``escalate``): both only recorded (ADR 0058)."""

    use_case: str
    user: str | None = None
    prompt_version: str | None = None
    stage: str = "first"


@dataclass(frozen=True)
class Attempt:
    """One provider asked once for one call (ADR 0058): when (UTC), who answered or failed
    (``provider``, ``model``), for whom and what (``use_case``, ``user``), the ``outcome``
    (``OUTCOMES``: ``ok``, ``failed``, ``fell_back`` = answered after an earlier provider
    failed, ``skipped_budget`` = not asked: the budget is spent), how long the attempt took,
    tokens as the provider reported them (``None``: not reported, never ``0``) and the notional
    cost a subscription login reported (``reported_cost_usd``). A failure carries what is needed
    to diagnose it: ``stage`` (``provider``: the attempt raised, ``error`` its message;
    ``answer``: the provider answered but the caller refused it, a ``rejected`` attempt reported
    after the ``ok`` one, ``error`` the reason), ``sentence`` (the user prompt, clipped),
    ``answer`` (the raw model text, clipped) and ``prompt_chars`` (system + user length; the
    system prompt itself is never kept). Metering (ADR 0058 amended 2026-10-11): the cache
    tokens (``None``: not reported), ``call_id`` (shared by every attempt of one call and its
    ``rejected`` row), the caller's ``prompt_version`` and ``call_stage`` (``CallTag.stage``)."""

    at: datetime
    provider: str
    model: str
    use_case: str
    user: str | None
    outcome: str
    latency_s: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    reported_cost_usd: float | None = None
    fell_back_from: str | None = None
    error: str | None = None
    stage: str | None = None
    sentence: str | None = None
    answer: str | None = None
    prompt_chars: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    call_id: str | None = None
    prompt_version: str | None = None
    call_stage: str = "first"
