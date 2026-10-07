"""``financials@v2``: discrete quarters from year-to-date facts (the fourth quarter as annual
minus nine months), four-quarter and annual TTMs, the year-ago TTMs, the latest quarter and
the same quarter a year earlier, restatements and filing dates (point in time), split-adjusted
EPS, the statuses (OK / PARTIAL / NO_TTM / NO_FACTS / STALE), the ``pe_ratio`` /
``revenue_growth_yoy`` expression features, and that every v1 column is unchanged."""

from calendar import monthrange
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.fields import field_source
from algotrade.features.framework.runner import compute_in_memory
from algotrade.features.registry import catalogue_columns
from algotrade.features.rollups.corporate.financials import (
    GROUP,
    TAG_RANK,
    FinancialsParams,
    annual,
    discrete_quarters,
    latest_quarter,
    months,
    split_adjusted,
    trailing,
)
from algotrade.features.rollups.price import price_stats
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, series, store, write_bars, write_split
from tests.helpers.stored_frames import stamped

STORED = END + timedelta(days=1)  # a backfill stored after every session it serves
EPOCH = date(1970, 1, 1)
UNITS = {"revenue": "usd", "net_income": "usd", "eps_diluted": "usd_per_share"}
TAGS = {
    "revenue": "us-gaap:Revenues",
    "net_income": "us-gaap:NetIncomeLoss",
    "eps_diluted": "us-gaap:EarningsPerShareDiluted",
}
CONTRACT = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def day(d: date) -> int:
    return (d - EPOCH).days


def period_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def fact(iid, concept, start, end, value, filed, form="10-Q", tag=None):  # type: ignore[no-untyped-def]
    return {
        "instrument_id": iid, "symbol": iid[3:], "cik": "0000000001", "concept": concept,
        "period_start": start, "period_end": end, "filed": filed, "form": form,
        "accn": f"{iid}-{concept}-{start}-{end}-{filed}", "value": float(value),
        "unit": UNITS[concept], "tag": tag or TAGS[concept], "fetched_on": STORED,
    }  # fmt: skip


def ytd(iid, concept, year, month, value, filed, quarter=False):  # type: ignore[no-untyped-def]
    """A calendar-year company's year-to-date fact (or just the quarter with ``quarter``)."""
    first = month - 2 if quarter else 1
    form = "10-K" if month == 12 else "10-Q"
    return fact(iid, concept, date(year, first, 1), period_end(year, month), value, filed, form)


def company_a(iid: str = "EQ:A", concept: str = "revenue", scale: float = 1.0):  # type: ignore[no-untyped-def]
    """Quarters 2024: 90 100 110 120; 2025: 100 115 130 135; 2026: 130 140 (scaled)."""
    cumulative = [
        (2024, 3, 90, date(2024, 5, 3)), (2024, 6, 190, date(2024, 8, 2)),
        (2024, 9, 300, date(2024, 11, 1)), (2024, 12, 420, date(2025, 2, 14)),
        (2025, 3, 100, date(2025, 5, 2)), (2025, 6, 215, date(2025, 8, 1)),
        (2025, 9, 345, date(2025, 10, 31)), (2025, 12, 480, date(2026, 2, 13)),
        (2026, 3, 130, date(2026, 5, 5)), (2026, 6, 270, date(2026, 8, 4)),
    ]  # fmt: skip
    rows = [ytd(iid, concept, y, m, v * scale, f) for y, m, v, f in cumulative]
    return [*rows, ytd(iid, concept, 2026, 6, 140 * scale, date(2026, 8, 4), quarter=True)]


def fy(iid, concept, year, value):  # type: ignore[no-untyped-def]
    """A calendar fiscal year's annual fact, filed on 1 March of the next year."""
    return fact(
        iid, concept, date(year, 1, 1), date(year, 12, 31), value, date(year + 1, 3, 1), "10-K"
    )


def facts_of(rows: list[dict[str, object]]) -> list[tuple[int, int, float, int, int]]:
    return [
        (
            day(r["period_start"]),  # type: ignore[arg-type]
            day(r["period_end"]),  # type: ignore[arg-type]
            r["value"],  # type: ignore[arg-type]
            day(r["filed"]),  # type: ignore[arg-type]
            TAG_RANK.get(str(r["tag"]), len(TAG_RANK)),
        )
        for r in rows
    ]


def test_months_by_span() -> None:
    assert [months(0, n) for n in (60, 89, 97, 177, 272, 363, 371, 500)] == [
        0,
        3,
        3,
        6,
        9,
        12,
        12,
        0,
    ]


