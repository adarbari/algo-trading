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
