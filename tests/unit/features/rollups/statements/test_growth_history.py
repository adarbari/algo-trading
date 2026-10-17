"""growth_history@v1: the revenue and EPS TTMs three and five years back from hand-built facts
(four quarters, or the fiscal year, ending near the target), a hole in that history giving
null, a restatement filed after the session ignored, EPS split-adjusted, the statuses and the
longer window."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.rollups.statements import growth_history as gh
from algotrade.features.rollups.statements.ttm import trailing_ago

FIRST_END = date(2020, 3, 31)  # 24 quarters ending every 91 days: the last on 2025-12-26
QUARTERS = 24
LAST_END = FIRST_END + timedelta(days=91 * (QUARTERS - 1))
SESSION = LAST_END + timedelta(days=60)  # the last quarter was filed 40 days after its end
REVENUE_TAG, EPS_TAG = "us-gaap:Revenues", "us-gaap:EarningsPerShareDiluted"
P = gh.GrowthParams()


def quarter(  # type: ignore[no-untyped-def]
    n: int, value: float, concept: str = "revenue", iid: str = "EQ:A", lag: int = 40, **over
) -> dict:
    end = FIRST_END + timedelta(days=91 * n)
    row = {
        "instrument_id": iid, "concept": concept, "value": float(value),
        "tag": EPS_TAG if concept == "eps_diluted" else REVENUE_TAG,
        "period_start": end - timedelta(days=89), "period_end": end,
        "filed": end + timedelta(days=lag),
    }  # fmt: skip
    return {**row, **over}


def history(concept: str = "revenue", iid: str = "EQ:A", skip: tuple[int, ...] = ()) -> list[dict]:
    """Quarter n is worth n + 1 (revenue), so a window's sum is easy to state by hand."""
    return [quarter(n, n + 1, concept, iid) for n in range(QUARTERS) if n not in skip]


def window(last: int) -> float:
    """The TTM of the four quarters ending at index ``last`` of ``history``."""
    return float(sum(range(last - 2, last + 2)))


def run(
    facts: list[dict], splits: list[dict] | None = None, ids: tuple[str, ...] = ("EQ:A",),
    session: date = SESSION,
) -> pd.DataFrame:  # fmt: skip
    stats = pd.DataFrame({"instrument_id": list(ids), "session_date": session})
    inputs = {gh.PRICE_STATS: stats, gh.FACTS: pd.DataFrame(facts) if facts else None}
    if splits:
        inputs[gh.SPLITS] = pd.DataFrame(splits)
    return (
        gh.compute(inputs, session, P).set_index("instrument_id").reindex(columns=list(gh.COLUMNS))
    )


def test_three_and_five_year_ttms_are_the_four_quarters_ending_that_long_before() -> None:
    row = run(history() + history("eps_diluted")).loc["EQ:A"]
    assert row["revenue_ttm_3y_ago"] == window(QUARTERS - 1 - 12)  # quarters 8..11: 9+10+11+12
    assert row["revenue_ttm_5y_ago"] == window(QUARTERS - 1 - 20)  # quarters 0..3: 1+2+3+4
    assert row["revenue_ttm_5y_ago"] == 10.0 and row["revenue_ttm_3y_ago"] == 42.0
    assert row["eps_diluted_ttm_3y_ago"] == 42.0 and row["eps_diluted_ttm_5y_ago"] == 10.0
    assert row["gh_status"] == "OK"


def test_a_hole_in_the_history_is_null_never_a_shorter_sum() -> None:
    row = run(history(skip=(10,)) + history("eps_diluted")).loc["EQ:A"]  # inside quarters 8..11
    assert pd.isna(row["revenue_ttm_3y_ago"]) and row["revenue_ttm_5y_ago"] == 10.0
    assert row["eps_diluted_ttm_3y_ago"] == 42.0  # the other concept's history is whole
    assert row["gh_status"] == "PARTIAL"


def test_a_history_shorter_than_five_years_has_a_three_year_value_only() -> None:
    facts = [f for f in history() + history("eps_diluted") if f["period_end"] > date(2021, 1, 1)]
    row = run(facts).loc["EQ:A"]
    assert row["revenue_ttm_3y_ago"] == 42.0 and pd.isna(row["revenue_ttm_5y_ago"])
    assert row["gh_status"] == "PARTIAL"