def test_discrete_quarters_difference_year_to_date_periods_and_prefer_reported_ones() -> None:
    quarters = discrete_quarters(facts_of(company_a()))
    assert [q[1] for q in quarters] == [90, 100, 110, 120, 100, 115, 130, 135, 130, 140]
    assert quarters[-1][0] == day(date(2026, 6, 30)) and quarters[-1][2] == day(date(2026, 8, 4))
    assert quarters[3][2] == day(date(2025, 2, 14))  # Q4 2024 is public when the 10-K is filed


def test_trailing_is_the_last_four_quarters_with_a_year_ago() -> None:
    (total, ago) = trailing(facts_of(company_a())) or (None, None)
    assert total == (535, day(date(2026, 6, 30)), day(date(2026, 8, 4)), False)
    assert ago == 445  # 110 + 120 + 100 + 115
    facts = facts_of(company_a())
    through_q4 = [f for f in facts if f[3] <= day(date(2026, 3, 1))]  # the 10-K is the latest
    (total, ago) = trailing(through_q4) or (None, None)
    assert total == (480, day(date(2025, 12, 31)), day(date(2026, 2, 13)), False)  # = the year
    assert ago == 420


def test_trailing_falls_back_to_the_latest_fiscal_year() -> None:
    rows = [
        fy("EQ:B", "revenue", 2024, 1000),
        fy("EQ:B", "revenue", 2025, 1200),
    ]  # fmt: skip
    (total, ago) = trailing(facts_of(rows)) or (None, None)
    assert total == (1200, day(date(2025, 12, 31)), day(date(2026, 3, 1)), True) and ago == 1000
    assert [x[2] for x in annual(facts_of(rows))] == [1000, 1200]
    assert trailing([]) is None
    only_q1 = facts_of([ytd("EQ:E", "revenue", 2026, 3, 5, date(2026, 5, 5))])
    assert trailing(only_q1) is None  # one quarter, no year


def test_a_broken_quarter_chain_uses_the_latest_fiscal_year() -> None:
    facts = facts_of(company_a())
    gap = [f for f in facts if f[1] != day(date(2025, 9, 30))]  # no nine months: no Q3, no Q4
    (total, _) = trailing(gap) or (None, None)
    assert total == (480, day(date(2025, 12, 31)), day(date(2026, 2, 13)), True)


def _cum(iid, tag, year, rows):  # type: ignore[no-untyped-def]
    """Year-to-date revenue facts of a calendar year: (month, value, filed) under one tag."""
    return [ytd(iid, "revenue", year, m, v, f, quarter=q) | {"tag": tag} for m, v, f, q in rows]


def test_year_ago_ttm_must_end_a_year_before_the_ttm() -> None:
    """Quarters 2023-03..12, then 2024-06..12 (2024 Q1 not derivable) and 2025-03: the last
    four quarters are consecutive, but the four before them have a hole, so there is no
    year-ago TTM (it used to be the TTM to 2023-12, almost two years back)."""
    rows = [
        *_cum("EQ:G", TAGS["revenue"], 2023, [
            (3, 100, date(2023, 5, 1), True), (6, 100, date(2023, 8, 1), True),
            (9, 100, date(2023, 11, 1), True), (9, 300, date(2023, 11, 1), False),
            (12, 400, date(2024, 2, 15), False),
        ]),
        *_cum("EQ:G", TAGS["revenue"], 2024, [
            (6, 110, date(2024, 8, 1), True), (9, 110, date(2024, 11, 1), True),
            (9, 330, date(2024, 11, 1), False), (12, 440, date(2025, 2, 15), False),
        ]),
        *_cum("EQ:G", TAGS["revenue"], 2025, [(3, 120, date(2025, 5, 1), True)]),
    ]  # fmt: skip
    (total, ago) = trailing(facts_of(rows), True) or (None, None)
    assert total == (450, day(date(2025, 3, 31)), day(date(2025, 5, 1)), False)  # 110 x 3 + 120
    assert ago is None


