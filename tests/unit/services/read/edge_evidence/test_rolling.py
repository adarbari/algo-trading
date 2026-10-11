"""Rolling starts and the monthly map: pooled from the same windows, never from another source."""

from datetime import date, timedelta

import pytest

from algotrade.services.read.edge_evidence.rolling import load_monthly, load_rolling_starts
from algotrade.services.read.values import Unknown
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.edge_evidence.stored_result import (
    DAYS,
    EXIT,
    read,
    series_of,
    stored_run,
)
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row


def test_each_years_start_pools_the_windows_decided_from_it_on(backend: MemoryBackend) -> None:
    kw = {"picks": 4, "eligible": 20, "base_hits": 10}
    rows = [
        series_row(date(2026, 12, 14), FROZEN, pick_hits=1, pick_mean=0.01, **kw),
        series_row(date(2027, 2, 1), FROZEN, pick_hits=3, pick_mean=0.03, **kw),
        series_row(date(2027, 3, 15), FROZEN, pick_hits=4, pick_mean=0.05, **kw),
        series_row(
            date(2028, 3, 6), FROZEN, pick_hits=None, pick_mean=0.09, **kw
        ),  # no wins stored
    ]
    stored_run(backend, rows)
    r = load_rolling_starts(series_of(read(backend)))
    assert [(s.start.year, s.trades) for s in r.starts] == [(2026, 3), (2027, 2)]
    # 2026 forward: picks won 8 of 12, the field 10 of 20 each: 66.7% - 50%
    assert r.starts[0].lift_pts == pytest.approx((8 / 12 - 0.5) * 100)
    assert r.starts[1].lift_pts == pytest.approx((7 / 8 - 0.5) * 100)
    assert r.starts[0].mean_excess == pytest.approx(0.03) and r.unit == "excess_return"


def test_a_non_return_outcome_has_a_lift_and_no_mean(backend: MemoryBackend) -> None:
    kw = {"unit": "cushion", "picks": 4, "eligible": 20, "base_hits": 10, "pick_hits": 3}
    stored_run(backend, [series_row(d, FROZEN, **kw) for d in DAYS])
    (start,) = load_rolling_starts(series_of(read(backend))).starts
    assert start.mean_excess is None and start.lift_pts == pytest.approx(25.0)


def test_a_month_is_the_sum_of_the_windows_that_closed_in_it(backend: MemoryBackend) -> None:
    stored_run(
        backend, [series_row(d, FROZEN, pick_mean=0.01 * (i + 1)) for i, d in enumerate(DAYS)]
    )
    m = load_monthly(series_of(read(backend)))
    by = {x.month: x for x in m.months}
    closes = [d + EXIT for d in DAYS]
    assert all(x.month.day == 1 for x in m.months)
    assert sum(x.trades for x in m.months) == 8
    may = [i for i, c in enumerate(closes) if (c.year, c.month) == (2026, 5)]
    assert len(may) == 2 and by[date(2026, 5, 1)].trades == 2
    assert by[date(2026, 5, 1)].value == pytest.approx(sum(0.01 * (i + 1) for i in may))
    assert by[date(2026, 5, 1)].period == "in_sample"
    assert by[date(2026, 7, 1)].period == "out_of_sample"
    assert sum(x.value for x in m.months) == pytest.approx(0.36)  # the curve's last value


def test_a_month_that_closes_windows_of_both_sides_says_both(backend: MemoryBackend) -> None:
    june = {"exit_session": date(2026, 6, 10)}
    stored_run(
        backend,
        [
            series_row(DAYS[3], FROZEN, pick_mean=0.01, **june),  # decided before the split
            series_row(DAYS[4], FROZEN, pick_mean=0.02, exit_session=date(2026, 6, 20)),
        ],
    )
    (month,) = load_monthly(series_of(read(backend))).months
    assert (month.month, month.period, month.trades) == (date(2026, 6, 1), "both", 2)


def test_overlapping_windows_are_weighted_in_a_month_and_in_the_lift(
    backend: MemoryBackend,
) -> None:
    kw = {"picks": 4, "eligible": 20, "base_hits": 10}
    rows = [
        series_row(
            date(2026, 3, 2) + timedelta(days=i), FROZEN, pick_mean=0.02,
            pick_hits=4 if i < 2 else 0, exit_session=date(2026, 4, 1), **kw,
        )
        for i in range(3)  # decided on consecutive days: weights 1 / 20 each (a weekend or not)
    ]  # fmt: skip
    stored_run(backend, rows)
    series = series_of(read(backend))
    (month,) = load_monthly(series).months
    assert month.trades == 3 and month.value < 0.06 and month.value > 0.0
    weights = [w.weight for w in series.windows]  # type: ignore[union-attr]
    assert month.value == pytest.approx(0.02 * sum(weights))


def test_no_series_is_unknown(backend: MemoryBackend) -> None:
    stored_run(backend, [])
    found = series_of(read(backend))
    assert isinstance(found, Unknown)
    assert load_rolling_starts(found).unknown is found and load_monthly(found).unknown is found
