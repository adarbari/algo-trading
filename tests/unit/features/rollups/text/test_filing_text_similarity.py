"""``filing_text_similarity@v1``: the latest filing per instrument carried 150 days (the 10-K risk
factors 400), no row past the cap, the latest of two filings, the risk-factor status when the
filing compared but its Item 1A did not, and a chain through ``filing_text_change@v1``."""

from datetime import date, timedelta

import pandas as pd

from algotrade.features.framework.columns import conform
from algotrade.features.rollups.text import filing_text_similarity as fts

SESSION = date(2026, 10, 2)


def change(iid: str, known: date, form: str = "10-Q", acc: str = "A", status: str = "OK",
           cosine: float | None = 0.9, rf: float | None = None) -> dict[str, object]:  # fmt: skip
    k = form == "10-K"  # a 10-K is its own latest 10-K (ftc_k_*); a 10-Q has none
    return {"instrument_id": iid, "session_date": known, "ftc_accession": acc, "ftc_form": form,
            "ftc_known_from": known, "ftc_status": status, "ftc_cosine": cosine,
            "ftc_jaccard": 0.8, "ftc_k_accession": acc if k else None,
            "ftc_k_known_from": known if k else None, "ftc_k_status": status if k else None,
            "ftc_k_rf_cosine": rf if k else None,
            "ftc_k_rf_len_change": 0.1 if k and rf is not None else None}  # fmt: skip


def compute(*rows: dict[str, object]) -> pd.DataFrame:
    return fts.compute({fts.SOURCE: pd.DataFrame(list(rows))}, SESSION, None)


def test_the_latest_filing_is_carried_with_its_values() -> None:
    old = change("EQ:A", SESSION - timedelta(days=100), acc="OLD", cosine=0.5)
    new = change("EQ:A", SESSION - timedelta(days=20), acc="NEW", cosine=0.95)
    [row] = compute(old, new, old).to_dict("records")
    assert row["text_sim_cosine"] == 0.95 and row["text_sim_status"] == "OK"
    assert row["text_sim_known_from"] == SESSION - timedelta(days=20)
    assert row["text_sim_form"] == "10-Q" and pd.isna(row["risk_factor_sim_cosine"])


def test_the_carry_caps_are_150_days_and_400_for_the_10k_risk_factors() -> None:
    k = change("EQ:A", SESSION - timedelta(days=300), "10-K", rf=0.8)
    out = compute(k).set_index("instrument_id")
    assert pd.isna(out.at["EQ:A", "text_sim_cosine"])  # past 150 days
    assert (
        out.at["EQ:A", "risk_factor_sim_cosine"] == 0.8
        and out.at["EQ:A", "risk_factor_status"] == "OK"
    )
    assert compute(change("EQ:A", SESSION - timedelta(days=150))).at[0, "text_sim_cosine"] == 0.9
    assert compute(change("EQ:A", SESSION - timedelta(days=151))).empty  # a 10-Q: no row at all
    assert compute(change("EQ:A", SESSION - timedelta(days=400), "10-K", rf=0.8)).shape[0] == 1
    assert compute(change("EQ:A", SESSION - timedelta(days=401), "10-K", rf=0.8)).empty


def test_a_10q_does_not_replace_the_10k_risk_factor_value() -> None:
    k = change("EQ:A", SESSION - timedelta(days=60), "10-K", acc="K", rf=0.7)
    q = change("EQ:A", SESSION - timedelta(days=10), "10-Q", acc="Q")
    [row] = compute(k, q).to_dict("records")
    assert row["text_sim_form"] == "10-Q" and row["risk_factor_sim_cosine"] == 0.7


def test_a_10k_hidden_by_a_later_10q_in_the_window_still_gives_the_risk_factor_value() -> None:
    """The gap of #720 (review finding 3): both filings in one change row, the 10-Q the latest;
    the risk factors are the 10-K's, not last year's."""
    prior_year = change("EQ:A", SESSION - timedelta(days=370), "10-K", acc="K0", rf=0.5)
    both = change("EQ:A", SESSION - timedelta(days=3), "10-Q", acc="Q", cosine=0.9) | {
        "ftc_k_accession": "K1", "ftc_k_known_from": SESSION - timedelta(days=4),
        "ftc_k_status": "OK", "ftc_k_rf_cosine": 0.8, "ftc_k_rf_len_change": 0.3}  # fmt: skip
    [row] = compute(prior_year, both).to_dict("records")
    assert row["text_sim_form"] == "10-Q" and row["text_sim_cosine"] == 0.9
    assert row["risk_factor_sim_cosine"] == 0.8 and row["risk_factor_len_change"] == 0.3


def test_a_10k_known_after_the_session_gives_no_risk_factor_value() -> None:
    future = change("EQ:A", SESSION - timedelta(days=3), "10-Q", acc="Q") | {
        "ftc_k_accession": "K", "ftc_k_known_from": SESSION + timedelta(days=1),
        "ftc_k_status": "OK", "ftc_k_rf_cosine": 0.8, "ftc_k_rf_len_change": 0.3}  # fmt: skip
    [row] = compute(future).to_dict("records")
    assert pd.isna(row["risk_factor_sim_cosine"]) and pd.isna(row["risk_factor_status"])


def test_a_non_ok_status_is_carried_with_null_values_and_item_1a_gap_is_not_comparable() -> None:
    np_row = change("EQ:A", SESSION - timedelta(days=5), status="NO_PRIOR", cosine=None)
    [row] = compute(np_row).to_dict("records")
    assert row["text_sim_status"] == "NO_PRIOR" and pd.isna(row["text_sim_cosine"])
    no_1a = change("EQ:B", SESSION - timedelta(days=5), "10-K", rf=None)  # compared, no 1A pair
    [row2] = compute(no_1a).to_dict("records")
    assert row2["text_sim_status"] == "OK" and row2["risk_factor_status"] == "NOT_COMPARABLE"
    assert pd.isna(row2["risk_factor_sim_cosine"])


def test_no_input_gives_no_rows_and_the_output_is_typed() -> None:
    assert fts.compute({fts.SOURCE: None}, SESSION, None).empty
    out = compute(change("EQ:A", SESSION - timedelta(days=5), "10-K", rf=0.8))
    typed = conform("rollups/instrument/filing_text_similarity@v1", out, fts.COLUMNS)
    assert str(typed["risk_factor_sim_cosine"].dtype) == "float32"
    assert str(typed["text_sim_known_from"].dtype) == "date32[day][pyarrow]"