def test_a_quarter_is_never_derived_across_tags() -> None:
    """Annual revenue under Revenues (600), quarters and nine months under the contract tag
    (100 a quarter, 300): the fourth quarter is not 300, it is unknown."""
    q = lambda m, v, f, qq: (m, v, f, qq)  # noqa: E731
    contract = [
        q(3, 100, date(2025, 5, 1), True), q(6, 100, date(2025, 8, 1), True),
        q(9, 100, date(2025, 11, 1), True), q(9, 300, date(2025, 11, 1), False),
    ]  # fmt: skip
    annual_other_tag = _cum("EQ:H", TAGS["revenue"], 2025, [(12, 600, date(2026, 2, 15), False)])
    rows = [*_cum("EQ:H", CONTRACT, 2025, contract), *annual_other_tag]
    quarters = discrete_quarters(facts_of(rows), True)
    assert [x[0] for x in quarters] == [day(date(2025, m, 30 + (m in (3, 12)))) for m in (3, 6, 9)]
    assert 300 not in [x[1] for x in quarters]
    same_tag = _cum("EQ:H", CONTRACT, 2025, [(12, 400, date(2026, 2, 15), False)])
    derived = discrete_quarters(
        facts_of([*_cum("EQ:H", CONTRACT, 2025, contract), *same_tag]), True
    )
    assert [x[1] for x in derived] == [100, 100, 100, 100]  # 400 - 300 under one tag


def test_the_better_tag_wins_a_reported_quarter() -> None:
    both = [
        *_cum("EQ:H", CONTRACT, 2025, [(3, 90, date(2025, 5, 1), True)]),
        *_cum("EQ:H", TAGS["revenue"], 2025, [(3, 100, date(2025, 5, 1), True)]),
    ]
    assert [x[1] for x in discrete_quarters(facts_of(both))] == [100]


def test_year_to_date_facts_of_different_restatement_generations_are_not_subtracted() -> None:
    """The next 10-K restates the prior year's annual figure (discontinued operations) while
    that year's nine months stay as first filed: 250 - 300 is not a quarter."""
    nine = _cum("EQ:R", TAGS["revenue"], 2024, [(9, 300, date(2024, 11, 1), False)])
    restated = _cum("EQ:R", TAGS["revenue"], 2024, [(12, 250, date(2026, 2, 15), False)])
    assert discrete_quarters(facts_of([*nine, *restated]), True) == []
    close = _cum("EQ:R", TAGS["revenue"], 2024, [(12, 250, date(2025, 2, 15), False)])
    assert discrete_quarters(facts_of([*nine, *close]), True) == []  # negative revenue: dropped
    negative_ok = discrete_quarters(facts_of([*nine, *close]), False)  # net income may fall
    assert [x[1] for x in negative_ok] == [-50]


def _setup() -> tuple[object, list[date]]:
    writer, reader = store()
    names = ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:E", "EQ:S", "EQ:LOSS", "EQ:ETF", "EQ:ADR", "EQ:M"]
    closes = {iid: series(100, n, start=40.0) for n, iid in enumerate(names)}
    days = write_bars(writer, closes)
    rows = [
        *company_a("EQ:A", "revenue"),
        *company_a("EQ:A", "net_income", 0.1),  # a tenth of the revenue
        *company_a("EQ:A", "eps_diluted", 0.01),  # a hundredth: TTM 5.35
        # B reports only annually
        fy("EQ:B", "revenue", 2024, 1000),
        fy("EQ:B", "revenue", 2025, 1200),
        fy("EQ:B", "net_income", 2025, 120),
        fy("EQ:B", "eps_diluted", 2025, 1.2),
        # C has revenue only
        fy("EQ:C", "revenue", 2025, 50),
        # D stopped filing long ago
        fy("EQ:D", "revenue", 2024, 70),
        fy("EQ:D", "net_income", 2024, 7),
        fy("EQ:D", "eps_diluted", 2024, 0.7),
        # E has one quarter and no year
        ytd("EQ:E", "revenue", 2026, 3, 5, date(2026, 5, 5)),
        # S: twice the EPS of A (TTM 10.7), a 2:1 split on 2026-08-20 after every filing
        *company_a("EQ:S", "eps_diluted", 0.02),
        # ADR: the same figures as A, per ordinary share
        *company_a("EQ:ADR", "revenue"),
        *company_a("EQ:ADR", "eps_diluted", 0.01),
        # M: revenue only annual and old, EPS current
        fy("EQ:M", "revenue", 2024, 80),
        *company_a("EQ:M", "eps_diluted", 0.01),
        # LOSS: negative EPS and net income
        *company_a("EQ:LOSS", "eps_diluted", -0.01),
        *company_a("EQ:LOSS", "net_income", -0.1),
    ]  # fmt: skip
    writer.write_table("instruments/shares", STORED, "facts", stamped(rows, STORED, "facts"))
    write_split(writer, "EQ:S", date(2026, 8, 20), 2.0, END)
    reference = [
        {"instrument_id": iid, "symbol": iid[3:], "asset_class": "equity", "multiplier": 1.0,
         "security_type": "ADR" if iid == "EQ:ADR" else "COMMON_STOCK", "status": "ACTIVE"}
        for iid in names
    ]  # fmt: skip
    writer.write_table("instruments/reference", END, "ref", stamped(reference, END, "ref"))
    return reader, days


