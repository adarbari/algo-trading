"""Properties of the vendor order (ADR 0080): ``choose_vendor`` takes the first vendor of the
order whose status is OK or STALE, else the next with a row or a marker that is not FAILED, else the
first, whatever the rows; and the ratings' Yahoo change (0m less -3m) is read from one snapshot,
so it never depends on another vendor's rows or an older fetch. (``tests/property`` is at its
module cap; these live beside the group they check.)"""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.features.rollups.consensus import analyst_ratings as ar
from algotrade.features.rollups.consensus.analyst_status import (
    FINNHUB,
    NOT_FETCHED,
    OK,
    STALE,
    TARGET,
    YAHOO,
    AnalystParams,
    choose_vendor,
    resolve,
    vendor_rows,
)
from tests.helpers.analyst.snapshots import marker, put, recommendation, store, target, visible

S = date(2026, 10, 22)
IDS = ("EQ:A", "EQ:B", "EQ:C", "EQ:D")
FMP = "fmp"
VENDORS = (FMP, FINNHUB, YAHOO)
# what a vendor holds for a name: nothing, a row, a coverage marker of some status, or both
HOLDS = st.sampled_from(("none", "row", "OK", "EMPTY", "NOT_COVERED", "FAILED", "row+OK"))


def seed(plan: dict[tuple[str, str], str]):
    writer = store()
    for vendor in VENDORS:
        rows = []
        for iid in IDS:
            held = plan.get((vendor, iid), "none")
            if held in ("row", "row+OK"):
                rows.append(target(iid, 10.0))
            if held in ("OK", "EMPTY", "NOT_COVERED", "FAILED"):
                rows.append(marker(iid, held))
            if held == "row+OK":
                rows.append(marker(iid, "OK"))
        if rows:
            put(writer, S, rows, source=vendor, run_id=vendor)
    return writer


plans = st.dictionaries(st.tuples(st.sampled_from(VENDORS), st.sampled_from(IDS)), HOLDS)
orders = st.sampled_from(((FMP, YAHOO), (FINNHUB, YAHOO), (YAHOO, FMP), (FMP, FINNHUB, YAHOO)))


@settings(max_examples=60, deadline=None)
@given(plan=plans, order=orders)
def test_the_chosen_vendor_is_the_first_answering_else_the_first_with_a_marker(plan, order) -> None:
    both = visible(seed(plan), S)
    ids = list(IDS)
    chosen = choose_vendor(both, ids, TARGET, S, AnalystParams(), order)
    status = {
        v: resolve(ids, vendor_rows(both, TARGET, v), both, S, AnalystParams(), v).set_index(
            "instrument_id"
        )["status"]
        for v in order
    }
    for iid in ids:
        answered = [v for v in order if status[v][iid] in (OK, STALE)]
        asked = [v for v in order[1:] if status[v][iid] != NOT_FETCHED]
        want = answered[0] if answered and answered[0] == order[0] else (asked or [order[0]])[0]
        assert chosen[iid] == want, (iid, order, plan)


@settings(max_examples=60, deadline=None)
@given(plan=plans)
def test_a_name_with_the_first_vendors_answer_never_reads_the_second(plan) -> None:
    both = visible(seed(plan), S)
    chosen = choose_vendor(both, list(IDS), TARGET, S, AnalystParams(), (FMP, YAHOO))
    for iid in IDS:
        if plan.get((FMP, iid)) in ("row", "row+OK"):
            assert chosen[iid] == FMP


COUNTS = st.tuples(*[st.integers(0, 12)] * 5)
MONTHS = ("2026-10-01", "2026-09-01", "2026-08-01", "2026-07-01")  # 0m, -1m, -2m, -3m


@settings(max_examples=60, deadline=None)
@given(
    yahoo_months=st.dictionaries(st.sampled_from(MONTHS), COUNTS, min_size=1),
    finnhub_counts=COUNTS,
    other_vendor=st.booleans(),
    older=st.booleans(),
)
def test_the_yahoo_change_is_the_0m_less_the_minus_3m_of_one_snapshot_whatever_else_is_stored(
    yahoo_months, finnhub_counts, other_vendor, older
) -> None:
    writer = store()
    put(writer, S, recommendation("EQ:A", yahoo_months), source=YAHOO, run_id="y")
    if older:  # an older Yahoo fetch listing every month: never mixed in
        put(
            writer,
            date(2026, 9, 20),
            recommendation("EQ:A", dict.fromkeys(MONTHS, (9, 0, 0, 0, 0))),
            source=YAHOO,
            run_id="o",
        )
    if other_vendor:  # another vendor's row for ANOTHER name must not change this one
        put(
            writer,
            S,
            recommendation("EQ:B", {MONTHS[0]: finnhub_counts}),
            source=FINNHUB,
            run_id="f",
        )
    inputs = {
        ar.SNAPSHOTS: visible(writer, S),
        ar.UNIVERSE: pd.DataFrame({"instrument_id": ["EQ:A"], "asset_class": ["STOCK"]}),
    }
    row = ar.compute(inputs, S, ar.RatingsParams()).set_index("instrument_id").loc["EQ:A"]

    def score(counts):
        total = sum(counts)
        return (
            None
            if total == 0
            else sum(c * w for c, w in zip(counts, (5, 4, 3, 2, 1), strict=True)) / total
        )

    now, back = yahoo_months.get(MONTHS[0]), yahoo_months.get(MONTHS[3])
    # the newest month listed is the row; the change needs exactly 0m and -3m
    newest = yahoo_months[max(yahoo_months)]
    assert row["ratings_source"] == YAHOO
    if score(newest) is None:
        assert pd.isna(row["rating_score"])
    else:
        assert row["rating_score"] == pytest.approx(score(newest))
    want = None
    if now is not None and back is not None and score(now) is not None and score(back) is not None:
        want = score(now) - score(back)
    if want is None:
        assert pd.isna(row["rating_score_change_90d"])
    else:
        assert row["rating_score_change_90d"] == pytest.approx(want)
