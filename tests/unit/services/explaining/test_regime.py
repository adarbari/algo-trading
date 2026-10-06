"""``explain_regime`` (ADR 0041, amended): the fixed question or a card, a cached answer for the
same signals (free, and checked again), the model asked and rate-limited otherwise, an unchecked
answer never kept."""

import json

import pytest

from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError, RateLimitedError
from algotrade.services.explaining.limits import RateLimiter
from algotrade.services.explaining.regime import explain_regime
from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.storage.backends.text_cache import MemoryTextCache
from tests.unit.services.explaining.conftest import Canned, Down
from tests.unit.services.read.instruments.conftest import D0
from tests.unit.services.read.regime.conftest import regime_ctx

GOOD = json.dumps({"text": "A storm: stress is 71 out of 100.", "links": []})
BAD = json.dumps({"text": "A storm: stress is 99 out of 100.", "links": []})


@pytest.fixture
def ctx() -> ReadContext:
    return regime_ctx()


def ask(
    ctx: ReadContext,
    model: object,
    cache: MemoryTextCache,
    limiter: RateLimiter,
    question: str | None = "What is happening?",
    card: str | None = None,
):  # type: ignore[no-untyped-def]
    return explain_regime(ctx, model, cache, limiter, "ann", question, card)  # type: ignore[arg-type]


def test_the_second_ask_reads_the_cache(ctx: ReadContext) -> None:
    model, cache, limiter = Canned(GOOD), MemoryTextCache(), RateLimiter()
    first = ask(ctx, model, cache, limiter)
    second = ask(ctx, model, cache, limiter)
    assert (first.cached, second.cached) == (False, True)
    assert first.explanation == second.explanation and first.explanation.checked
    assert len(model.asked) == 1
    assert len(limiter._calls["ann"]) == 1  # a cache hit is free


def test_a_card_is_asked_by_its_plain_name(ctx: ReadContext) -> None:
    model = Canned(GOOD)
    ask(ctx, model, MemoryTextCache(), RateLimiter(), question=None, card="trend")
    system, user = model.asked[0]
    assert user == "Plain trend?" and "Why it matters: Why trend matters." in system


def test_an_unchecked_answer_is_not_kept(ctx: ReadContext) -> None:
    model, cache = Canned(BAD), MemoryTextCache()
    found = ask(ctx, model, cache, RateLimiter())
    assert not found.explanation.checked and found.explanation.text == ""
    ask(ctx, model, cache, RateLimiter())
    assert len(model.asked) == 2  # asked again: nothing was cached


def test_a_cached_answer_that_no_longer_checks_is_asked_again(ctx: ReadContext) -> None:
    model, cache = Canned(GOOD), MemoryTextCache()
    ask(ctx, model, cache, RateLimiter())
    (key,) = cache._items
    cache._items[key] = BAD  # the facts moved under it
    found = ask(ctx, model, cache, RateLimiter())
    assert found.cached is False and found.explanation.checked and len(model.asked) == 2


def test_the_sixth_call_a_minute_is_the_last(ctx: ReadContext) -> None:
    now = [0.0]
    limiter = RateLimiter(2, 60.0, lambda: now[0])
    for card in ("curve", "trend"):
        ask(ctx, Canned(GOOD), MemoryTextCache(), limiter, question=None, card=card)
    with pytest.raises(RateLimitedError):
        ask(ctx, Canned(GOOD), MemoryTextCache(), limiter)


@pytest.mark.parametrize(
    ("question", "card", "message"),
    [
        (None, None, "one of question or card"),
        ("what is happening?", "curve", "one of question or card"),
        ("should I sell everything?", None, "the only question"),
    ],
)
def test_bad_asks_are_configuration_errors(
    ctx: ReadContext, question: str | None, card: str | None, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        ask(ctx, Canned(GOOD), MemoryTextCache(), RateLimiter(), question, card)


def test_an_unknown_card_is_not_found(ctx: ReadContext) -> None:
    with pytest.raises(NotFoundError, match="nope"):
        ask(ctx, Canned(GOOD), MemoryTextCache(), RateLimiter(), question=None, card="nope")


def test_an_unknown_regime_has_nothing_to_explain() -> None:
    with pytest.raises(ConfigurationError, match="not computed"):
        ask(regime_ctx(D0), Canned(GOOD), MemoryTextCache(), RateLimiter())


def test_a_model_that_is_down_propagates_and_caches_nothing(ctx: ReadContext) -> None:
    cache = MemoryTextCache()
    with pytest.raises(ModelUnavailableError):
        ask(ctx, Down(), cache, RateLimiter())
    assert not cache._items
