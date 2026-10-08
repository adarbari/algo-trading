"""``FallbackTextModel`` (ADR 0041, amended 2026-10-08): the first member that answers wins, only
``ModelUnavailableError`` moves on to the next, a chain that all failed names every provider,
and one deadline stops a chain from starting more providers."""

import logging

import pytest

from algotrade.core.model.completion import Attempt, CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError
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

    def complete(self, system: str, user: str, *, tag: object = None) -> Completion:
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

    def complete(self, system: str, user: str, *, tag: object = None) -> Completion:
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
