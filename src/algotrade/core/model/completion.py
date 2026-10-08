"""``Completion``: what one text-model call returned (ADR 0041, amended 2026-10-08): the text
and where it came from (the model and provider that answered, the provider the chain fell back
from, if any), what it cost (tokens as the provider reported them, ``None`` when it did not:
never ``0``) and how long it took."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Completion:
    text: str
    model: str  # the model id that answered: what a cache of its answers is keyed by
    provider: str  # the ``llm.toml`` provider id that answered
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float = 0.0  # the whole call, retries and fall-backs included
    fell_back_from: str | None = None  # the first provider that failed before this one answered