def _rows(reader: object, sessions: list[date], params: FinancialsParams | None = None):  # type: ignore[no-untyped-def]
    by_key = {GROUP.key: params} if params else None
    out = compute_in_memory(reader, [price_stats.GROUP, GROUP], sessions, by_key)  # type: ignore[arg-type]
    return {r.session: r.frame.set_index("instrument_id") for r in out[GROUP.key]}


def test_ttm_values_and_dates_on_the_latest_session() -> None:
    reader, _ = _setup()
    a = _rows(reader, [END])[END].loc["EQ:A"]
    assert (a["revenue_ttm"], a["revenue_ttm_year_ago"]) == (535, 445)
    assert (a["net_income_ttm"], a["eps_diluted_ttm"]) == (pytest.approx(53.5), pytest.approx(5.35))
    assert (a["revenue_fy"], a["revenue_fy_end"]) == (480, date(2025, 12, 31))
    assert (a["ttm_as_of"], a["ttm_filed"]) == (date(2026, 6, 30), date(2026, 8, 4))
    assert (a["ttm_basis"], a["financials_status"]) == ("QUARTERS", "OK")
    b = _rows(reader, [END])[END].loc["EQ:B"]
    assert (b["revenue_ttm"], b["revenue_ttm_year_ago"], b["ttm_basis"]) == (1200, 1000, "ANNUAL")
    assert (b["revenue_fy"], b["financials_status"]) == (1200, "OK")


def test_point_in_time_by_filing_date() -> None:
    reader, days = _setup()
    before = date(2026, 7, 20)  # Q2 2026 is filed on 2026-08-04
    assert before in days
    a = _rows(reader, [before])[before].loc["EQ:A"]
    assert (a["revenue_ttm"], a["revenue_ttm_year_ago"]) == (510, 430)
    assert (a["ttm_as_of"], a["ttm_filed"]) == (date(2026, 3, 31), date(2026, 5, 5))
    assert a["revenue_fy"] == 480
    b = _rows(reader, [before])[before].loc["EQ:B"]
    assert b["revenue_ttm"] == 1200  # filed 2026-03-01


def test_a_restated_value_counts_from_its_filing_date() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(100, 0)})
    amended = ytd("EQ:A", "revenue", 2026, 3, 150, date(2026, 9, 1), "10-Q/A")
    rows = [*company_a("EQ:A", "revenue"), amended]
    writer.write_table("instruments/shares", STORED, "facts", stamped(rows, STORED, "facts"))
    early, late = date(2026, 8, 20), END
    assert {early, late} <= set(days)
    out = _rows(reader, [early, late])
    assert out[early].loc["EQ:A", "revenue_ttm"] == 535
    assert out[late].loc["EQ:A", "revenue_ttm"] == 555  # Q1 2026 restated 130 -> 150


def test_statuses_and_missing_facts_are_null_not_errors() -> None:
    reader, _ = _setup()
    rows = _rows(reader, [END])[END]
    assert rows.loc["EQ:C", "financials_status"] == "PARTIAL"
    assert rows.loc["EQ:C", "revenue_ttm"] == 50 and pd.isna(rows.loc["EQ:C", "eps_diluted_ttm"])
    d = rows.loc["EQ:D"]
    assert d["financials_status"] == "STALE" and d["revenue_ttm"] == 70  # still shown
    assert d["eps_stale"]
    m = rows.loc["EQ:M"]  # stale annual revenue, current quarterly EPS: the EPS is not stale
    assert (m["financials_status"], m["ttm_basis"], bool(m["eps_stale"])) == (
        "STALE",
        "ANNUAL",
        False,
    )
    assert not rows.loc["EQ:A", "eps_stale"] and pd.isna(rows.loc["EQ:C", "eps_stale"])
    e = rows.loc["EQ:E"]
    assert e["financials_status"] == "NO_TTM" and pd.isna(e["revenue_ttm"])
    assert pd.isna(e["ttm_basis"]) and pd.isna(e["ttm_as_of"])
    etf = rows.loc["EQ:ETF"]
    assert etf["financials_status"] == "NO_FACTS"
    assert etf[["revenue_ttm", "net_income_ttm", "eps_diluted_ttm", "revenue_fy"]].isna().all()
    loose = _rows(reader, [END], FinancialsParams(stale_days=900))[END]
    assert loose.loc["EQ:D", "financials_status"] == "OK"


