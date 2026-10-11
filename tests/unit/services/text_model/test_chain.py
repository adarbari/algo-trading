"""``FallbackTextModel`` (ADR 0041, amended 2026-10-08): the first member that answers wins, only
``ModelUnavailableError`` moves on to the next, a chain that all failed names every provider,
and one deadline stops a chain from starting more providers."""

import logging
from dataclasses import replace

import pytest

from algotrade.config.site.llm import ProviderSettings
from algotrade.core.model.completion import Attempt, CallTag, Completion
from algotrade.core.model.errors import InvalidAnswerError, ModelUnavailableError
from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.services.text_model.model import TextModel


class Member:
    """A ``TextModel`` that answers, or raises what it was given; counts its calls."""

    def __init__(self, provider: str, outcome: Exception | None = None, clock=None, cost=0.0):  # type: ignore[no-untyped-def]
        self.provider, self.outcome, self.calls = provider, outcome, 0
        self.names = (f"{provider}-model",)
        self.clock, self.cost = clock, cost

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.calls += 1
        if self.clock is not None:
            self.clock.now += self.cost
        if self.outcome is not None:
            raise self.outcome
        return Completion("answer", self.names[0], self.provider, 1, 2, 0.1)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def chain(*members: Member, deadline_s: float = 120.0, clock: Clock | None = None) -> TextModel:
    return FallbackTextModel([(m.provider, m) for m in members], deadline_s, clock or Clock())


def test_the_primary_answers_and_the_secondary_is_not_asked() -> None:
    claude, gemini = Member("claude"), Member("gemini")
    done = chain(claude, gemini).complete("s", "u")
    assert (done.provider, done.model, done.fell_back_from) == ("claude", "claude-model", None)
    assert gemini.calls == 0


def test_the_secondary_answers_when_the_primary_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    claude = Member("claude", ModelUnavailableError("claude-model at x: HTTP 529"))
    gemini = Member("gemini")
    model = chain(claude, gemini)
    with caplog.at_level(logging.WARNING):
        done = model.complete("s", "u")
    assert (done.provider, done.model, done.fell_back_from) == (
        "gemini",
        "gemini-model",
        "claude",
    )
    assert (done.input_tokens, done.output_tokens) == (1, 2)
    assert model.names == ("claude-model", "gemini-model")  # the chain order
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "claude" in caplog.records[0].getMessage() and "HTTP 529" in caplog.text


def test_a_client_error_falls_back_but_is_logged_as_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    claude = Member("claude", ModelUnavailableError("claude-model at x: HTTP 401 bad key"))
    with caplog.at_level(logging.WARNING):
        done = chain(claude, Member("gemini")).complete("s", "u")
    assert done.provider == "gemini"
    assert [r.levelname for r in caplog.records] == ["ERROR"]


def test_all_failed_names_every_provider_with_its_reason() -> None:
    claude = Member("claude", ModelUnavailableError("claude-model: HTTP 401 bad key"))
    gemini = Member("gemini", ModelUnavailableError("gemini-model: timed out"))
    with pytest.raises(ModelUnavailableError) as exc:
        chain(claude, gemini).complete("s", "u")
    message = str(exc.value)
    assert "claude: claude-model: HTTP 401 bad key" in message
    assert "gemini: gemini-model: timed out" in message


def test_any_other_error_propagates_and_asks_no_one_else() -> None:
    claude = Member("claude", ValueError("a bug"))
    gemini = Member("gemini")
    with pytest.raises(ValueError, match="a bug"):
        chain(claude, gemini).complete("s", "u")
    assert gemini.calls == 0


def test_the_deadline_stops_the_chain_starting_another_provider() -> None:
    clock = Clock()
    claude = Member("claude", ModelUnavailableError("slow"), clock, cost=130.0)
    gemini = Member("gemini")
    with pytest.raises(ModelUnavailableError) as exc:
        chain(claude, gemini, deadline_s=120.0, clock=clock).complete("s", "u")
    assert gemini.calls == 0
    assert "claude: slow" in str(exc.value) and "120 s deadline" in str(exc.value)
    assert "gemini" in str(exc.value)  # named as not tried


