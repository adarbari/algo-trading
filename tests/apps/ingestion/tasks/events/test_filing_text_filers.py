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
from algotrade_sources.vendors.sec.daily_index import parse_index
from tests.conftest import REPO_ROOT

SESSION = date(2026, 2, 10)
DAY = date(2026, 2, 3)  # a Tuesday, no SEC holiday
HOLIDAY = date(2025, 2, 17)  # Presidents Day


FULL = (REPO_ROOT / "tests/fixtures/sources/sec/full_index_form_2011q3_hand_built.idx").read_bytes()


class FakeIndex:
    """Answers per day from a script: ``None`` (a 403) or a CIK; the quarter's full index
    (``full_payload``, else a 403) is the recorded fixture, parsed by the real parser."""

    def __init__(
        self, script: dict[date, list[str | None]], full_payload: bytes | None = None
    ) -> None:
        self.script = script
        self.full_payload = full_payload
        self.calls: dict[date, int] = {}
        self.full_calls = 0

    def fetch(self, request: Any) -> Any:
        if request.full:
            self.full_calls += 1
            return self.full_payload
        n = self.calls.get(request.day, 0)
        self.calls[request.day] = n + 1
        answers = self.script[request.day]
        return answers[min(n, len(answers) - 1)]

    def normalize(self, request: Any, payload: Any) -> Any:
        if request.full:
            frame = parse_index(payload, request.forms, full=True)
            return SimpleNamespace(parsed={DAILY_INDEX_FRAME: frame})
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


JULY = [date(2011, 7, d) for d in (1, 5, 6)]  # 2011-07-04 is a holiday


def test_days_with_no_daily_file_are_served_from_the_quarters_full_index_read_once() -> None:
    index = FakeIndex({d: [None] for d in [*JULY, date(2011, 7, 4)]}, FULL)
    slept: list[float] = []
    filers = walk(index, date(2011, 7, 1), date(2011, 7, 6), slept)
    assert filers.ciks == ["0000001213", "0000001234", "0000005678", "0000091011"]
    assert filers.from_full_index == JULY
    assert filers.holidays == [date(2011, 7, 4)]
    assert index.full_calls == 1  # one quarter, one read
    assert all(index.calls[d] == 1 + len(INDEX_RETRY_BACKOFF) for d in JULY)


def test_a_day_absent_from_both_indexes_still_raises_the_gap() -> None:
    index = FakeIndex({date(2011, 7, 7): [None]}, FULL)  # no row for the 7th in the full index
    with pytest.raises(IndexGapError, match=r"2011-07-07"):
        walk(index, date(2011, 7, 7), date(2011, 7, 7), [])
    assert index.full_calls == 1