def test_eps_is_split_adjusted_by_filing_date() -> None:
    reader, days = _setup()
    before = date(2026, 8, 10)
    assert before in days
    out = _rows(reader, [before, END])
    assert out[before].loc["EQ:S", "eps_diluted_ttm"] == pytest.approx(10.7)  # the split is ahead
    assert out[END].loc["EQ:S", "eps_diluted_ttm"] == pytest.approx(5.35)  # 10.7 / 2
    assert out[END].loc["EQ:A", "eps_diluted_ttm"] == pytest.approx(5.35)  # no split


def test_split_adjusted_divides_only_facts_filed_before_the_split() -> None:
    facts = pd.DataFrame(
        {
            "instrument_id": ["EQ:S", "EQ:S", "EQ:T"],
            "filed": [day(date(2026, 1, 1)), day(date(2026, 9, 1)), day(date(2026, 1, 1))],
            "value": [8.0, 3.0, 5.0],
        }
    )
    splits = pd.DataFrame(
        {
            "instrument_id": ["EQ:S", "EQ:S", "EQ:S"],
            "event_date": [date(2026, 8, 20), date(2026, 8, 25), date(2026, 10, 20)],
            "ratio": [2.0, 3.0, 5.0],
        }
    )
    got = split_adjusted(facts, splits, END)  # the 2026-10-20 split is after the session
    assert got.tolist() == [8.0 / 6, 3.0, 5.0]
    assert split_adjusted(facts, None, END).tolist() == [8.0, 3.0, 5.0]


def _expressions(rows: pd.DataFrame, close: float = 100.0) -> pd.DataFrame:
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    stats = pd.DataFrame(
        {"instrument_id": rows["instrument_id"], "session_date": END, "close": close}
    )
    rows = rows.assign(session_date=END)
    for flag in ("eps_stale", "is_adr"):
        if flag not in rows.columns:
            rows[flag] = False
    frames = {price_stats.GROUP.table: stats, GROUP.table: rows}
    return fs.evaluate(frames, ["pe_ratio", "revenue_growth_yoy"]).set_index("instrument_id")


def test_pe_ratio_and_revenue_growth_expression_features() -> None:
    rows = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:LOSS", "EQ:ZERO", "EQ:OLD", "EQ:ETF", "EQ:ADR", "EQ:M"],
            "eps_diluted_ttm": [4.0, -2.0, 0.0, 5.0, None, 4.0, 4.0],
            "eps_stale": [False, False, False, True, None, False, False],
            "is_adr": [False, False, False, False, False, True, False],
            "financials_status": ["OK", "OK", "OK", "STALE", "NO_FACTS", "OK", "STALE"],
            "revenue_ttm": [535.0, 10.0, 10.0, 10.0, None, 535.0, 10.0],
            "revenue_ttm_year_ago": [445.0, 20.0, 0.0, None, None, 445.0, None],
        }
    )
    out = _expressions(rows)
    assert out.loc["EQ:A", "pe_ratio"] == pytest.approx(25.0)
    assert out.loc["EQ:A", "revenue_growth_yoy"] == pytest.approx(535 / 445 - 1)
    for loss in ("EQ:LOSS", "EQ:ZERO", "EQ:OLD", "EQ:ETF", "EQ:ADR"):  # no loss, stale or ADR P/E
        assert pd.isna(out.loc[loss, "pe_ratio"]), loss
    assert out.loc["EQ:M", "pe_ratio"] == pytest.approx(25.0)  # stale revenue, current EPS
    assert out.loc["EQ:LOSS", "revenue_growth_yoy"] == pytest.approx(-0.5)
    assert pd.isna(out.loc["EQ:ZERO", "revenue_growth_yoy"])  # zero base
    assert pd.isna(out.loc["EQ:OLD", "revenue_growth_yoy"])  # no year-ago


def test_pe_ratio_end_to_end_on_stored_facts() -> None:
    reader, _ = _setup()
    rows = _rows(reader, [END])[END]
    close = float(price_stats_close(reader, "EQ:A"))
    out = _expressions(rows.reset_index(), close)
    assert out.loc["EQ:A", "pe_ratio"] == pytest.approx(close / 5.35)
    assert out.loc["EQ:S", "pe_ratio"] == pytest.approx(close / 5.35)
    assert pd.isna(out.loc["EQ:LOSS", "pe_ratio"]) and pd.isna(out.loc["EQ:ETF", "pe_ratio"])
    assert rows.loc["EQ:ADR", "is_adr"] and not rows.loc["EQ:A", "is_adr"]
    assert pd.isna(out.loc["EQ:ADR", "pe_ratio"])  # same EPS as A, but per ordinary share
    assert out.loc["EQ:M", "pe_ratio"] == pytest.approx(close / 5.35)


