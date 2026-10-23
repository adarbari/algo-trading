"""``analyst_revisions@v3``: the EPS revisions of a Yahoo name from Yahoo's own epsTrend when our
own snapshots are not OK (``revisions_basis``), taken in-series, never across vendors (ADR 0080
amendment 2026-10-24)."""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_estimates as ae
from algotrade.features.rollups.consensus import analyst_revisions as rv
from tests.helpers.analyst.snapshots import estimates, put, store, universe, visible

A, B = "EQ:A", "EQ:B"
S = date(2027, 1, 15)
D90, D60, D30 = date(2026, 10, 16), date(2026, 11, 13), date(2026, 12, 11)
YEAR, NEXT = "2026-12-31", "2027-12-31"
REVISIONS = [f"eps_fy1_revision_{d}d" for d in rv.WINDOWS]


def trend(now: float | None, d30: float | None, d60: float | None, d90: float | None) -> dict:
    return {
        "eps_trend_current": now,
        "eps_trend_30d_ago": d30,
        "eps_trend_60d_ago": d60,
        "eps_trend_90d_ago": d90,
    }


def rows(iid: str, eps: float, **more) -> list[dict]:
    return estimates(iid, {YEAR: eps, NEXT: eps + 1}, **more)


def run(writer, ids=(A,)) -> pd.DataFrame:
    fin = pd.concat(
        [
            pd.DataFrame(
                {"instrument_id": [i], "revenue_fy_end": [pd.Timestamp("2025-12-31")]}
            ).assign(qtr_as_of=pd.NaT)
            for i in ids
        ]
    )
    inputs = {ae.SNAPSHOTS: visible(writer, S), ae.UNIVERSE: universe(*ids), ae.FINANCIALS: fin}
    table = conform("t", ae.compute(inputs, S, ae.EstimatesParams()), ae.COLUMNS)
    got = rv.compute({rv.ESTIMATES_TABLE: table, rv.SNAPSHOTS: visible(writer, S)}, S, None)
    return got.set_index("instrument_id")


def yahoo(writer, session: date, eps: float, iid: str = A, **more) -> None:
    put(writer, session, rows(iid, eps, **more), run_id="y", source="yahoo")


def test_a_yahoo_name_with_only_its_trend_reads_revisions_from_the_trend_on_day_one() -> None:
    """ARX-like: Yahoo's only snapshot is tonight's. eps_avg (9.9) is another restatement than
    the trend and never enters: (5.5 - 5.0) / 5.0 and so on, in-series."""
    writer = store()
    yahoo(writer, S, 9.9, **trend(5.5, 5.0, 4.4, 4.0))
    row = run(writer).loc[A]
    assert row["eps_fy1_revision_30d"] == pytest.approx(10.0)
    assert row["eps_fy1_revision_60d"] == pytest.approx(25.0)
    assert row["eps_fy1_revision_90d"] == pytest.approx(37.5)
    assert (row["revisions_status"], row["revisions_basis"]) == (rv.OK, rv.TREND)
    assert row["revisions_source"] == "yahoo"
    # revenue and the analysts count are own history, which does not exist yet
    assert pd.isna(row["revenue_fy1_revision_30d"]) and pd.isna(row["eps_fy1_analysts_change_90d"])


def test_our_own_snapshots_win_when_they_are_ok_whatever_the_trend_says() -> None:
    writer = store()
    for day, eps in ((D90, 4.0), (D60, 4.4), (D30, 5.0)):
        yahoo(writer, day, eps)
    yahoo(writer, S, 5.5, **trend(5.5, 1.0, 1.0, 1.0))  # a trend that would read +450%
    row = run(writer).loc[A]
    assert row["eps_fy1_revision_90d"] == pytest.approx(37.5)  # 4.0 -> 5.5, our own
    assert (row["revisions_status"], row["revisions_basis"]) == (rv.OK, rv.OWN)


def test_a_building_own_history_gives_way_to_the_trend_all_windows_together() -> None:
    writer = store()
    yahoo(writer, D30, 5.0)  # own: only the 30 day window, status BUILDING
    yahoo(writer, S, 5.5, **trend(5.5, 5.0, 4.4, 4.0))
    row = run(writer).loc[A]
    assert row[REVISIONS].tolist() == pytest.approx([10.0, 25.0, 37.5])
    assert row["revisions_basis"] == rv.TREND