def test_within_the_deadline_the_next_provider_is_tried() -> None:
    clock = Clock()
    claude = Member("claude", ModelUnavailableError("slow"), clock, cost=100.0)
    gemini = Member("gemini")
    done = chain(claude, gemini, deadline_s=120.0, clock=clock).complete("s", "u")
    assert done.provider == "gemini" and done.latency_s == 100.0


class Tagged(Member):
    """A member that keeps the tag it was asked with."""

    tag: object = None

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.tag = tag
        return super().complete(system, user, tag=tag)


def owner_only(owner: Member, gemini: Member) -> FallbackTextModel:
    return FallbackTextModel(
        [(owner.provider, owner), (gemini.provider, gemini)],
        only_users={owner.provider: frozenset({"abhi"})},
        clock=Clock(),
    )


def test_a_member_limited_to_users_answers_only_them() -> None:
    cli, gemini = Tagged("cli"), Tagged("gemini")
    done = owner_only(cli, gemini).complete("s", "u", tag=CallTag("regime-explain", "abhi"))
    assert done.provider == "cli" and gemini.calls == 0
    assert cli.tag == CallTag("regime-explain", "abhi")  # the tag reaches the member


def test_everyone_else_goes_straight_to_the_next_provider_without_asking_the_limited_one() -> None:
    cli, gemini = Tagged("cli"), Tagged("gemini")
    done = owner_only(cli, gemini).complete("s", "u", tag=CallTag("screener-draft", "bob"))
    assert (done.provider, done.fell_back_from, cli.calls) == ("gemini", None, 0)


def test_a_call_with_no_user_or_no_tag_is_no_one() -> None:
    cli, gemini = Tagged("cli"), Tagged("gemini")
    model = owner_only(cli, gemini)
    assert model.complete("s", "u").provider == "gemini"
    assert model.complete("s", "u", tag=CallTag("regime-explain")).provider == "gemini"
    assert cli.calls == 0


def test_a_chain_with_nothing_for_the_user_is_unavailable() -> None:
    cli = Tagged("cli")
    model = FallbackTextModel([("cli", cli)], only_users={"cli": frozenset({"abhi"})})
    with pytest.raises(ModelUnavailableError, match="may answer this user"):
        model.complete("s", "u", tag=CallTag("screener-draft", "bob"))


def test_the_owners_chain_falls_back_to_gemini_when_the_login_fails() -> None:
    cli = Tagged("cli", ModelUnavailableError("claude-cli haiku: Not logged in"))
    done = owner_only(cli, Tagged("gemini")).complete(
        "s", "u", tag=CallTag("screener-draft", "abhi")
    )
    assert (done.provider, done.fell_back_from) == ("gemini", "cli")


def test_names_for_lists_only_the_models_that_user_may_be_answered_by() -> None:
    model = owner_only(Tagged("cli"), Tagged("gemini"))
    assert model.names == ("cli-model", "gemini-model")
    assert model.names_for("abhi") == ("cli-model", "gemini-model")
    assert model.names_for("bob") == model.names_for(None) == ("gemini-model",)


