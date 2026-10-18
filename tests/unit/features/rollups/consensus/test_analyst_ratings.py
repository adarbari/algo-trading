"""``analyst_ratings@v1``: Finnhub's recommendation counts and score (5 = strong buy), the 90-day
change of the score from our own snapshots only, STALE after 45 days, NOT_COVERED and NOT_FETCHED
told apart, the personal licence."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.consensus import analyst_ratings as ar
from algotrade.features.rollups.consensus.analyst_status import (
    NOT_COVERED,
    NOT_FETCHED,
    OK,
    STALE,
    UNCOVERED,
)
from tests.helpers.analyst.snapshots import (
    estimates,
    marker,
    night,
    put,
    recommendation,
    store,
    universe,
    visible,
)

A, B, C = "EQ:A", "EQ:B", "EQ:C"
S = date(2027, 1, 15)
OLD = date(2026, 10, 16)  # 91 days before S: the snapshot the 90-day change reads
TREND = {"2026-12-01": (3, 5, 10, 1, 1)}  # 20 analysts, score 68 / 20 = 3.4


def run(writer, session: date = S, ids=(A,)) -> pd.DataFrame:
    inputs = {ar.SNAPSHOTS: visible(writer, session), ar.UNIVERSE: universe(*ids)}
    return ar.compute(inputs, session, ar.RatingsParams()).set_index("instrument_id")


def finnhub(writer, session: date, rows: list[dict], **more) -> None:
    put(writer, session, rows, source="finnhub", **more)


def test_the_counts_and_the_score_of_the_newest_month_five_is_strong_buy() -> None:
    writer = store()
    finnhub(writer, S, recommendation(A, {"2026-11-01": (0, 0, 0, 0, 9), **TREND}))
    row = run(writer).loc[A]
    assert [row[f"rating_{n}"] for n in ar.POINTS] == [3, 5, 10, 1, 1]
    assert row["rating_count"] == 20 and row["rating_month"] == date(2026, 12, 1)
    assert row["rating_score"] == pytest.approx(3.4)  # (15 + 20 + 30 + 2 + 1) / 20
    assert row["ratings_status"] == OK


def test_all_strong_buy_scores_five_and_all_strong_sell_one() -> None:
    writer = store()
    finnhub(writer, S, [*recommendation(A, {"2026-12-01": (8, 0, 0, 0, 0)})])
    finnhub(writer, S, [*recommendation(B, {"2026-12-01": (0, 0, 0, 0, 4)})], run_id="b")
    got = run(writer, ids=(A, B))
    assert (got.loc[A, "rating_score"], got.loc[B, "rating_score"]) == (5.0, 1.0)


def test_a_month_nobody_rates_has_count_zero_and_no_score() -> None:
    writer = store()
    finnhub(writer, S, recommendation(A, {"2026-12-01": (0, 0, 0, 0, 0)}))
    row = run(writer).loc[A]
    assert row["rating_count"] == 0 and pd.isna(row["rating_score"])
    assert row["ratings_status"] == OK  # the vendor answered: the count says there is no view


def test_the_change_is_the_score_now_less_the_snapshot_about_90_days_back() -> None:
    writer = store()
    finnhub(writer, OLD, recommendation(A, {"2026-10-01": (2, 4, 10, 2, 2)}))  # 62 / 20 = 3.1
    finnhub(writer, S, recommendation(A, TREND))
    row = run(writer).loc[A]
    assert row["rating_score_change_90d"] == pytest.approx(3.4 - 3.1)


def test_the_change_uses_our_snapshots_never_the_months_the_vendor_lists() -> None:
    """The newest snapshot also lists October (the vendor's restated past); with no snapshot of
    ours 90 days back the change stays null, not December less October."""
    writer = store()
    finnhub(writer, S, recommendation(A, {"2026-10-01": (0, 0, 0, 0, 9), **TREND}))
    assert pd.isna(run(writer).loc[A, "rating_score_change_90d"])
    finnhub(writer, date(2026, 12, 18), recommendation(A, {"2026-12-01": (1, 1, 1, 1, 1)}))
    assert pd.isna(run(writer).loc[A, "rating_score_change_90d"])  # 28 days is not 90


def test_a_snapshot_too_old_for_the_slack_is_not_the_one_90_days_back() -> None:
    writer = store()
    finnhub(writer, date(2026, 10, 2), recommendation(A, {"2026-10-01": (2, 4, 10, 2, 2)}))
    finnhub(writer, S, recommendation(A, TREND))  # 105 days: past 90 + 7
    assert pd.isna(run(writer).loc[A, "rating_score_change_90d"])


def test_the_latest_snapshot_in_the_window_is_the_one_compared() -> None:
    writer = store()
    finnhub(writer, date(2026, 10, 12), recommendation(A, {"2026-10-01": (0, 0, 0, 0, 9)}))
    finnhub(writer, OLD, recommendation(A, {"2026-10-01": (2, 4, 10, 2, 2)}))
    finnhub(writer, S, recommendation(A, TREND))
    assert run(writer).loc[A, "rating_score_change_90d"] == pytest.approx(3.4 - 3.1)


def test_a_snapshot_published_after_the_next_open_is_not_the_history_of_the_session() -> None:
    """The lookahead rule through the input: the old snapshot is re-run late, after Tuesday's
    open that follows the holiday weekend, so Friday's session cannot know it (change null);
    Tuesday's session can."""
    tue = date(2027, 1, 19)
    writer = store()
    finnhub(writer, S, recommendation(A, TREND))
    finnhub(
        writer, OLD, recommendation(A, {"2026-10-01": (2, 4, 10, 2, 2)}), knowledge=night(tue, 15)
    )
    assert pd.isna(run(writer, S).loc[A, "rating_score_change_90d"])
    assert run(writer, tue).loc[A, "rating_score_change_90d"] == pytest.approx(3.4 - 3.1)


def test_a_snapshot_for_a_later_session_is_never_read() -> None:
    """Whatever the frame holds, compute reads snapshots up to its session: Monday's counts
    are not Friday's."""
    writer = store()
    finnhub(writer, S, recommendation(A, TREND))
    finnhub(writer, date(2027, 1, 18), recommendation(A, {"2026-12-01": (0, 0, 0, 0, 9)}))
    inputs = {ar.SNAPSHOTS: visible(writer, date(2027, 1, 18)), ar.UNIVERSE: universe(A)}
    got = ar.compute(inputs, S, ar.RatingsParams()).set_index("instrument_id")
    assert got.loc[A, "rating_score"] == pytest.approx(3.4)


def test_a_snapshot_older_than_45_days_is_stale_and_serves_no_values() -> None:
    writer = store()
    finnhub(writer, date(2026, 12, 1), recommendation(A, TREND))
    assert run(writer, date(2027, 1, 15)).loc[A, "rating_score"] == pytest.approx(3.4)  # 45 days
    stale = run(writer, date(2027, 1, 18)).loc[A]  # 48 days
    assert stale["ratings_status"] == STALE and stale["rating_score"] != stale["rating_score"]
    assert pd.isna(stale["rating_count"]) and pd.isna(stale["rating_month"])


def test_not_covered_and_not_fetched_read_from_finnhubs_own_markers() -> None:
    writer = store()
    finnhub(writer, S, [*recommendation(A, TREND), marker(A, "OK"), marker(C, "EMPTY")])
    # FMP's markers say nothing about Finnhub: B was refused by FMP and never asked of Finnhub
    put(writer, S, [marker(B, "NOT_COVERED"), *estimates("EQ:D", {"2027-12-31": 5.0})], run_id="f")
    got = run(writer, ids=(A, B, C, "EQ:D"))
    assert got["ratings_status"].to_dict() == {
        A: OK,
        B: NOT_FETCHED,
        C: NOT_COVERED,
        "EQ:D": NOT_FETCHED,
    }
    assert got.loc[[B, C], "rating_count"].isna().all()


def test_an_ok_marker_without_a_newer_row_is_the_vendor_having_none_now() -> None:
    writer = store()
    finnhub(writer, date(2027, 1, 8), recommendation(A, TREND))
    finnhub(writer, S, [marker(A, "OK")], run_id="m")
    assert run(writer).loc[A, "ratings_status"] == NOT_COVERED


def test_a_store_without_the_table_reads_every_name_as_never_asked() -> None:
    got = ar.compute({ar.SNAPSHOTS: None, ar.UNIVERSE: universe(A, B)}, S, ar.RatingsParams())
    assert set(got["ratings_status"]) == {NOT_FETCHED} and got["rating_score"].isna().all()


def test_the_output_conforms_and_every_feature_is_personal_and_optional() -> None:
    writer = store()
    finnhub(writer, OLD, recommendation(A, TREND))
    finnhub(writer, S, recommendation(A, TREND))
    conform("t", run(writer, ids=(A, B)).reset_index(), ar.COLUMNS)
    assert all(f.licence == "personal" for f in ar.GROUP.features) and ar.GROUP.optional
    values = [f for f in ar.GROUP.features if f.name != "ratings_status"]
    assert all(f.null_status == "ratings_status" for f in values)
    assert all(f.uncovered_statuses == UNCOVERED for f in values)


def test_stale_days_defaults_to_a_month_and_a_half_and_must_be_positive() -> None:
    assert ar.RatingsParams().stale_days == 45
    with pytest.raises(ValueError, match="stale_days"):
        ar.RatingsParams(stale_days=0)
