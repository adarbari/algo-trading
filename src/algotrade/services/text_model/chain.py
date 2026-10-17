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
An optional ``CallLedger`` (ADR 0058) sees every attempt, the failed ones too, and may refuse
a call or skip the members that spend when the budget is used up; it never raises into the
chain (a bug in recording must not stop an answer). A failed attempt is recorded with its
message, the prompt and its length; ``reject`` records, as a second row, an answer the caller
could not use (outcome ``rejected``, no cost: the ``ok`` row already carries it).
The order of the members is the tier order: cheap first, strong last. With the caller's
``accept`` (ADR 0041, amended 2026-10-11) an answer it refuses (``ModelUnavailableError``,
usually ``InvalidAnswerError``) is recorded as ``rejected``, the same member is asked once more
(``repair``: the question, the refused answer and the exact error), and if that is refused too
the next member is asked (``escalate``): at most two calls per member, none started after
``deadline_s``. ``schema`` is passed to the members, which send it only when configured to.
A member that raises ``QuotaExhaustedError`` (ADR 0041, amended 2026-10-17: its quota is used
up for the day) cools off: until ``cool_off_s`` has passed on the chain's clock it is skipped
without being asked, each skip recorded as a ``cooling_off`` attempt (not a failure) (the first
one logged once at WARNING). The state is process-local and thread-safe."""

import logging
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from algotrade.core.model.completion import (
    ANSWER,
    COOLING_OFF,
    FAILED,
    FELL_BACK,
    MAX_ANSWER,
    MAX_SENTENCE,
    OK,
    PROVIDER,
    REJECTED,
    SKIPPED_BUDGET,
    Attempt,
    CallTag,
    Completion,
    clip,
)
from algotrade.core.model.errors import ModelUnavailableError, QuotaExhaustedError
from algotrade.services.text_model.model import TextModel

log = logging.getLogger(__name__)
_REFUSED = re.compile(r"HTTP 4(?!08|29)\d\d")  # a client error the adapter does not retry
REPAIR, ESCALATE = "repair", "escalate"  # ``CallTag.stage`` of a retry and of the next provider


def _stage(tag: CallTag | None) -> str:
    return tag.stage if tag is not None else "first"


def _refusal(accept: Callable[[str], None] | None, text: str) -> str | None:
    """Why the caller refuses ``text`` (its ``accept`` raised ``ModelUnavailableError``), else
    ``None``. Any other error in ``accept`` is a bug and propagates."""
    if accept is None:
        return None
    try:
        accept(text)
    except ModelUnavailableError as exc:
        return str(exc)
    return None


def repair_prompt(user: str, answer: str, error: str) -> str:
    """The user text of a repair call: the original question, the refused answer and the exact
    error, asking for the corrected JSON only."""
    return (
        f"{user}\n\nYour previous answer:\n{clip(answer, MAX_ANSWER)}\n\n"
        f"Your answer was rejected: {error}. Return only the corrected JSON object."
    )


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


@dataclass
class _Call:
    """What one ``complete`` carries across its members: the question, the clock, its id shared
    by every attempt and rejection, the causes so far, the first member that failed or was
    refused (``fell_back_from``), whether a refused answer makes the next member an escalation,
    and whether a member follows (for the log)."""

    system: str
    user: str
    tag: CallTag | None
    schema: Mapping[str, Any] | None
    started: float
    call_id: str
    failures: list[str] = field(default_factory=list)
    first_failed: str | None = None
    escalating: bool = False
    later: bool = False


@dataclass(frozen=True)
class FallbackTextModel:
    """``members``: ``(provider id, model)`` in the order tried; ``only_users``: provider id ->
    the users it answers (a provider not in it answers everyone)."""

    members: Sequence[tuple[str, TextModel]]
    deadline_s: float = 120.0  # ``LlmSettings`` guarantees it exceeds every non-last member
    clock: Callable[[], float] = field(default=time.monotonic)
    only_users: Mapping[str, frozenset[str]] = field(default_factory=dict)
    ledger: CallLedger | None = None
    worst_s: Mapping[str, float] = field(default_factory=dict)  # provider id -> worst_case_s
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    cooling: dict[str, float] = field(default_factory=dict)  # provider id -> clock() it is back
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def cooling_for(self, provider: str) -> float | None:
        """Seconds ``provider`` stays cooled off, else ``None`` (an expired entry is dropped)."""
        with self._lock:
            until = self.cooling.get(provider)
            if until is None:
                return None
            left = until - self.clock()
            if left <= 0:
                del self.cooling[provider]
                return None
            return left

    def _cool(self, provider: str, seconds: float) -> bool:
        """Start (or extend) the cool-off; ``True`` when it was not cooling already."""
        with self._lock:
            fresh = provider not in self.cooling
            self.cooling[provider] = self.clock() + seconds
            return fresh

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

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: Mapping[str, Any] | None = None,
        accept: Callable[[str], None] | None = None,
    ) -> Completion:
        call = _Call(system, user, tag, schema, self.clock(), uuid.uuid4().hex)
        asking = tag.user if tag is not None else None
        members = [(p, m) for p, m in self.members if self.allowed(p, asking)]
        if not members:
            raise ModelUnavailableError("no text model may answer this user")
        if self.ledger is not None and self._refuses():
            for provider, model in members:
                self._note(tag, call.call_id, provider, model, SKIPPED_BUDGET)
            raise ModelUnavailableError("the text-model budget is spent (llm.toml [budget])")
        for position, (provider, model) in enumerate(members):
            if position and self._late(call):
                skipped = [pid for pid, _ in members[position:]]
                call.failures.append(
                    f"not tried, the {self.deadline_s:g} s deadline passed: {skipped}"
                )
                break
            call.later = position + 1 < len(members)
            asked, stage = user, ESCALATE if call.escalating else _stage(tag)
            refusal: str | None = None
            for attempt in (0, 1):  # the call, then at most one repair of a refused answer
                if attempt and (left := self._short(call, provider, members[position + 1 :])):
                    call.failures.append(f"{provider}: {refusal} (not repaired, {left})")
                    call.escalating = True
                    call.first_failed = call.first_failed or provider  # its answer was refused
                    break
                called = tag if tag is None else replace(tag, stage=REPAIR if attempt else stage)
                completion = self._ask(call, provider, model, asked, called)
                if completion is None:  # failed or skipped: the next provider
                    if attempt == 1:  # the repair never happened: the first answer was refused
                        call.escalating = True
                        call.first_failed = call.first_failed or provider
                    break
                refusal = _refusal(accept, completion.text)
                if refusal is None:
                    return replace(
                        completion,
                        latency_s=self.clock() - call.started,
                        fell_back_from=call.first_failed,
                    )
                self.reject(called, completion, refusal, asked, len(system) + len(asked))
                if attempt == 0:
                    asked = repair_prompt(user, completion.text, refusal)
                    continue
                call.failures.append(f"{provider}: {refusal} (after one repair)")
                call.first_failed, call.escalating = call.first_failed or provider, True
        unavailable = ModelUnavailableError(
            "no text model could answer: " + "; ".join(call.failures)
        )
        unavailable.call_id = call.call_id
        raise unavailable

    def _late(self, call: "_Call") -> bool:
        return self.clock() - call.started > self.deadline_s

    def _short(
        self, call: "_Call", provider: str, later: Sequence[tuple[str, TextModel]]
    ) -> str | None:
        """Why a repair by ``provider`` must not start, else ``None``: the deadline has passed,
        or, when members follow, the repair's worst case would cut into the time they need (the
        worst cases of ``later`` but the last, as ``LlmSettings`` validates the deadline, so the
        fallback keeps its turn). The last member's repair needs only the deadline not to have
        passed."""
        spent = self.clock() - call.started
        if spent > self.deadline_s:
            return f"the {self.deadline_s:g} s deadline passed"
        if not later:
            return None
        reserve = sum(self.worst_s.get(pid, 0.0) for pid, _ in later[:-1])
        left = self.deadline_s - reserve - spent
        if self.worst_s.get(provider, 0.0) > left:
            return f"{max(left, 0.0):g} s left, the fallback needs {reserve:g} s"
        return None

    def _ask(
        self, call: "_Call", provider: str, model: TextModel, asked: str, called: CallTag | None
    ) -> Completion | None:
        """One request to ``provider`` (recorded as an attempt): its answer, or ``None`` when it
        was skipped (budget) or failed (``ModelUnavailableError``; the cause is noted in
        ``call``). Any other error propagates after what it may have cost is settled."""
        chars = len(call.system) + len(asked)
        if (left := self.cooling_for(provider)) is not None:
            message = f"cooling off, its quota is used up (back in {left:.0f} s)"
            self._note(
                called, call.call_id, provider, model, COOLING_OFF, error=message,
                stage=PROVIDER, user_text=asked, chars=chars,
            )  # fmt: skip
            call.failures.append(f"{provider}: {message}")
            call.first_failed = call.first_failed or provider
            return None
        reserved = self._admit(provider, chars)
        if reserved is None:
            self._note(called, call.call_id, provider, model, SKIPPED_BUDGET)
            call.failures.append(f"{provider}: skipped, the budget is spent")
            return None
        began = self.clock()
        try:
            completion = model.complete(call.system, asked, tag=called, schema=call.schema)
        except ModelUnavailableError as exc:
            self._note(
                called, call.call_id, provider, model, FAILED, reserved,
                took=self.clock() - began, error=str(exc), stage=PROVIDER,
                user_text=asked, chars=chars,
            )  # fmt: skip
            call.failures.append(f"{provider}: {exc}")
            call.first_failed = call.first_failed or provider
            if isinstance(exc, QuotaExhaustedError):
                if self._cool(provider, exc.cool_off_s):  # the warning once, not per skip
                    log.warning(
                        "text model %s quota exhausted, skipped for %.0f s: %s",
                        provider, exc.cool_off_s, exc,
                    )  # fmt: skip
                return None
            # a refusal that retrying cannot fix (bad key, unknown model) needs the owner
            refused = _REFUSED.search(str(exc)) is not None
            log.log(
                logging.ERROR if refused else logging.WARNING,
                "text model %s failed%s: %s",
                provider,
                ", falling back" if call.later else "",
                exc,
            )
            return None
        except Exception as exc:  # a bug propagates, what it may have cost is settled
            self._note(
                called, call.call_id, provider, model, FAILED, reserved,
                took=self.clock() - began, error=f"{type(exc).__name__}: {exc}",
                stage=PROVIDER, user_text=asked, chars=chars,
            )  # fmt: skip
            raise
        self._note(
            called, call.call_id, provider, model, FELL_BACK if call.first_failed else OK,
            reserved, took=self.clock() - began, answer=completion,
            fell_back_from=call.first_failed, chars=chars,
        )  # fmt: skip
        return replace(completion, call_id=call.call_id)

    def reject(
        self,
        tag: CallTag | None,
        completion: Completion,
        reason: str,
        user_text: str,
        prompt_chars: int | None = None,
    ) -> None:
        """The caller could not use ``completion`` (``reason``): log it, with the raw answer and
        ``user_text`` (the prompt), as a ``rejected`` row of the provider that gave it. The ``ok``
        row already carries the cost, so this one has none. Never raises."""
        log.warning(  # the answer itself is in the usage table, not in this log
            "text model %s answer rejected (%s), %d chars",
            completion.provider, clip(reason, MAX_SENTENCE), len(completion.text),
        )  # fmt: skip
        if self.ledger is None:
            return
        try:
            self.ledger.record(
                Attempt(
                    at=self.now(),
                    provider=completion.provider,
                    model=completion.model,
                    use_case=tag.use_case if tag is not None else "untagged",
                    user=tag.user if tag is not None else None,
                    outcome=REJECTED,
                    error=clip(reason, MAX_SENTENCE),
                    stage=ANSWER,
                    sentence=clip(user_text, MAX_SENTENCE),
                    answer=clip(completion.text, MAX_ANSWER),
                    prompt_chars=prompt_chars,
                    call_id=completion.call_id,
                    prompt_version=tag.prompt_version if tag is not None else None,
                    call_stage=tag.stage if tag is not None else "first",
                ),
            )
        except Exception:
            log.exception("the text-model ledger could not record a rejection; the call goes on")

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
        call_id: str,
        provider: str,
        model: TextModel,
        outcome: str,
        reserved: float = 0.0,
        took: float = 0.0,
        answer: Completion | None = None,
        fell_back_from: str | None = None,
        error: str | None = None,
        stage: str | None = None,
        user_text: str | None = None,
        chars: int | None = None,
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
                    cache_read_tokens=answer.cache_read_tokens if answer is not None else None,
                    cache_write_tokens=answer.cache_write_tokens if answer is not None else None,
                    call_id=call_id,
                    prompt_version=tag.prompt_version if tag is not None else None,
                    call_stage=tag.stage if tag is not None else "first",
                    fell_back_from=fell_back_from,
                    error=None if error is None else clip(error, MAX_SENTENCE),
                    stage=stage,
                    sentence=None if user_text is None else clip(user_text, MAX_SENTENCE),
                    prompt_chars=chars,
                ),
                reserved,
            )
        except Exception:
            log.exception("the text-model ledger could not record a call; the call goes on")