def price_stats_close(reader: object, iid: str) -> float:
    out = compute_in_memory(reader, [price_stats.GROUP], [END])  # type: ignore[arg-type]
    return float(out[price_stats.GROUP.key][0].frame.set_index("instrument_id").loc[iid, "close"])


def test_params_validate_and_catalogue_fields() -> None:
    with pytest.raises(ValueError, match="stale_days"):
        replace(FinancialsParams(), stale_days=0)
    with pytest.raises(ValueError, match="history_days"):
        replace(FinancialsParams(), history_days=300)
    columns = catalogue_columns()["financials@v2"]
    assert columns["revenue_ttm"] == "float" and columns["eps_diluted_ttm"] == "float32"
    assert columns["financials_status"] == "str" and columns["revenue_fy_end"] == "date"
    assert field_source("rollup.financials@v2.net_income_ttm") == (
        "rollups/instrument/financials@v2",
        "net_income_ttm",
    )


# What financials@v1 computed for the facts of ``_setup`` (recorded from the v1 module before it
# was replaced; dates as ISO strings): every v2 column that existed in v1 stays identical.
V1_COLUMNS = (
    "revenue_ttm", "revenue_ttm_year_ago", "net_income_ttm", "eps_diluted_ttm", "revenue_fy",
    "revenue_fy_end", "ttm_as_of", "ttm_filed", "ttm_basis", "eps_stale", "is_adr",
    "financials_status",
)  # fmt: skip
# fmt: off
V1_END = {
    "EQ:A": (535.0, 445.0, 53.5, 5.349999904632568, 480.0, "2025-12-31", "2026-06-30",
             "2026-08-04", "QUARTERS", False, False, "OK"),
    "EQ:ADR": (535.0, 445.0, None, 5.349999904632568, 480.0, "2025-12-31", "2026-06-30",
               "2026-08-04", "QUARTERS", False, True, "PARTIAL"),
    "EQ:B": (1200.0, 1000.0, 120.0, 1.2000000476837158, 1200.0, "2025-12-31", "2025-12-31",
             "2026-03-01", "ANNUAL", False, False, "OK"),
    "EQ:C": (50.0, None, None, None, 50.0, "2025-12-31", "2025-12-31", "2026-03-01", "ANNUAL",
             None, False, "PARTIAL"),
    "EQ:D": (70.0, None, 7.0, 0.699999988079071, 70.0, "2024-12-31", "2024-12-31", "2025-03-01",
             "ANNUAL", True, False, "STALE"),
    "EQ:E": (None, None, None, None, None, None, None, None, None, None, False, "NO_TTM"),
    "EQ:ETF": (None, None, None, None, None, None, None, None, None, None, False, "NO_FACTS"),
    "EQ:LOSS": (None, None, -53.5, -5.349999904632568, None, None, "2026-06-30", "2026-08-04",
                "QUARTERS", False, False, "PARTIAL"),
    "EQ:M": (80.0, None, None, 5.349999904632568, 80.0, "2024-12-31", "2024-12-31", "2025-03-01",
             "ANNUAL", False, False, "STALE"),
    "EQ:S": (None, None, None, 5.349999904632568, None, None, "2026-06-30", "2026-08-04",
             "QUARTERS", False, False, "PARTIAL"),
}

V1_JULY = {
    "EQ:A": (510.0, 430.0, 51.0, 5.099999904632568, 480.0, "2025-12-31", "2026-03-31",
             "2026-05-05", "QUARTERS", False, False, "OK"),
    "EQ:B": (1200.0, 1000.0, 120.0, 1.2000000476837158, 1200.0, "2025-12-31", "2025-12-31",
             "2026-03-01", "ANNUAL", False, False, "OK"),
}

# fmt: on


def _recorded(rows: pd.DataFrame, columns: tuple[str, ...]) -> dict[str, tuple[object, ...]]:
    """The rows' columns as plain values: nulls None, dates ISO strings, flags bool."""

    def plain(value: object) -> object:
        if value is None or (not isinstance(value, str | bool | date) and pd.isna(value)):
            return None
        if isinstance(value, date):
            return value.isoformat()
        return bool(value) if isinstance(value, bool | np.bool_) else value

    return {iid: tuple(plain(row[c]) for c in columns) for iid, row in rows.iterrows()}