class Ledger:
    """A ``CallLedger`` that notes attempts and reservations. ``spent``: the paying providers
    (all but "free") are not admitted; ``broken``: ``refuses`` / ``admit`` raise; ``blind``:
    ``spends`` raises too; ``deaf``: ``record`` raises."""

    def __init__(self, spent: bool = False, refuse: bool = False, broken: bool = False,
                 blind: bool = False, deaf: bool = False) -> None:  # fmt: skip
        self.spent, self.refuse, self.broken, self.blind, self.deaf = (
            spent,
            refuse,
            broken,
            blind,
            deaf,
        )
        self.attempts: list[Attempt] = []
        self.reserved: list[float] = []
        self.chars: list[int] = []

    def refuses(self) -> bool:
        if self.broken:
            raise RuntimeError("ledger bug")
        return self.refuse

    def spends(self, provider: str) -> bool:
        if self.blind:
            raise RuntimeError("ledger bug")
        return provider != "free"

    def admit(self, provider: str, prompt_chars: int) -> float | None:
        if self.broken:
            raise RuntimeError("ledger bug")
        if self.spent and self.spends(provider):
            return None
        self.chars.append(prompt_chars)
        return 0.5 if self.spends(provider) else 0.0

    def record(self, attempt: Attempt, reserved: float = 0.0) -> None:
        if self.deaf:
            raise RuntimeError("ledger bug")
        self.attempts.append(attempt)
        self.reserved.append(reserved)


def with_ledger(ledger: Ledger, *members: Member) -> FallbackTextModel:
    return FallbackTextModel([(m.provider, m) for m in members], clock=Clock(), ledger=ledger)


def test_every_attempt_is_recorded_the_failed_one_and_the_one_that_answered() -> None:
    ledger = Ledger()
    claude = Member("claude", ModelUnavailableError("HTTP 529"))
    with_ledger(ledger, claude, Member("gemini")).complete(
        "s", "u", tag=CallTag("screener-draft", "abhi")
    )
    failed, answered = ledger.attempts
    assert (failed.provider, failed.outcome, failed.input_tokens) == ("claude", "failed", None)
    assert (answered.provider, answered.outcome, answered.fell_back_from) == (
        "gemini", "fell_back", "claude")  # fmt: skip
    assert (answered.input_tokens, answered.output_tokens) == (1, 2)
    assert {a.use_case for a in ledger.attempts} == {"screener-draft"}
    assert {a.user for a in ledger.attempts} == {"abhi"}


def test_one_call_id_ties_its_attempts_and_its_rejection_and_the_tag_is_recorded() -> None:
    ledger = Ledger()
    model = with_ledger(ledger, Member("claude", ModelUnavailableError("down")), Member("gemini"))
    tag = CallTag("screener-draft", "abhi", prompt_version="3", stage="repair")
    done = model.complete("s", "u", tag=tag)
    model.reject(tag, done, "not JSON", "u", 2)
    model.complete("s", "u", tag=tag)  # a second call: its own id
    failed, answered, rejected, _failed_again, other = ledger.attempts
    assert failed.call_id and failed.call_id == answered.call_id == rejected.call_id == done.call_id
    assert other.call_id != failed.call_id
    for a in ledger.attempts:
        assert (a.prompt_version, a.call_stage) == ("3", "repair")
    ledger2 = Ledger()
    with_ledger(ledger2, Member("x")).complete("s", "u")
    assert (ledger2.attempts[0].prompt_version, ledger2.attempts[0].call_stage) == (None, "first")


def test_every_member_failing_still_records_each_attempt() -> None:
    ledger = Ledger()
    both = [Member(p, ModelUnavailableError("down")) for p in ("a", "b")]
    with pytest.raises(ModelUnavailableError):
        with_ledger(ledger, *both).complete("s", "u")
    assert [(a.provider, a.outcome, a.use_case) for a in ledger.attempts] == [
        ("a", "failed", "untagged"), ("b", "failed", "untagged")]  # fmt: skip


def test_a_spent_budget_skips_the_paying_member_and_the_free_one_answers() -> None:
    ledger = Ledger(spent=True)
    paid, free = Member("paid"), Member("free")
    done = with_ledger(ledger, paid, free).complete("s", "u")
    assert done.provider == "free" and paid.calls == 0
    assert [(a.provider, a.outcome) for a in ledger.attempts] == [
        ("paid", "skipped_budget"), ("free", "ok")]  # fmt: skip


def test_a_spent_budget_with_no_free_member_is_unavailable() -> None:
    ledger = Ledger(spent=True)
    paid = Member("paid")
    with pytest.raises(ModelUnavailableError, match="budget"):
        with_ledger(ledger, paid).complete("s", "u")
    assert paid.calls == 0


