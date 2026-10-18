"""``dividend_months@v1``: the coming month's hits in the last 3 years, specials out, zero vs
unknown by history, nothing from after the session."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.corporate import dividend_months as dm
from algotrade.features.rollups.corporate.dividends import DIVIDENDS, PRICE_STATS

SESSION = date(2026, 10, 2)  # the coming month: November


def _divs(rows: list[tuple[str, date, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "event_date": [r[1] for r in rows],
            "distribution_type": [r[2] for r in rows],
        }
    )


def _compute(rows: list[tuple[str, date, str]], history: dict[str, int]) -> pd.DataFrame:
    stats = pd.DataFrame(
        {
            "instrument_id": list(history),
            "session_date": SESSION,
            "history_days": list(history.values()),
        }
    )
    out = dm.compute({PRICE_STATS: stats, DIVIDENDS: _divs(rows)}, SESSION, None)
    return out.set_index("instrument_id")


def test_coming_month_wraps_the_year() -> None:
    assert dm.coming_month(date(2026, 12, 31)) == (2027, 1)
    assert dm.coming_month(date(2026, 10, 2)) == (2026, 11)


def test_counts_the_years_with_an_ex_date_in_the_coming_month() -> None:
    rows = [
        ("EQ:A", date(2025, 11, 14), "recurring"),
        ("EQ:A", date(2024, 11, 15), "recurring"),
        ("EQ:A", date(2024, 11, 29), "recurring"),  # a second one in a year counts once
        ("EQ:A", date(2025, 8, 14), "recurring"),  # another month
        ("EQ:A", date(2022, 11, 14), "recurring"),  # four years back: outside the 3
        ("EQ:A", date(2026, 11, 14), "recurring"),  # a declared future ex-date: never history
        ("EQ:B", date(2023, 11, 10), "recurring"),
    ]
    out = _compute(rows, {"EQ:A": 252, "EQ:B": 252})
    assert out["div_month_hits_3y"].tolist() == [2, 1]
    assert out["expected_div_month_flag"].tolist() == [True, True]


def test_a_special_does_not_make_a_month_expected() -> None:
    out = _compute([("EQ:A", date(2025, 11, 14), "special")], {"EQ:A": 252})
    assert out["div_month_hits_3y"].tolist() == [0]  # a known non-payer of that month
    assert out["expected_div_month_flag"].tolist() == [False]


def test_a_new_name_with_no_hit_is_unknown_but_a_payer_is_known() -> None:
    out = _compute(
        [("EQ:P", date(2025, 11, 14), "recurring")], {"EQ:P": 50, "EQ:NEW": 50, "EQ:OLD": 252}
    )
    assert out.loc["EQ:P", "expected_div_month_flag"] is True or bool(
        out.loc["EQ:P", "expected_div_month_flag"]
    )
    assert pd.isna(out.loc["EQ:NEW", "expected_div_month_flag"])
    assert pd.isna(out.loc["EQ:NEW", "div_month_hits_3y"])
    assert out.loc["EQ:OLD", "div_month_hits_3y"] == 0


def test_december_session_looks_at_january() -> None:
    session = date(2026, 12, 15)
    stats = pd.DataFrame({"instrument_id": ["EQ:A"], "session_date": session, "history_days": 252})
    rows = _divs(
        [("EQ:A", date(2026, 1, 20), "recurring"), ("EQ:A", date(2025, 1, 20), "recurring")]
    )
    out = dm.compute({PRICE_STATS: stats, DIVIDENDS: rows}, session, None)
    assert out["div_month_hits_3y"].tolist() == [2]  # Januaries 2026 and 2025 before Jan 2027
