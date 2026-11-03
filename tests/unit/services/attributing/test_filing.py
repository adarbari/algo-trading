"""``attribute``: the 8-K item codes name the cause of a mover's reaction session, and a filing for
another session, a mover-less name or an exhibit alone gives no row."""

from datetime import date

import pandas as pd
import pytest

from algotrade.services.attributing import filing, taxonomy

S = date(2026, 10, 2)


def _filings(*rows: tuple[str, str, date, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"instrument_id": i, "items": items, "event_date": day, "accession": acc,
             "ts": pd.Timestamp("2026-10-02T12:00:00Z")}
            for i, items, day, acc in rows
        ]
    )  # fmt: skip


def test_the_item_names_the_cause_with_high_confidence() -> None:
    out = filing.attribute_from_filings(
        {"EQ:A"}, _filings(("EQ:A", "2.02,9.01", S, "0001-26-1")), S
    )
    row = out.iloc[0]
    assert (row["cause_class"], row["confidence"]) == (taxonomy.RESULTS, filing.SINGLE)
    assert row["evidence_ref"] == "0001-26-1" and row["known_from"] == S
    assert row["ts"] == pd.Timestamp(S, tz="UTC")


def test_several_causes_take_the_most_specific_and_lower_confidence() -> None:
    row = filing.attribute_from_filings(
        {"EQ:A"}, _filings(("EQ:A", "1.01,4.02,8.01", S, "x")), S
    ).iloc[0]
    assert row["cause_class"] == taxonomy.RESTATEMENT
    assert row["confidence"] == pytest.approx(filing.MIXED)
    assert "agreement" in row["cause_text"] and "other_event" in row["cause_text"]


def test_a_filing_of_another_session_a_non_mover_or_an_exhibit_alone_gives_no_row() -> None:
    other = _filings(("EQ:A", "2.02", date(2026, 10, 1), "a"))
    assert filing.attribute_from_filings({"EQ:A"}, other, S).empty  # accepted for another session
    assert filing.attribute_from_filings({"EQ:B"}, _filings(("EQ:A", "2.02", S, "a")), S).empty
    assert filing.attribute_from_filings({"EQ:A"}, _filings(("EQ:A", "9.01", S, "a")), S).empty
    assert filing.attribute_from_filings({"EQ:A"}, None, S).empty


def test_two_filings_for_one_mover_keep_the_most_specific() -> None:
    both = _filings(("EQ:A", "8.01", S, "a"), ("EQ:A", "2.01", S, "b"))
    out = filing.attribute_from_filings({"EQ:A"}, both, S)
    assert list(out["cause_class"]) == [taxonomy.ACQUISITION] and list(out["evidence_ref"]) == ["b"]