def test_over_refuse_asks_no_one_and_says_why() -> None:
    ledger = Ledger(refuse=True)
    free = Member("free")
    with pytest.raises(ModelUnavailableError, match="budget is spent"):
        with_ledger(ledger, free).complete("s", "u")
    assert free.calls == 0 and [a.outcome for a in ledger.attempts] == ["skipped_budget"]


def test_each_attempt_settles_the_reservation_made_for_it_and_sees_the_prompt_size() -> None:
    ledger = Ledger()
    claude = Member("claude", ModelUnavailableError("down"))
    with_ledger(ledger, claude, Member("free")).complete("sys", "question")
    assert ledger.chars == [len("sys") + len("question")] * 2
    assert ledger.reserved == [0.5, 0.0]  # the failed paid attempt settles its own reservation


def test_a_bug_in_a_member_still_settles_its_reservation() -> None:
    ledger = Ledger()
    with pytest.raises(ValueError):
        with_ledger(ledger, Member("claude", ValueError("a bug"))).complete("s", "u")
    assert [(a.outcome, r) for a, r in zip(ledger.attempts, ledger.reserved, strict=True)] == [
        ("failed", 0.5)
    ]


def test_a_ledger_that_breaks_fails_closed_for_paying_members_and_free_ones_answer() -> None:
    ledger = Ledger(broken=True)
    paid, free = Member("paid"), Member("free")
    done = with_ledger(ledger, paid, free).complete("s", "u")
    assert done.provider == "free" and paid.calls == 0


def test_a_ledger_that_cannot_even_say_who_spends_skips_everyone() -> None:
    ledger = Ledger(broken=True, blind=True)
    free = Member("free")
    with pytest.raises(ModelUnavailableError):
        with_ledger(ledger, free).complete("s", "u")
    assert free.calls == 0


def test_a_ledger_that_cannot_record_never_stops_an_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    done = with_ledger(Ledger(deaf=True), Member("gemini")).complete("s", "u")
    assert done.provider == "gemini" and "could not record" in caplog.text


def test_close_closes_the_ledger() -> None:
    class Closing(Ledger):
        closed = False

        def close(self) -> None:
            self.closed = True

    ledger = Closing()
    with_ledger(ledger, Member("free")).close()
    assert ledger.closed
    FallbackTextModel([("free", Member("free"))]).close()  # no ledger: nothing to do


def test_a_failed_attempt_records_its_message_the_prompt_and_its_length() -> None:
    ledger = Ledger()
    claude = Member("claude", ModelUnavailableError("claude: is_error: timed out"))
    with_ledger(ledger, claude, Member("gemini")).complete(
        "system text", "what the trader typed", tag=CallTag("screener-draft", "abhi")
    )
    failed, answered = ledger.attempts
    assert (failed.stage, failed.error) == ("provider", "claude: is_error: timed out")
    assert failed.sentence == "what the trader typed"
    assert failed.prompt_chars == len("system text") + len("what the trader typed")
    assert (answered.error, answered.stage, answered.sentence, answered.answer) == (None,) * 4
    assert answered.prompt_chars == failed.prompt_chars


def test_a_prompt_over_the_cap_is_clipped_in_the_record() -> None:
    ledger = Ledger()
    claude = Member("claude", ModelUnavailableError("down"))
    with pytest.raises(ModelUnavailableError):
        with_ledger(ledger, claude).complete("s", "x" * 5000)
    (failed,) = ledger.attempts
    assert failed.sentence is not None and len(failed.sentence) == 2000
    assert failed.prompt_chars == 5001