def test_a_restatement_filed_after_the_session_never_moves_it() -> None:
    after = SESSION + timedelta(days=2)
    restated = quarter(9, 1000.0, filed=after)  # quarter 9 sits in the 3y window; same period
    facts = [*history(), restated, *history("eps_diluted")]
    assert run(facts).loc["EQ:A", "revenue_ttm_3y_ago"] == 42.0  # as first filed
    later = run(facts, session=after + timedelta(days=1)).loc["EQ:A", "revenue_ttm_3y_ago"]
    assert later == 42.0 - 10.0 + 1000.0  # the restatement counts from its filing date
    never_public = [f for f in history() if f["period_end"] != quarter(11, 0)["period_end"]]
    late = quarter(11, 12.0, filed=after)  # the only filing of that quarter is after S
    assert pd.isna(run([*never_public, late]).loc["EQ:A", "revenue_ttm_3y_ago"])


def test_eps_is_split_adjusted_to_the_session_by_filing_date() -> None:
    eps = [quarter(n, 1.0, "eps_diluted") for n in range(QUARTERS)]
    split_day = quarter(15, 0)["filed"] + timedelta(days=1)  # after quarters 0..15 were filed
    split = [{"instrument_id": "EQ:A", "event_date": split_day, "ratio": 2.0}]
    row = run(history() + eps, split).loc["EQ:A"]
    assert row["eps_diluted_ttm_3y_ago"] == 2.0 and row["eps_diluted_ttm_5y_ago"] == 2.0
    assert row["revenue_ttm_3y_ago"] == 42.0  # revenue is not per share
    ahead = [{**split[0], "event_date": SESSION + timedelta(days=5)}]  # not yet effective
    assert run(history() + eps, ahead).loc["EQ:A", "eps_diluted_ttm_3y_ago"] == 4.0


def test_a_fiscal_year_reporter_has_its_year_ending_near_the_target() -> None:
    ends = [date(2019 + y, 12, 31) for y in range(7)]  # 2019..2025, annual facts only
    facts = [
        {
            "instrument_id": "EQ:Y", "concept": "revenue", "value": 100.0 * (y + 1),
            "tag": REVENUE_TAG, "period_start": e - timedelta(days=364), "period_end": e,
            "filed": e + timedelta(days=50),
        }
        for y, e in enumerate(ends)
    ]  # fmt: skip
    row = run(facts, ids=("EQ:Y",), session=date(2026, 3, 1)).loc["EQ:Y"]
    assert row["revenue_ttm_3y_ago"] == 400.0  # fiscal 2022: the newest is 2025
    assert row["revenue_ttm_5y_ago"] == 200.0


def test_trailing_ago_tolerates_forty_days_and_no_more() -> None:
    def fact(end: date, value: float) -> tuple[int, int, float, int, int]:
        e = (end - date(1970, 1, 1)).days
        return (e - 364, e, value, e + 50, 0)

    newest = date(2025, 12, 31)
    near = [fact(date(2022, 11, 25), 7.0), fact(newest, 9.0)]  # 36 days off 2022-12-31
    far = [fact(date(2022, 11, 15), 7.0), fact(newest, 9.0)]  # 46 days off
    end = (newest - date(1970, 1, 1)).days
    assert trailing_ago(near, end, 3) == 7.0
    assert trailing_ago(far, end, 3) is None


def test_statuses_and_missing_facts() -> None:
    mixed = history() + history("eps_diluted") + history(iid="EQ:B")
    out = run(mixed, ids=("EQ:A", "EQ:B", "EQ:Z"))
    assert out.loc["EQ:A", "gh_status"] == "OK"
    assert out.loc["EQ:B", "gh_status"] == "PARTIAL"  # no EPS facts at all
    assert (
        out.loc["EQ:Z", "gh_status"] == "NO_FACTS"
        and out.loc["EQ:Z"].drop("gh_status").isna().all()
    )
    assert run([], ids=("EQ:Z",)).loc["EQ:Z", "gh_status"] == "NO_FACTS"
    stale = run(history() + history("eps_diluted"), session=LAST_END + timedelta(days=500))
    assert stale.loc["EQ:A", "gh_status"] == "STALE"
    assert stale.loc["EQ:A", "revenue_ttm_3y_ago"] == 42.0  # shown, not hidden


def test_revenue_and_eps_ending_on_different_periods_are_partial() -> None:
    eps = [quarter(n, 1.0, "eps_diluted") for n in range(QUARTERS - 1)]  # one quarter behind
    row = run(history() + eps).loc["EQ:A"]
    assert row["gh_status"] == "PARTIAL"
    assert row["revenue_ttm_3y_ago"] == 42.0 and row["eps_diluted_ttm_3y_ago"] == 4.0


def test_params_keep_a_window_that_reaches_five_years_back() -> None:
    assert P.history_days == 2500 and P.history_days > 5 * 365 + gh.TtmParams().stale_days
    with pytest.raises(ValueError, match="history_days"):
        gh.GrowthParams(history_days=500)
    assert [f.name for f in gh.FEATURES][-1] == "gh_status"
