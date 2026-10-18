"""The IPO facts read from a 424B4 text (edge build D8): each rule of
``sec_prospectus/prospectus.py`` and each failure mode (not an IPO, a SPAC, no term, an anchor
that is not the prospectus date, several terms, a term in months or years, an early-release
clause), plus the document URL and the fetch."""

from datetime import date

import pytest

from algotrade_sources.framework.series import IPO_COLUMNS, IPO_FRAME, ProspectusRequest
from algotrade_sources.vendors.sec_prospectus.prospectus import (
    AMBIGUOUS,
    EXTRACTED,
    NO_LOCKUP,
    NOT_IPO,
    SPAC,
    UNANCHORED,
    SecProspectus,
    document_url,
    extract,
    lockup_sentences,
    lockup_terms,
    main_term,
    parse_facts,
    plain_text,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import sec as payloads


def facts(payload: bytes) -> dict[str, object]:
    return extract(plain_text(payload))


def test_the_cover_facts_of_a_standard_ipo() -> None:
    row = facts(payloads.prospectus())
    assert row["is_ipo"] is True and row["extraction"] == EXTRACTED and row["reason"] is None
    assert (row["lockup_n"], row["lockup_unit"]) == (180, "days")
    assert row["prospectus_date"] == date(2026, 6, 12) and row["offer_price"] == 18.0
    assert (row["ticker"], row["exchange"]) == ("ABCD", "NASDAQ")
    assert row["lockup_terms"] == "180 days x3"
    # the representatives' discretionary release is in every prospectus: not an early release
    assert row["early_release"] is False and row["early_release_text"] is None


def test_a_prospectus_without_a_first_offering_marker_is_not_an_ipo() -> None:
    row = facts(
        b"<p>We are offering 5,000,000 shares. Lock-up: 90 days after the date of this "
        b"prospectus we will not sell shares.</p>"
    )
    assert row["is_ipo"] is False and row["extraction"] == NOT_IPO
    assert row["lockup_n"] is None and "follow-on" in str(row["reason"])


def test_no_lockup_sentence_is_no_lockup_with_a_reason_and_no_guess() -> None:
    cover = payloads.prospectus(repeat=0)
    row = facts(cover)
    assert row["extraction"] == NO_LOCKUP and row["lockup_n"] is None
    assert row["lockup_terms"] is None and "no lock-up term" in str(row["reason"])


def test_a_day_count_from_another_anchor_is_unanchored_not_a_date_guess() -> None:
    extra = "<p>The lock-up agreements expire 90 days after the closing of this offering.</p>"
    row = facts(payloads.prospectus(repeat=0, extra=extra))
    assert row["extraction"] == UNANCHORED and row["lockup_n"] is None
    assert "90 days" in str(row["reason"])


def test_a_blank_check_company_has_no_dated_lockup() -> None:
    extra = "<p>We are a blank check company formed to effect a business combination.</p>"
    row = facts(payloads.prospectus(extra=extra))
    assert row["is_ipo"] is True and row["extraction"] == SPAC and row["lockup_n"] is None


def test_the_main_term_dominates_a_carve_out_but_two_equal_terms_are_ambiguous() -> None:
    carve = facts(payloads.prospectus(terms=("180 days", "90 days"), repeat=2))
    assert carve["extraction"] == AMBIGUOUS and carve["lockup_n"] is None
    assert "90 days x2; 180 days x2" in str(carve["lockup_terms"])
    many = payloads.prospectus(terms=("180 days",), repeat=5) + payloads.prospectus(
        terms=("365 days",), repeat=1
    )
    dominant = facts(many)
    assert dominant["extraction"] == EXTRACTED and dominant["lockup_n"] == 180
    assert dominant["lockup_terms"] == "180 days x5; 365 days x1"


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("180 days", (180, "days")),
        ("the 180-day period beginning on", None),  # handled below: the phrase form
        ("six months", (6, "months")),
        ("12 months", (12, "months")),
        ("one year", (12, "months")),
    ],
)
def test_terms_in_days_months_and_years(term: str, expected: tuple[int, str] | None) -> None:
    if expected is None:
        text = "The 180-day period beginning on the date of this prospectus is the lock-up period."
        assert lockup_terms(lockup_sentences(text)) == {(180, "days"): 1}
        return
    text = f"Holders agreed to a lock-up of {term} after the date of this prospectus."
    assert lockup_terms(lockup_sentences(text)) == {expected: 1}