def test_reject_records_the_unusable_answer_as_a_second_row_and_logs_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ledger = Ledger()
    model = with_ledger(ledger, Member("claude"))
    tag = CallTag("screener-draft", "abhi")
    done = model.complete("s", "typed", tag=tag)
    with caplog.at_level("WARNING"):
        model.reject(tag, replace(done, text="Sure! not json"), "not JSON", "typed", 6)
    ok, rejected = ledger.attempts
    assert ok.outcome == "ok" and ok.stage is None
    assert (rejected.outcome, rejected.stage, rejected.error) == ("rejected", "answer", "not JSON")
    assert (rejected.provider, rejected.use_case, rejected.user) == (
        "claude", "screener-draft", "abhi")  # fmt: skip
    assert (rejected.sentence, rejected.answer, rejected.prompt_chars) == (
        "typed", "Sure! not json", 6)  # fmt: skip
    assert rejected.input_tokens is None and rejected.reported_cost_usd is None
    assert "not JSON" in caplog.text and "14 chars" in caplog.text
    assert "Sure! not json" not in caplog.text  # the answer is in the usage table, not the log


def test_reject_never_raises_when_the_ledger_breaks_and_works_without_one() -> None:
    done = Completion("t", "m", "claude")
    with_ledger(Ledger(deaf=True), Member("claude")).reject(None, done, "why", "u")
    FallbackTextModel([("claude", Member("claude"))]).reject(None, done, "why", "u")


# ------------------------------------------------ validate, repair once, escalate (ADR 0041)


class Scripted:
    """A member that gives its answers in order and keeps what each call was given."""

    def __init__(self, provider: str, *answers: str) -> None:
        self.provider, self.answers = provider, list(answers)
        self.names = (f"{provider}-model",)
        self.seen: list[tuple[str, str | None, object]] = []  # user, stage, schema

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.seen.append((user, tag.stage if tag else None, schema))
        return Completion(self.answers.pop(0), self.names[0], self.provider, 1, 2, 0.1)


def only_good(text: str) -> None:
    if text != "good":
        raise InvalidAnswerError(f"{text!r} is not good")


SCHEMA = {"type": "object"}
TAG = CallTag("screener-draft", "abhi")


def test_a_valid_first_answer_is_one_call_with_the_schema_passed_down() -> None:
    cheap = Scripted("cheap", "good")
    ledger = Ledger()
    done = with_ledger(ledger, cheap, Scripted("strong")).complete(
        "s", "u", tag=TAG, schema=SCHEMA, accept=only_good
    )
    assert done.text == "good" and done.fell_back_from is None
    assert cheap.seen == [("u", "first", SCHEMA)]
    assert [(a.outcome, a.call_stage) for a in ledger.attempts] == [("ok", "first")]


def test_an_invalid_answer_is_repaired_once_by_the_same_provider() -> None:
    cheap, strong = Scripted("cheap", "bad", "good"), Scripted("strong")
    ledger = Ledger()
    done = with_ledger(ledger, cheap, strong).complete("s", "u", tag=TAG, accept=only_good)
    assert (done.provider, done.text, done.fell_back_from) == ("cheap", "good", None)
    assert [stage for _, stage, _ in cheap.seen] == ["first", "repair"] and not strong.seen
    repair = cheap.seen[1][0]
    assert repair.startswith("u") and "'bad' is not good" in repair  # the question and the error
    assert (
        "Your answer was rejected: 'bad' is not good. Return only the corrected JSON object."
        in repair
    )
    assert [a.outcome for a in ledger.attempts] == ["ok", "rejected", "ok"]
    assert ledger.attempts[1].answer == "bad" and ledger.attempts[1].call_stage == "first"
    assert len({a.call_id for a in ledger.attempts}) == 1


