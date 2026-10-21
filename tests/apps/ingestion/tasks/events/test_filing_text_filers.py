"""``walk_index``: SEC's daily index answers a transient 403 on days that exist, so a weekday
with no index is re-read a few times before it is a gap (a holiday or allowed day is never)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade_ingestion.tasks.events.filing_text_filers import (
    INDEX_RETRY_BACKOFF,
    IndexGapError,
    walk_index,
)
from algotrade_sources.framework.series import DAILY_INDEX_FRAME

SESSION = date(2026, 2, 10)
DAY = date(2026, 2, 3)  # a Tuesday, no SEC holiday
HOLIDAY = date(2025, 2, 17)  # Presidents Day


class FakeIndex:
    """Answers per day from a script: ``None`` (a 403) or a CIK."""

    def __init__(self, script: dict[date, list[str | None]]) -> None:
        self.script = script
        self.calls: dict[date, int] = {}

    def fetch(self, request: Any) -> str | None:
        n = self.calls.get(request.day, 0)
        self.calls[request.day] = n + 1
        answers = self.script[request.day]
        return answers[min(n, len(answers) - 1)]

    def normalize(self, request: Any, payload: str) -> Any:
        frame = pd.DataFrame({"cik": [payload]})
        return SimpleNamespace(parsed={DAILY_INDEX_FRAME: frame})


def walk(index: FakeIndex, since: date, until: date, slept: list[float], **kw: Any) -> Any:
    return walk_index(
        SimpleNamespace(session=SESSION), index, since, until, sleep=slept.append, **kw
    )


def test_a_day_that_returns_none_twice_then_data_is_not_a_gap() -> None:
    index = FakeIndex({DAY: [None, None, "0000000001"]})
    slept: list[float] = []
    filers = walk(index, DAY, DAY, slept)
    assert filers.ciks == ["0000000001"]
    assert index.calls[DAY] == 3
    assert slept == list(INDEX_RETRY_BACKOFF[:2])


def test_a_day_that_returns_none_every_attempt_still_raises_the_gap() -> None:
    index = FakeIndex({DAY: [None]})
    slept: list[float] = []
    with pytest.raises(IndexGapError, match=r"2026-02-03"):
        walk(index, DAY, DAY, slept)
    assert index.calls[DAY] == 1 + len(INDEX_RETRY_BACKOFF)
    assert slept == list(INDEX_RETRY_BACKOFF)


def test_a_holiday_and_an_allowed_day_are_not_retried() -> None:
    index = FakeIndex({HOLIDAY: [None], DAY: [None]})
    slept: list[float] = []
    filers = walk(index, HOLIDAY, HOLIDAY, slept)
    assert filers.holidays == [HOLIDAY]
    filers = walk(index, DAY, DAY, slept, allowed={DAY})
    assert filers.holidays == [DAY]
    assert index.calls == {HOLIDAY: 1, DAY: 1}
    assert slept == []
