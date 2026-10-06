"""Downsampling a history for a chart (``services/read/market/buckets.py``): every session a
point while they fit, else fixed buckets each keeping its minimum and maximum at their own
sessions (ties to the earliest), an empty bucket one gap, runs of a flag or label merged;
deterministic."""

from datetime import date, timedelta

import pytest

from algotrade.services.read.market.buckets import (
    Point,
    Segment,
    bucket_numbers,
    bucket_sessions_for,
    merge_segments,
)

START = date(2024, 1, 1)


def days(n: int) -> list[date]:
    return [START + timedelta(i) for i in range(n)]


def test_a_window_that_fits_is_every_session_and_a_gap_run_is_one_null() -> None:
    d = days(5)
    size, points = bucket_numbers(d, [1.0, None, None, 3.0, 4.0], points=10)
    assert size == 1
    # one null breaks the line however many sessions are missing
    assert points == (Point(d[0], 1.0), Point(d[1], None), Point(d[3], 3.0), Point(d[4], 4.0))


def test_buckets_keep_each_minimum_and_maximum_at_their_own_session() -> None:
    sessions = days(8)
    values: list[float | None] = [5.0, 9.0, 1.0, 5.0, 2.0, 2.0, 7.0, 3.0]
    size, points = bucket_numbers(sessions, values, points=4)  # two buckets of four
    assert size == 4
    assert points == (  # bucket 1: low 1.0 (day 2), high 9.0 (day 1), by session; bucket 2: below
        Point(sessions[1], 9.0), Point(sessions[2], 1.0),
        Point(sessions[4], 2.0), Point(sessions[6], 7.0),
    )  # fmt: skip


def test_ties_go_to_the_earliest_session_and_a_flat_bucket_is_one_point() -> None:
    sessions = days(4)
    assert bucket_numbers(sessions, [2.0, 2.0, 2.0, 2.0], points=2)[1] == (Point(sessions[0], 2.0),)
    _, points = bucket_numbers(sessions, [1.0, 3.0, 3.0, 1.0], points=2)
    assert points == (Point(sessions[0], 1.0), Point(sessions[1], 3.0))  # earliest low and high


def test_the_last_bucket_may_be_short_and_the_total_stays_within_the_budget() -> None:
    sessions = days(1001)
    values = [float((i * 37) % 101) for i in range(1001)]
    size, points = bucket_numbers(sessions, values, points=100)
    assert size == 21  # ceil(1001 / 50)
    assert len(points) <= 100
    assert list(points) == sorted(points, key=lambda p: p.session)  # oldest first
    assert max(p.value for p in points if p.value is not None) == max(values)  # the spike stays
    assert min(p.value for p in points if p.value is not None) == min(values)


def test_an_empty_bucket_is_one_gap_and_neighbours_share_it() -> None:
    sessions = days(16)
    values: list[float | None] = [1.0, 2.0, *[None] * 12, 4.0, 3.0]
    size, points = bucket_numbers(sessions, values, points=8)
    assert size == 4
    assert points == (
        Point(sessions[0], 1.0), Point(sessions[1], 2.0),
        Point(sessions[4], None),  # buckets 2 and 3 are both empty: one null breaks the line
        Point(sessions[14], 4.0), Point(sessions[15], 3.0),
    )  # fmt: skip
    assert bucket_numbers([], [], 10) == (1, ())


def test_the_same_input_gives_the_same_buckets() -> None:
    values: list[float | None] = [float((i * 7) % 13) if i % 11 else None for i in range(500)]
    assert bucket_numbers(days(500), values, 60) == bucket_numbers(days(500), values, 60)


def test_bucket_sessions_and_inputs_are_checked() -> None:
    assert bucket_sessions_for(600, 600) == 1 and bucket_sessions_for(601, 600) == 3
    assert bucket_sessions_for(13_500, 600) == 45
    with pytest.raises(ValueError, match="at least 2"):
        bucket_sessions_for(10, 1)
    with pytest.raises(ValueError, match="one value per session"):
        bucket_numbers(days(2), [1.0], 10)
    with pytest.raises(ValueError, match="one state per session"):
        merge_segments(days(2), ["ON"])


def test_segments_merge_runs_of_equal_states() -> None:
    d = days(5)
    assert merge_segments(d, ["ON", "ON", "UNKNOWN", "OFF", "OFF"]) == (
        Segment(d[0], d[1], "ON"), Segment(d[2], d[2], "UNKNOWN"), Segment(d[3], d[4], "OFF"),
    )  # fmt: skip
    assert merge_segments([], []) == ()
