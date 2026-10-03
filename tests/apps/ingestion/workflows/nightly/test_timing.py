"""Run timing: derived start / end, share, throughput, sub-steps and the trend flag."""

from datetime import UTC, datetime, timedelta

from algotrade_ingestion.workflows.nightly.timing import step_timings

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
