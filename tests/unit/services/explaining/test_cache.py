"""The cache key (the session, the signals and their verdicts, the question, the model) and the
per-user rate limit (ADR 0041, amended)."""

from dataclasses import replace

import pytest

from algotrade.core.model.errors import RateLimitedError
from algotrade.services.explaining.cache import cache_key, open_text_cache, signals_hash
from algotrade.services.explaining.limits import RateLimiter
from algotrade.services.read.regime.indicators import IndicatorStatus
from algotrade.services.read.regime.regime import MarketRegime


def test_the_key_changes_with_the_session_signals_question_and_model(
    regime: MarketRegime,
) -> None:
    key = cache_key(regime, "what is happening?", "gemini")
    assert key == cache_key(regime, "what is happening?", "gemini")
    assert key.startswith("2026-10-01_")
    assert key != cache_key(regime, "Plain curve?", "gemini")
    assert key != cache_key(regime, "what is happening?", "llama")
    other_day = replace(regime, session=regime.session.replace(day=2))
    assert cache_key(other_day, "what is happening?", "gemini").startswith("2026-10-02_")
    assert cache_key(other_day, "what is happening?", "gemini") != key
    flipped = replace(
        regime,
        indicators=(
            replace(regime.indicators[0], status=IndicatorStatus.OFF),
            *regime.indicators[1:],
        ),
    )
    assert signals_hash(flipped) != signals_hash(regime)


def test_a_value_moving_within_its_verdict_keeps_the_key(regime: MarketRegime) -> None:
    moved = replace(
        regime, indicators=(replace(regime.indicators[0], value=-0.3), *regime.indicators[1:])
    )
    assert cache_key(moved, "q", "m") == cache_key(regime, "q", "m")


def test_the_cache_opens_beside_the_store(tmp_path) -> None:  # type: ignore[no-untyped-def]
    memory = open_text_cache("memory://")
    memory.put("k", "text")
    assert memory.get("k") == "text" and memory.get("other") is None
    local = open_text_cache(f"file://{tmp_path}/var/data")
    local.put("k", "text")
    assert (tmp_path / "var" / "cache" / "explanations" / "k.json").is_file()
    assert local.get("k") == "text"


def test_a_user_is_limited_to_six_calls_a_minute() -> None:
    now = [0.0]
    limiter = RateLimiter(6, 60.0, lambda: now[0])
    for _ in range(6):
        limiter.take("ann", "explanations")
    with pytest.raises(RateLimitedError, match="try again in 60 s") as error:
        limiter.take("ann", "explanations")
    assert error.value.retry_after_s == 60
    limiter.take("bob", "explanations")  # another user has their own allowance
    now[0] = 59.5
    with pytest.raises(RateLimitedError) as late:
        limiter.take("ann", "explanations")
    assert late.value.retry_after_s == 1
    now[0] = 60.0
    limiter.take("ann", "explanations")  # the first call left the window
