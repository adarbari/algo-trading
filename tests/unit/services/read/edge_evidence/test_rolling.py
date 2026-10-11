"""Rolling starts and the monthly map: pooled from the same windows, never from another source."""

from datetime import date

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
        series_row(date(2026, 12, 7), FROZEN, pick_hits=1, pick_mean=0.01, **kw),
        series_row(date(2027, 1, 4), FROZEN, pick_hits=3, pick_mean=0.03, **kw),
        series_row(date(2027, 2, 1), FROZEN, pick_hits=4, pick_mean=0.05, **kw),
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
    closes = [d + EXIT for d in DAYS]  # 2026-06-02 .. 2026-07-21
    assert all(x.month.day == 1 for x in m.months)
    assert sum(x.trades for x in m.months) == 8
    june = [i for i, c in enumerate(closes) if c.month == 6]
    assert by[date(2026, 6, 1)].value == pytest.approx(sum(0.01 * (i + 1) for i in june))
    assert by[date(2026, 6, 1)].period == "both"  # decided before and after the split
    assert by[date(2026, 7, 1)].period == "out_of_sample"
    assert sum(x.value for x in m.months) == pytest.approx(0.36)  # the curve's last value


def test_no_series_is_unknown(backend: MemoryBackend) -> None:
    stored_run(backend, [])
    found = series_of(read(backend))
    assert isinstance(found, Unknown)
    assert load_rolling_starts(found).unknown is found and load_monthly(found).unknown is found
