"""``FallbackTextModel``: the provider chain of ``llm.toml`` (ADR 0041, amended 2026-10-08).
Asks its members in order and returns the first answer; a member that raises
``ModelUnavailableError`` (off, refused, timed out, busy past its retries, an answer that is not
text) is logged at WARNING and the next is asked. Any other error propagates: a bug is not a
reason to ask another provider. When every member failed the error names each of them with its
own message (never a credential: the members' messages carry none). One deadline covers the
chain: once ``deadline_s`` has passed no further member is started, so retries across
providers never stack unbounded (a request already running keeps its own timeout)."""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.text_model.model import TextModel

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FallbackTextModel:
    """``members``: ``(provider id, model)`` in the order tried."""

    members: Sequence[tuple[str, TextModel]]
    deadline_s: float = 120.0
    clock: Callable[[], float] = field(default=time.monotonic)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for _, model in self.members for name in model.names)

    def complete(self, system: str, user: str) -> Completion:
        started = self.clock()
        failures: list[str] = []
        first_failed: str | None = None
        for position, (provider, model) in enumerate(self.members):
            if position and self.clock() - started > self.deadline_s:
                skipped = [pid for pid, _ in self.members[position:]]
                failures.append(f"not tried, the {self.deadline_s:g} s deadline passed: {skipped}")
                break
            try:
                completion = model.complete(system, user)
            except ModelUnavailableError as exc:
                failures.append(f"{provider}: {exc}")
                first_failed = first_failed or provider
                later = position + 1 < len(self.members)
                log.warning(
                    "text model %s failed%s: %s",
                    provider,
                    ", falling back" if later else "",
                    exc,
                )
                continue
            return replace(
                completion,
                latency_s=self.clock() - started,
                fell_back_from=first_failed,
            )
        raise ModelUnavailableError("no text model could answer: " + "; ".join(failures))
