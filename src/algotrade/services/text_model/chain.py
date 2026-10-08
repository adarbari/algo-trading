"""``FallbackTextModel``: the provider chain of ``llm.toml`` (ADR 0041, amended 2026-10-08).
Asks its members in order and returns the first answer; a member that raises
``ModelUnavailableError`` (off, refused, timed out, busy past its retries, an answer that is not
text) is logged at WARNING (ERROR for a client error such as a refused key) and the next is
asked. Any other error propagates: a bug is not a reason to ask another provider. When every
member failed the error names each of them with its own message (never a credential: the
members' messages carry none). One deadline covers the chain: once ``deadline_s`` has passed no
further member is started, so retries across providers never stack unbounded (a request already
running keeps its own timeout; ``LlmSettings`` keeps the deadline above every earlier member's
worst case, so the fallback always gets its turn). A member restricted to some users
(``only_users``, ADR 0041 amended 2026-10-08, the Claude Code login) is skipped, without being
asked, for any other user and for a call with no user; ``names_for(user)`` lists only the
models that user may be answered by, so a cache never serves them another user's answer."""

import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.text_model.model import TextModel

log = logging.getLogger(__name__)
_REFUSED = re.compile(r"HTTP 4(?!08|29)\d\d")  # a client error the adapter does not retry


@dataclass(frozen=True)
class FallbackTextModel:
    """``members``: ``(provider id, model)`` in the order tried; ``only_users``: provider id ->
    the users it answers (a provider not in it answers everyone)."""

    members: Sequence[tuple[str, TextModel]]
    deadline_s: float = 120.0  # ``LlmSettings`` guarantees it exceeds every non-last member
    clock: Callable[[], float] = field(default=time.monotonic)
    only_users: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for _, model in self.members for name in model.names)

    def allowed(self, provider: str, user: str | None) -> bool:
        users = self.only_users.get(provider)
        return users is None or (user is not None and user in users)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return tuple(
            name
            for provider, model in self.members
            if self.allowed(provider, user)
            for name in model.names
        )

    def complete(self, system: str, user: str, *, tag: CallTag | None = None) -> Completion:
        started = self.clock()
        asking = tag.user if tag is not None else None
        failures: list[str] = []
        first_failed: str | None = None
        members = [(p, m) for p, m in self.members if self.allowed(p, asking)]
        if not members:
            raise ModelUnavailableError("no text model may answer this user")
        for position, (provider, model) in enumerate(members):
            if position and self.clock() - started > self.deadline_s:
                skipped = [pid for pid, _ in members[position:]]
                failures.append(f"not tried, the {self.deadline_s:g} s deadline passed: {skipped}")
                break
            try:
                completion = model.complete(system, user, tag=tag)
            except ModelUnavailableError as exc:
                failures.append(f"{provider}: {exc}")
                first_failed = first_failed or provider
                later = position + 1 < len(members)
                # a refusal that retrying cannot fix (bad key, unknown model) needs the owner
                refused = _REFUSED.search(str(exc)) is not None
                log.log(
                    logging.ERROR if refused else logging.WARNING,
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