def test_invalid_twice_escalates_to_the_next_provider_with_rejected_rows() -> None:
    cheap, strong = Scripted("cheap", "bad", "worse"), Scripted("strong", "good")
    ledger = Ledger()
    done = with_ledger(ledger, cheap, strong).complete("s", "u", tag=TAG, accept=only_good)
    assert (done.provider, done.fell_back_from) == ("strong", "cheap")
    assert [stage for _, stage, _ in cheap.seen] == ["first", "repair"]
    assert [stage for _, stage, _ in strong.seen] == ["escalate"]
    assert strong.seen[0][0] == "u"  # the next provider is asked the original question afresh
    assert [(a.provider, a.outcome, a.call_stage) for a in ledger.attempts] == [
        ("cheap", "ok", "first"),
        ("cheap", "rejected", "first"),
        ("cheap", "ok", "repair"),
        ("cheap", "rejected", "repair"),
        ("strong", "fell_back", "escalate"),
    ]
    assert ledger.attempts[3].error == "'worse' is not good"


def test_every_provider_refused_is_an_error_naming_each_cause_after_at_most_two_calls_each() -> (
    None
):
    a, b = Scripted("a", "x1", "x2"), Scripted("b", "y1", "y2")
    with pytest.raises(ModelUnavailableError) as raised:
        chain(a, b).complete("s", "u", tag=TAG, accept=only_good)
    message = str(raised.value)
    assert "'x2' is not good" in message and "'y2' is not good" in message
    assert len(a.seen) == len(b.seen) == 2


def test_an_unavailable_provider_is_not_repaired_and_the_next_is_not_an_escalation() -> None:
    down, strong = Member("down", ModelUnavailableError("HTTP 503")), Scripted("strong", "good")
    done = chain(down, strong).complete("s", "u", tag=TAG, accept=only_good)
    assert done.text == "good" and down.calls == 1
    assert strong.seen[0][1] == "first"


def test_no_repair_or_escalation_starts_after_the_deadline() -> None:
    clock = Clock()

    class Slow(Scripted):
        def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            clock.now += 100.0
            return super().complete(*args, **kwargs)

    slow, strong = Slow("slow", "bad", "good"), Scripted("strong", "good")
    with pytest.raises(ModelUnavailableError, match="deadline"):
        chain(slow, strong, deadline_s=60.0, clock=clock).complete(
            "s", "u", tag=TAG, accept=only_good
        )
    assert len(slow.seen) == 1 and not strong.seen


def test_without_accept_the_answer_is_returned_as_before() -> None:
    cheap = Scripted("cheap", "bad")
    assert chain(cheap).complete("s", "u").text == "bad" and len(cheap.seen) == 1


class Timed(Scripted):
    """A scripted member whose every call takes ``took`` seconds of the injected clock."""

    def __init__(self, clock: Clock, took: float, provider: str, *answers: str) -> None:
        super().__init__(provider, *answers)
        self.clock, self.took = clock, took

    def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.clock.now += self.took
        return super().complete(*args, **kwargs)


def reserving(clock: Clock, *members: Scripted, worst: dict[str, float]) -> FallbackTextModel:
    return FallbackTextModel([(m.provider, m) for m in members], 100.0, clock, worst_s=worst)


def test_a_repair_that_would_cut_into_the_fallbacks_reserved_time_is_skipped() -> None:
    clock = Clock()
    a, b, c = Timed(clock, 30, "a", "bad"), Scripted("b", "good"), Scripted("c")
    worst = {"a": 50.0, "b": 40.0, "c": 10.0}  # a's repair needs 50 s; b must keep 40 of 100
    model = reserving(clock, a, b, c, worst=worst)
    done = model.complete("s", "u", tag=TAG, accept=only_good)
    assert done.provider == "b" and len(a.seen) == 1  # 30 + 50 > 100 - 40: not repaired
    assert [s for _, s, _ in b.seen] == ["escalate"]


def test_a_repair_runs_when_time_allows_and_the_last_member_repairs_with_no_reserve() -> None:
    clock = Clock()
    a = Timed(clock, 5, "a", "bad", "good")
    assert (
        reserving(clock, a, Scripted("b"), worst={"a": 50.0, "b": 40.0})
        .complete("s", "u", tag=TAG, accept=only_good)
        .text
        == "good"
        and len(a.seen) == 2
    )  # 5 + 50 <= 100 - 0 (b is last)
    clock2 = Clock()
    down = Member("down", ModelUnavailableError("HTTP 503"))
    last = Timed(clock2, 40, "last", "bad", "good")  # 40 + 50 <= 100: the last has no reserve
    done = reserving(clock2, down, last, worst={"down": 1.0, "last": 50.0}).complete(
        "s", "u", tag=TAG, accept=only_good
    )
    assert done.text == "good" and [s for _, s, _ in last.seen] == ["first", "repair"]


