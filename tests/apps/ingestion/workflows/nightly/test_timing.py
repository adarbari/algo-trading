"""Run timing: derived start / end, share, throughput, sub-steps and the trend flag."""

from datetime import UTC, date, datetime, timedelta

from algotrade_ingestion.tasks.maintenance.quality import Check
from algotrade_ingestion.workflows.nightly.timing import (
    arrival_line,
    arrival_stats,
    minutes_after_close,
    observe,
    percentile,
    step_timings,
)

T0 = datetime(2026, 10, 3, 13, 26, tzinfo=UTC)
STEPS = [
    ("2026-10-02", "earnings", {"status": "COMPLETE", "duration_s": 60.0}),
    ("2026-10-02", "chains", {"status": "PARTIAL", "duration_s": 1200.0}),
    (
        "2026-10-02",
        "rollups",
        {
            "status": "COMPLETE",
            "duration_s": 30.0,
            "result": {"a@v1": {"rows": 600, "seconds": 2.5}, "b@v1": {"rows": 300, "seconds": 9}},
        },
    ),
    ("2026-10-02", "shares", {"status": "COMPLETE", "duration_s": 0.5, "result": {"requested": 3}}),
    ("", "purge-raw", {"status": "COMPLETE", "duration_s": 0.0}),
]
HISTORY = [
    {"earnings": 58.0, "chains": 600.0},
    {"earnings": 62.0, "chains": 700.0, "rollups": 25.0},
    {"earnings": 61.0, "chains": 650.0},
]


def test_timings_follow_the_run_order() -> None:
    items = {("2026-10-02", "earnings"): 41, ("2026-10-02", "chains"): 4200}
    by = {t.step: t for t in step_timings(STEPS, T0, 1290.5, items, HISTORY)}
    assert by["earnings"].start == T0 and by["earnings"].end == T0 + timedelta(minutes=1)
    assert by["chains"].start == by["earnings"].end
    assert by["purge-raw"].start == T0 + timedelta(seconds=1290.5)
    assert round(by["chains"].share, 3) == round(1200 / 1290.5, 3)
    assert by["chains"].items == 4200 and by["chains"].per_min == 210.0
    assert by["chains"].unit == "underlyings"
    assert by["rollups"].items == 900 and by["rollups"].substeps == (("b@v1", 9.0), ("a@v1", 2.5))
    assert by["shares"].items == 3 and by["shares"].per_min is None  # under a second
    assert by["purge-raw"].items is None and by["purge-raw"].previous_s is None


def test_trend_against_previous_and_median() -> None:
    by = {t.step: t for t in step_timings(STEPS, T0, 1290.5, {}, HISTORY)}
    assert (by["chains"].previous_s, by["chains"].median_s) == (600.0, 650.0)
    assert by["chains"].slower and not by["earnings"].slower
    assert by["rollups"].previous_s is None and by["rollups"].median_s == 25.0
    assert not by["rollups"].slower  # +20%
    assert not step_timings(STEPS, None, 0, {}, [])[1].slower  # no history: never flagged
    assert step_timings(STEPS, None, 0, {}, [])[0].start is None


# ----------------------------------------------------------------------------- arrivals


def _attempt(minutes: float, published: bool, step: str = "bars") -> dict:
    return {step: {"arrival": {"minutes_after_close": minutes, "published": published}}}


def test_arrival_stats_use_the_first_published_attempt_per_session() -> None:
    d = [date(2026, 10, i) for i in (1, 2, 5)]
    attempts = [
        (d[0], _attempt(60, False)),
        (d[0], _attempt(240, True)),
        (d[0], _attempt(300, True)),  # later attempts do not count
        (d[1], _attempt(120, True)),
        (d[2], _attempt(60, False)),  # never published in the window
    ]
    (stat,) = arrival_stats(attempts)
    assert (stat.step, stat.sessions, stat.published) == ("bars", 3, 2)
    assert (stat.p50, stat.p90) == (180.0, 228.0)
    assert (
        arrival_line(stat)
        == "first published: p50 180 min, p90 228 min after close (2 of 3 sessions)"
    )


def test_arrival_stats_with_few_or_no_sessions() -> None:
    assert arrival_stats([]) == ()
    assert arrival_stats([(date(2026, 10, 1), {"bars": {"status": "SUCCEEDED"}})]) == ()
    (one,) = arrival_stats([(date(2026, 10, 1), _attempt(90, True))])
    assert (one.p50, one.p90) == (90.0, 90.0)
    (never,) = arrival_stats([(date(2026, 10, 1), _attempt(90, False))])
    assert never.p50 is None and "never published" in arrival_line(never)


def test_arrival_stats_keep_only_the_latest_sessions() -> None:
    attempts = [(date(2026, 10, i), _attempt(i * 10, True)) for i in range(1, 6)]
    (stat,) = arrival_stats(attempts, sessions=2)
    assert stat.sessions == 2 and stat.p50 == 45.0


def test_percentile_interpolates() -> None:
    assert percentile([], 0.5) is None
    assert percentile([10, 20, 30, 40], 0.5) == 25.0
    assert percentile([5], 0.9) == 5


def test_observe_reads_publication_checks() -> None:
    fresh = Check("bars_fresh", "FAIL", "x", pending=True)
    assert observe("bars", [fresh, Check("bars_count", "PASS", "")]) == {"published": False}
    assert observe("bars", [Check("bars_fresh", "PASS", "")]) == {"published": True}
    stale = [
        Check("chains_stale_core", "PASS", "", value=0.02),
        Check("chains_stale_rest", "FAIL", "", pending=True, value=0.53),
    ]
    assert observe("chains", stale) == {"published": False, "stale_share": 0.53}
    assert observe("chains", [Check("chains_fetch", "PASS", "")]) is None
    assert observe("rollups", stale) is None
    assert minutes_after_close(T0, T0 - timedelta(minutes=58)) == 58.0