def test_main_term_rules() -> None:
    assert main_term({}) is None
    assert main_term({(180, "days"): 1}) == (180, "days")
    assert main_term({(180, "days"): 4, (90, "days"): 2}) == (180, "days")
    assert main_term({(180, "days"): 3, (90, "days"): 2}) is None


def test_a_contractual_early_release_is_kept_with_its_clause() -> None:
    extra = (
        "<p>If the closing price of our common stock exceeds 125% of the initial public offering "
        "price for 10 of the 15 trading days after our first earnings release, 25% of the "
        "shares subject to the lock-up will be released.</p>"
    )
    row = facts(payloads.prospectus(extra=extra))
    assert row["early_release"] is True and "earnings release" in str(row["early_release_text"])
    assert len(str(row["early_release_text"])) <= 400


def test_an_implausible_or_missing_price_and_date_are_null() -> None:
    row = facts(payloads.prospectus(price="0.01", dated="Smarch 99, 2026"))
    assert row["offer_price"] is None and row["prospectus_date"] is None
    assert row["extraction"] == EXTRACTED  # the term stands; the expiry waits for a date


def test_parse_facts_is_one_typed_row_and_an_empty_document_is_an_error() -> None:
    frame = parse_facts(payloads.prospectus())
    assert list(frame.columns) == list(IPO_COLUMNS) and len(frame) == 1
    assert str(frame["lockup_n"].dtype) == "Int64" and frame["offer_price"].iloc[0] == 18.0
    with pytest.raises(ValueError, match="empty"):
        parse_facts(b"<html><script>x</script></html>")


def test_plain_text_drops_tags_scripts_and_decodes_entities() -> None:
    text = plain_text(b"<p>a&nbsp;b</p><script>var x = 1;</script><b>&#8220;Q&#8221;</b>")
    assert text == "a b “Q”"


def test_the_document_url_and_its_guards() -> None:
    req = ProspectusRequest(key="0001193125-26-123456", cik="1234", document="d123424b4.htm")
    assert document_url(req) == (
        "https://www.sec.gov/Archives/edgar/data/1234/000119312526123456/d123424b4.htm"
    )
    old = ProspectusRequest(key="0001193125-06-123456", cik="1234")
    assert document_url(old).endswith("/data/1234/0001193125-06-123456.txt")
    for bad in (
        ProspectusRequest(key="0001193125-26-123456", cik="1234", document="../x.htm"),
        ProspectusRequest(key="not-an-accession", cik="1234"),
        ProspectusRequest(key="0001193125-26-123456", cik="abc"),
    ):
        with pytest.raises(ValueError):
            document_url(bad)


def test_fetch_and_normalize_over_a_fake_transport() -> None:
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        return payloads.prospectus()

    source = SecProspectus(http_for(transport))
    req = ProspectusRequest(key="0001193125-26-123456", cik="1234", document="a.htm")
    normalized = source.normalize(req, source.fetch(req) or b"")
    assert seen == ["https://www.sec.gov/Archives/edgar/data/1234/000119312526123456/a.htm"]
    assert normalized is not None and normalized.parsed[IPO_FRAME]["lockup_n"].iloc[0] == 180


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("one hundred eighty (180) days after the date of this prospectus", (180, "days")),
        ("one hundred and eighty days after the date of this prospectus", (180, "days")),
        ("ninety days after the date of the prospectus", (90, "days")),
        ("sixty (60) days from the date of the final prospectus", (60, "days")),
        ("one hundred twenty days following the date of this prospectus", (120, "days")),
        ("twelve (12) months after the date of this prospectus", (12, "months")),
    ],
)
def test_terms_written_in_words_with_digits_and_either_anchor(
    phrase: str, expected: tuple[int, str]
) -> None:
    text = f"Our holders entered into lock-up agreements for {phrase}."
    assert lockup_terms(lockup_sentences(text)) == {expected: 1}


def test_the_explicit_date_of_this_prospectus_wins_over_a_leftmost_date_form() -> None:
    extra = "<p>The date of this prospectus is June 12, 2026.</p>"
    row = facts(payloads.prospectus(dated="June 10, 2026", extra=extra))
    assert row["prospectus_date"] == date(2026, 6, 12)
