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
models that user may be answered by, so a cache never serves them another user's answer.
An optional ``CallLedger`` (ADR 0057) sees every attempt, the failed ones too, and may refuse
a call or skip the members that spend when the budget is used up; it never raises into the
chain (a bug in recording must not stop an answer)."""

import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from algotrade.core.model.completion import (
    FAILED,
    FELL_BACK,
    OK,
    SKIPPED_BUDGET,
    Attempt,
    CallTag,
    Completion,
)
from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.text_model.model import TextModel

log = logging.getLogger(__name__)
_REFUSED = re.compile(r"HTTP 4(?!08|29)\d\d")  # a client error the adapter does not retry


class CallLedger(Protocol):
    """What the chain tells and asks the usage ledger (``ledger.py``)."""

    def refuses(self) -> bool:
        """The budget is spent and ``over = "refuse"``: no provider is asked."""
        ...

    def spends(self, provider: str) -> bool:
        """``provider`` costs money (priced or reported), so it is asked only when admitted."""
        ...

    def admit(self, provider: str, prompt_chars: int) -> float | None:
        """``None``: do not ask ``provider``; else the USD reserved for the call."""
        ...

    def record(self, attempt: Attempt, reserved: float = 0.0) -> None:
        """One attempt happened; settles its ``reserved`` USD to the actual cost."""
        ...


@dataclass(frozen=True)
class FallbackTextModel:
    """``members``: ``(provider id, model)`` in the order tried; ``only_users``: provider id ->
    the users it answers (a provider not in it answers everyone)."""

    members: Sequence[tuple[str, TextModel]]
    deadline_s: float = 120.0  # ``LlmSettings`` guarantees it exceeds every non-last member
    clock: Callable[[], float] = field(default=time.monotonic)
    only_users: Mapping[str, frozenset[str]] = field(default_factory=dict)
    ledger: CallLedger | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

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
        if self.ledger is not None and self._refuses():
            for provider, model in members:
                self._note(tag, provider, model, SKIPPED_BUDGET)
            raise ModelUnavailableError("the text-model budget is spent (llm.toml [budget])")
        for position, (provider, model) in enumerate(members):
            if position and self.clock() - started > self.deadline_s:
                skipped = [pid for pid, _ in members[position:]]
                failures.append(f"not tried, the {self.deadline_s:g} s deadline passed: {skipped}")
                break
            reserved = self._admit(provider, len(system) + len(user))
            if reserved is None:
                self._note(tag, provider, model, SKIPPED_BUDGET)
                failures.append(f"{provider}: skipped, the budget is spent")
                continue
            began = self.clock()
            try:
                completion = model.complete(system, user, tag=tag)
            except ModelUnavailableError as exc:
                self._note(tag, provider, model, FAILED, reserved, took=self.clock() - began)
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
            except Exception:  # a bug propagates, but what it may have cost is settled first
                self._note(tag, provider, model, FAILED, reserved, took=self.clock() - began)
                raise
            self._note(
                tag, provider, model, FELL_BACK if first_failed else OK, reserved,
                took=self.clock() - began, answer=completion, fell_back_from=first_failed,
            )  # fmt: skip
            return replace(
                completion,
                latency_s=self.clock() - started,
                fell_back_from=first_failed,
            )
        raise ModelUnavailableError("no text model could answer: " + "; ".join(failures))

    def close(self) -> None:
        """Shutdown: the ledger writes what it still holds."""
        close = getattr(self.ledger, "close", None)
        if close is not None:
            close()

    # ---------------------------------------------------------------- the usage ledger

    def _refuses(self) -> bool:
        """``over = "refuse"`` and spent. A ledger that breaks does not refuse here: ``_admit``
        decides member by member, and fails closed for the ones that spend."""
        try:
            return self.ledger.refuses() if self.ledger is not None else False
        except Exception:
            log.exception("the text-model ledger failed (refuses)")
            return False

    def _admit(self, provider: str, chars: int) -> float | None:
        """The USD reserved for asking ``provider`` (0: no ledger or a free provider), ``None``
        to skip it. A ledger that raises skips every provider that spends (or might: when it
        cannot even say, all) and lets a free one answer."""
        if self.ledger is None:
            return 0.0
        try:
            return self.ledger.admit(provider, chars)
        except Exception:
            log.exception("the text-model ledger failed: %s is skipped if it spends", provider)
            try:
                return None if self.ledger.spends(provider) else 0.0
            except Exception:
                return None

    def _note(
        self,
        tag: CallTag | None,
        provider: str,
        model: TextModel,
        outcome: str,
        reserved: float = 0.0,
        took: float = 0.0,
        answer: Completion | None = None,
        fell_back_from: str | None = None,
    ) -> None:
        if self.ledger is None:
            return
        try:
            self.ledger.record(
                Attempt(
                    at=self.now(),
                    provider=provider,
                    model=answer.model if answer is not None else (model.names or ("",))[0],
                    use_case=tag.use_case if tag is not None else "untagged",
                    user=tag.user if tag is not None else None,
                    outcome=outcome,
                    latency_s=took,
                    input_tokens=answer.input_tokens if answer is not None else None,
                    output_tokens=answer.output_tokens if answer is not None else None,
                    reported_cost_usd=answer.cost_usd if answer is not None else None,
                    fell_back_from=fell_back_from,
                ),
                reserved,
            )
        except Exception:
            log.exception("the text-model ledger could not record a call; the call goes on")
