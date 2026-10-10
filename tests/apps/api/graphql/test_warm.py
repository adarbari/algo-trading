import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from algotrade_api.graphql import warm
from algotrade_api.graphql.warm import CacheWarmer


@dataclass
class _Reader:
    seq: int = 1

    def visible_seq(self) -> int:
        return self.seq


@dataclass
class _Session:
    date: date
    newer: object = None


@dataclass
class _Ctx:
    session: _Session
    reader: _Reader


def test_it_warms_at_start_and_after_each_publish_or_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[tuple[date, int]] = []
    monkeypatch.setattr(warm, "warm", lambda c: warmed.append((c.session.date, c.reader.seq)))
    reader, session = _Reader(), _Session(date(2026, 10, 8))
    warmer = CacheWarmer(lambda: _Ctx(session, reader))  # type: ignore[arg-type, return-value]
    assert warmer.warm_once() and not warmer.warm_once()  # nothing new: nothing read
    reader.seq = 2  # a publish
    assert warmer.warm_once()
    session.date = date(2026, 10, 9)  # the next session
    assert warmer.warm_once()
    assert warmed == [(date(2026, 10, 8), 1), (date(2026, 10, 8), 2), (date(2026, 10, 9), 2)]


def test_it_warms_when_a_session_becomes_complete_without_a_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0062: the nightly's record flipping the served session saves no table."""
    warmed: list[date] = []
    monkeypatch.setattr(warm, "warm", lambda c: warmed.append(c.session.date))
    session = _Session(date(2026, 10, 8), newer="2026-10-09 failing")
    warmer = CacheWarmer(lambda: _Ctx(session, _Reader()))  # type: ignore[arg-type, return-value]
    assert warmer.warm_once() and not warmer.warm_once()
    session.date, session.newer = date(2026, 10, 9), None  # the retry completed 10-09
    assert warmer.warm_once()
    assert warmed == [date(2026, 10, 8), date(2026, 10, 9)]


def test_a_failed_warm_is_logged_and_tried_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[int] = []

    def flaky(_ctx: Any) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("a store mid-publish")

    monkeypatch.setattr(warm, "warm", flaky)
    reader = _Reader()
    ctx = _Ctx(_Session(date(2026, 10, 8)), reader)
    warmer = CacheWarmer(lambda: ctx, every_s=0.01)  # type: ignore[arg-type, return-value]

    async def two_polls() -> None:
        task = asyncio.create_task(warmer.run())
        while len(calls) < 2:
            await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(asyncio.wait_for(two_polls(), 5))
    assert len(calls) == 2 and "warming the read cache failed" in caplog.text


def test_a_failing_step_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ran: list[str] = []

    def boom(_ctx: Any) -> None:
        raise ValueError("no data")

    monkeypatch.setattr(warm, "warm_market_frames", lambda c: ran.append("frames"))
    monkeypatch.setattr(warm, "load_completeness", lambda c, n: ran.append("completeness"))
    monkeypatch.setattr(warm, "load_regime", boom)
    monkeypatch.setattr(
        warm,
        "load_episodes",
        lambda configs: type("E", (), {"episodes": [type("X", (), {"key": "a"})]}),
    )
    monkeypatch.setattr(warm, "load_episode_signals", lambda c, k: ran.append(f"episode {k}"))
    ctx = type("C", (), {"configs": None})()
    warm.warm(ctx)  # type: ignore[arg-type]
    assert ran == ["frames", "completeness", "episode a"] and "regime failed" in caplog.text