def test_an_fmp_name_never_reads_a_trend_even_when_its_rows_carry_one() -> None:
    writer = store()
    put(writer, S, rows(A, 5.5, **trend(5.5, 5.0, 4.4, 4.0)))  # source fmp
    row = run(writer).loc[A]
    assert row["revisions_source"] == "fmp" and row["revisions_basis"] == rv.OWN
    assert row[REVISIONS].isna().all() and row["revisions_status"] == rv.NO_PRIOR


def test_a_yahoo_name_without_a_trend_reads_as_v2_did() -> None:
    writer = store()
    yahoo(writer, S, 5.5)
    row = run(writer).loc[A]
    assert row[REVISIONS].isna().all()
    assert (row["revisions_status"], row["revisions_basis"]) == (rv.NO_PRIOR, rv.OWN)


def test_a_missing_window_is_building_and_a_small_base_has_no_percent_but_is_ok() -> None:
    writer = store()
    yahoo(writer, S, 5.5, **trend(5.5, 5.0, 4.4, None))
    row = run(writer).loc[A]
    assert row[REVISIONS[:2]].tolist() == pytest.approx([10.0, 25.0]) and pd.isna(row[REVISIONS[2]])
    assert (row["revisions_status"], row["revisions_basis"]) == (rv.BUILDING, rv.TREND)
    small = store()
    yahoo(small, S, 5.5, **trend(5.5, 5.0, 4.4, rv.MIN_BASE / 2))
    got = run(small).loc[A]
    assert pd.isna(got["eps_fy1_revision_90d"]) and got["eps_fy1_revision_60d"] == pytest.approx(25)
    assert (got["revisions_status"], got["revisions_basis"]) == (rv.OK, rv.TREND)


def test_only_the_newest_snapshot_row_of_fy1_supplies_the_trend() -> None:
    """Yesterday's trend is not tonight's: when tonight's row has none, nothing is read."""
    writer = store()
    yahoo(writer, D30, 5.0, **trend(5.0, 4.0, 3.0, 2.0))
    yahoo(writer, S, 5.5)
    row = run(writer).loc[A]
    assert row[REVISIONS[1:]].isna().all()  # only our own 30 day snapshot says anything
    assert row["eps_fy1_revision_30d"] == pytest.approx(10.0)  # 5.0 -> 5.5, never 5.0 -> trend
    assert (row["revisions_status"], row["revisions_basis"]) == (rv.BUILDING, rv.OWN)


def test_names_that_are_not_ok_carry_the_own_basis() -> None:
    writer = store()
    put(writer, S, rows(A, 5.5))
    got = run(writer, ids=(A, B))
    assert got["revisions_basis"].tolist() == [rv.OWN, rv.OWN]


def test_the_new_column_and_inputs_are_declared() -> None:
    names = {f.name: f for f in rv.GROUP.features}
    assert names["revisions_basis"].categories == rv.BASES == ("own_snapshots", "vendor_trend")
    assert names["revisions_basis"].licence == "yahoo"
    assert "analyst/estimate_snapshots.eps_trend_90d_ago" in names["eps_fy1_revision_90d"].inputs
    assert rv.VERSION == 3


number = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False)


@settings(max_examples=25, deadline=None)
@given(now=number, d30=number, d60=number, d90=number, eps=number, fmp_eps=number)
def test_nothing_is_ever_differenced_across_vendors(now, d30, d60, d90, eps, fmp_eps) -> None:
    """Whatever FMP's EPS and Yahoo's eps_avg are, a vendor_trend revision is a function of the
    trend alone, in-series; and an FMP name's revisions never read a trend."""
    writer = store()
    yahoo(writer, S, eps, **trend(now, d30, d60, d90))
    put(writer, S, rows(B, fmp_eps, **trend(now, d30, d60, d90)))
    got = run(writer, ids=(A, B))
    for days, then in zip(rv.WINDOWS, (d30, d60, d90), strict=True):
        column = f"eps_fy1_revision_{days}d"
        want = (now - then) / abs(then) * 100 if abs(then) >= rv.MIN_BASE else None
        if want is None:
            assert pd.isna(got.loc[A, column])
        else:
            assert got.loc[A, column] == pytest.approx(want, rel=1e-4, abs=1e-4)
        assert pd.isna(got.loc[B, column])
    assert got.loc[B, "revisions_basis"] == rv.OWN