class AdmitFirst(Ledger):
    """Admits (and reserves 0.5 USD for) the first request only: the budget runs out after it."""

    def admit(self, provider: str, prompt_chars: int) -> float | None:
        if self.reserved and provider == "cheap":
            return None
        return super().admit(provider, prompt_chars)


def test_a_repair_refused_by_the_budget_keeps_the_fallback_trail_and_settles_each_attempt() -> None:
    cheap, free = Scripted("cheap", "bad"), Scripted("free", "good")
    ledger = AdmitFirst()
    done = with_ledger(ledger, cheap, free).complete("s", "u", tag=TAG, accept=only_good)
    assert len(cheap.seen) == 1  # the repair was never asked
    assert (done.provider, done.fell_back_from) == ("free", "cheap")
    assert [(a.provider, a.outcome, a.call_stage) for a in ledger.attempts] == [
        ("cheap", "ok", "first"),
        ("cheap", "rejected", "first"),
        ("cheap", "skipped_budget", "repair"),
        ("free", "fell_back", "escalate"),
    ]
    assert ledger.reserved == [0.5, 0.0, 0.0, 0.0]  # the first attempt's reserve settled once


def test_a_refused_answer_whose_repair_misses_the_deadline_still_falls_back_from_it() -> None:
    clock = Clock()
    slow = Timed(clock, 100, "slow", "bad")
    chained = FallbackTextModel([("slow", slow), ("b", Scripted("b", "good"))], 150.0, clock)
    chained = reserving(clock, slow, Scripted("b", "good"), worst={"slow": 80.0, "b": 1.0})
    done = chained.complete("s", "u", tag=TAG, accept=only_good)  # 100 + 80 > 100: no repair
    assert (done.provider, done.fell_back_from) == ("b", "slow")


def default_chain(clock: Clock, *members: Timed) -> FallbackTextModel:
    """The chain as llm.toml builds it with no ``deadline_s``: the sum of every worst case."""
    providers = [ProviderSettings(m.provider, "http://x/v1", "m") for m in members]
    worst = {p.id: p.worst_case_s for p in providers}
    return FallbackTextModel(
        [(m.provider, m) for m in members], sum(worst.values()), clock, worst_s=worst
    )


def test_a_single_provider_chain_repairs_under_the_default_deadline() -> None:
    clock = Clock()
    done = default_chain(clock, Timed(clock, 5, "only", "bad", "good")).complete(
        "s", "u", tag=TAG, accept=only_good
    )
    assert done.text == "good"


def test_the_first_skips_its_repair_for_the_fallback_but_the_last_repairs() -> None:
    clock = Clock()
    first = Timed(clock, 230, "first", "bad")  # worst case 220 s: 230 + 220 > the 440 s deadline
    last = Timed(clock, 5, "last", "bad", "good")
    done = default_chain(clock, first, last).complete("s", "u", tag=TAG, accept=only_good)
    assert (done.provider, done.text, done.fell_back_from) == ("last", "good", "first")
    assert [stage for _, stage, _ in last.seen] == ["escalate", "repair"] and len(first.seen) == 1


def test_the_not_repaired_failure_says_why_the_answer_was_refused() -> None:
    clock = Clock()
    slow = Timed(clock, 100, "slow", "bad")
    with pytest.raises(ModelUnavailableError, match=r"'bad' is not good \(not repaired, the 60 s"):
        chain(slow, deadline_s=60.0, clock=clock).complete("s", "u", tag=TAG, accept=only_good)
