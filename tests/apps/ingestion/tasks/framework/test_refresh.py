"""Refresh slots: after a one-night backfill the keys come due spread over the window, each
once per window; missed slot days are caught up; new keys first; ``force``; 0 days."""

from collections import Counter
from datetime import date, timedelta

from algotrade_ingestion.tasks.framework.refresh import due_keys, slot_day

DAY = date(2026, 10, 2)
CIKS = [f"{n:010d}" for n in range(100_000, 106_000)]  # ~ the universe's 6k CIKs


def _simulate(days: int, refresh: int = 30, every: int = 1) -> tuple[Counter[int], dict[str, int]]:
    """Backfill every CIK on DAY, then run every ``every`` days; -> requests per day offset
    and fetches per CIK."""
    fetched = dict.fromkeys(CIKS, DAY)
    per_day: Counter[int] = Counter()
    per_key: Counter[str] = Counter()
    for offset in range(1, days + 1, every):
        session = DAY + timedelta(days=offset)
        for key in due_keys(CIKS, fetched, session, refresh):
            fetched[key] = session
            per_day[offset] += 1
            per_key[key] += 1
    return per_day, dict(per_key)


def test_a_backfill_comes_due_spread_over_the_window() -> None:
    per_day, per_key = _simulate(30)
    assert sum(per_day.values()) == len(CIKS)  # every CIK exactly once in the first window
    assert set(per_key.values()) == {1}
    assert max(per_day.values()) < 2 * len(CIKS) / 30  # no night carries the old 100%
    assert len(per_day) == 30


def test_each_key_refreshes_once_per_window_after_that() -> None:
    _, per_key = _simulate(90)
    assert set(per_key.values()) == {3}


def test_missed_slot_days_are_caught_up_by_the_next_run() -> None:
    per_day, per_key = _simulate(31, every=3)  # runs on days 1, 4, ..., 31
    assert len(per_key) == len(CIKS)  # day 31 also refreshes day 1's slot: 30 days later
    assert len(per_day) == 11


def test_slot_day_is_stable_and_in_the_window() -> None:
    for key in CIKS[:50]:
        day = slot_day(key, DAY, 30)
        assert DAY - timedelta(days=29) <= day <= DAY
        assert slot_day(key, day, 30) == day
        assert slot_day(key, day + timedelta(days=30), 30) == day + timedelta(days=30)


def test_new_keys_first_then_stalest_force_and_zero() -> None:
    fetched = {"b": DAY - timedelta(days=400), "c": DAY - timedelta(days=100), "d": DAY}
    assert due_keys(["d", "c", "b", "a"], fetched, DAY, 30) == ["a", "b", "c"]
    assert due_keys(["d", "a"], fetched, DAY, 30, force=True) == ["a", "d"]
    assert due_keys(["d", "c"], fetched, DAY, 0) == ["c", "d"]
    assert due_keys(["d"], {"d": DAY + timedelta(days=5)}, DAY, 30) == []