def test_every_v1_column_is_unchanged() -> None:
    reader, _ = _setup()
    out = _rows(reader, [date(2026, 7, 20), END])
    assert _recorded(out[END], V1_COLUMNS) == V1_END
    assert _recorded(out[date(2026, 7, 20)].loc[["EQ:A", "EQ:B"]], V1_COLUMNS) == V1_JULY


def test_latest_quarter_with_the_same_quarter_a_year_earlier() -> None:
    facts = facts_of(company_a())
    assert latest_quarter(facts) == ((day(date(2026, 6, 30)), 140, day(date(2026, 8, 4))), 115)
    before_q2 = [f for f in facts if f[3] < day(date(2026, 8, 4))]  # a filing date, not a period
    assert latest_quarter(before_q2) == ((day(date(2026, 3, 31)), 130, day(date(2026, 5, 5))), 100)
    assert latest_quarter([]) is None


def test_the_fourth_quarter_of_a_10k_is_the_year_minus_the_nine_months() -> None:
    facts = facts_of(company_a())
    through_10k = [f for f in facts if f[3] <= day(date(2026, 3, 1))]
    last, ago = latest_quarter(through_10k) or (None, None)
    assert last == (day(date(2025, 12, 31)), 135, day(date(2026, 2, 13)))  # 480 - 345
    assert ago == 120  # 2024's fourth quarter: 420 - 300
    before_10k = [f for f in facts if f[3] < day(date(2026, 2, 13))]  # Q3 is the latest public
    last, ago = latest_quarter(before_10k) or (None, None)
    assert (last[1], ago) == (130, 110)  # type: ignore[index]


def test_no_fourth_quarter_without_the_nine_months_is_no_quarter() -> None:
    """The annual figure is newer than the newest quarter and cannot be split: the quarter
    columns are null rather than an older quarter shown as the latest."""
    facts = facts_of(company_a())
    no_nine_months = [f for f in facts if f[3] <= day(date(2026, 3, 1))]
    no_nine_months = [f for f in no_nine_months if f[1] != day(date(2025, 9, 30))]
    assert latest_quarter(no_nine_months) is None
    annual_only = facts_of([fy("EQ:B", "revenue", 2024, 1000), fy("EQ:B", "revenue", 2025, 1200)])
    assert latest_quarter(annual_only) is None


def test_quarter_and_year_ago_columns_on_stored_facts() -> None:
    reader, _ = _setup()
    out = _rows(reader, [date(2026, 7, 20), END])
    a = out[END].loc["EQ:A"]
    assert (a["revenue_qtr"], a["revenue_qtr_year_ago"]) == (140, 115)
    assert (a["eps_diluted_qtr"], a["eps_diluted_qtr_year_ago"]) == (
        pytest.approx(1.4),
        pytest.approx(1.15),
    )
    assert a["eps_diluted_ttm_year_ago"] == pytest.approx(4.45)  # 1.10 + 1.20 + 1.00 + 1.15
    assert a["qtr_as_of"] == date(2026, 6, 30)
    early = out[date(2026, 7, 20)].loc["EQ:A"]  # Q2 2026 is filed on 2026-08-04
    assert (early["revenue_qtr"], early["revenue_qtr_year_ago"]) == (130, 100)
    assert early["eps_diluted_ttm_year_ago"] == pytest.approx(4.30) and early["qtr_as_of"] == date(
        2026, 3, 31
    )
    annual_filer = out[END].loc["EQ:B"]  # no quarters; EPS has one fiscal year: no year ago
    assert pd.isna(annual_filer["qtr_as_of"]) and pd.isna(annual_filer["revenue_qtr"])
    assert pd.isna(annual_filer["eps_diluted_ttm_year_ago"])
    assert out[END].loc["EQ:B", "revenue_ttm_year_ago"] == 1000
    only_q1 = out[END].loc["EQ:E"]  # a quarter without a year-ago quarter or a TTM
    assert (only_q1["revenue_qtr"], only_q1["qtr_as_of"]) == (5, date(2026, 3, 31))
    assert pd.isna(only_q1["revenue_qtr_year_ago"]) and only_q1["financials_status"] == "NO_TTM"
    revenue_only = out[END].loc["EQ:C"]
    assert pd.isna(revenue_only["qtr_as_of"]) and pd.isna(revenue_only["eps_diluted_qtr"])
    loss = out[END].loc["EQ:LOSS"]  # losses are kept; the growth expressions null them
    assert (loss["eps_diluted_qtr"], loss["eps_diluted_qtr_year_ago"]) == (
        pytest.approx(-1.4),
        pytest.approx(-1.15),
    )
    assert pd.isna(loss["revenue_qtr"])


