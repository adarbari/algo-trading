"""``Completion``: what one text-model call returned (ADR 0041, amended 2026-10-08): the text
and where it came from (the model and provider that answered, the provider the chain fell back
from, if any), what it cost (tokens as the provider reported them, ``None`` when it did not:
never ``0``) and how long it took; ``CallTag``: who asks and for what; ``Attempt``: one
provider asked once, what the usage log records (ADR 0058)."""

from dataclasses import dataclass
from datetime import datetime

OK, FAILED, FELL_BACK, SKIPPED_BUDGET = "ok", "failed", "fell_back", "skipped_budget"
OUTCOMES = (OK, FAILED, FELL_BACK, SKIPPED_BUDGET)


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


@dataclass(frozen=True)
class CallTag:
    """Who asks and for what, passed by keyword to ``TextModel.complete``: ``use_case``
    ("screener-draft", "regime-explain") and ``user`` (a registry user id). A provider restricted
    with ``only_users`` answers only a tagged call by one of them; no user is no one."""

    use_case: str
    user: str | None = None


@dataclass(frozen=True)
class Attempt:
    """One provider asked once for one call (ADR 0058): when (UTC), who answered or failed
    (``provider``, ``model``), for whom and what (``use_case``, ``user``), the ``outcome``
    (``OUTCOMES``: ``ok``, ``failed``, ``fell_back`` = answered after an earlier provider
    failed, ``skipped_budget`` = not asked: the budget is spent), how long the attempt took,
    tokens as the provider reported them (``None``: not reported, never ``0``) and the notional
    cost a subscription login reported (``reported_cost_usd``)."""

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