def test_quarter_eps_is_split_adjusted_by_filing_date() -> None:
    reader, _ = _setup()
    before = date(2026, 8, 10)  # the 2:1 split of 2026-08-20 is ahead
    out = _rows(reader, [before, END])
    ahead, after = out[before].loc["EQ:S"], out[END].loc["EQ:S"]
    assert (ahead["eps_diluted_qtr"], ahead["eps_diluted_qtr_year_ago"]) == (
        pytest.approx(2.8),
        pytest.approx(2.3),
    )
    assert (after["eps_diluted_qtr"], after["eps_diluted_qtr_year_ago"]) == (
        pytest.approx(1.4),
        pytest.approx(1.15),
    )
    assert after["eps_diluted_ttm_year_ago"] == pytest.approx(4.45)  # 8.9 / 2
    assert pd.isna(after["revenue_qtr"])  # S has no revenue facts


def test_the_quarter_columns_describe_one_quarter() -> None:
    """Revenue is through Q2 2026, EPS only through Q1: qtr_as_of is Q2 and the EPS columns,
    of an older quarter, are null; and a quarter older than stale_days is null throughout
    while the TTMs stay shown."""
    writer, reader = store()
    write_bars(writer, {"EQ:X": series(100, 0), "EQ:OLD": series(100, 1)})
    q1_filed = date(2026, 5, 5)
    eps = [r for r in company_a("EQ:X", "eps_diluted", 0.01) if r["filed"] <= q1_filed]
    old = [r for r in company_a("EQ:OLD") if r["filed"] <= date(2025, 3, 1)]
    rows = [*company_a("EQ:X", "revenue"), *eps, *old]
    writer.write_table("instruments/shares", STORED, "facts", stamped(rows, STORED, "facts"))
    x = _rows(reader, [END])[END].loc["EQ:X"]
    assert (x["qtr_as_of"], x["revenue_qtr"]) == (date(2026, 6, 30), 140)
    assert pd.isna(x["eps_diluted_qtr"]) and pd.isna(x["eps_diluted_qtr_year_ago"])
    stale = _rows(reader, [END])[END].loc["EQ:OLD"]  # newest quarter: 2024-12-31
    assert stale["revenue_ttm"] == 420 and stale["financials_status"] == "STALE"
    assert pd.isna(stale["qtr_as_of"]) and pd.isna(stale["revenue_qtr"])
    loose = _rows(reader, [END], FinancialsParams(stale_days=900))[END].loc["EQ:OLD"]
    assert (loose["revenue_qtr"], loose["qtr_as_of"]) == (120, date(2024, 12, 31))
    assert pd.isna(loose["revenue_qtr_year_ago"])  # no 2023 facts


def test_growth_expressions_end_to_end_on_stored_facts() -> None:
    reader, _ = _setup()
    rows = _rows(reader, [END])[END].reset_index()
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    stats = pd.DataFrame(
        {"instrument_id": rows["instrument_id"], "session_date": END, "close": 1.0}
    )
    frames = {price_stats.GROUP.table: stats, GROUP.table: rows.assign(session_date=END)}
    names = ["eps_growth_yoy", "revenue_growth_qtr_yoy", "eps_growth_qtr_yoy"]
    out = fs.evaluate(frames, names).set_index("instrument_id")
    assert out.loc["EQ:A", "eps_growth_yoy"] == pytest.approx(5.35 / 4.45 - 1)
    assert out.loc["EQ:A", "revenue_growth_qtr_yoy"] == pytest.approx(140 / 115 - 1)
    assert out.loc["EQ:A", "eps_growth_qtr_yoy"] == pytest.approx(1.4 / 1.15 - 1)
    for loss in ("EQ:LOSS", "EQ:B", "EQ:ETF"):  # a loss base, no year-ago, no facts
        assert pd.isna(out.loc[loss, "eps_growth_yoy"]), loss
        assert pd.isna(out.loc[loss, "eps_growth_qtr_yoy"]), loss


def test_no_facts_table_at_all_gives_no_facts_rows() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:ETF": series(100, 0)})
    assert _rows(reader, [END])[END].loc["EQ:ETF", "financials_status"] == "NO_FACTS"
