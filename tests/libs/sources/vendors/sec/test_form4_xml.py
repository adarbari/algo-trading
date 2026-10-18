"""SEC Form 4 ownership XML (a hand-built filing in the real element layout): a row per
transaction line and owner, holdings left out, numbers and checkboxes read as filed, the raw XML
named from the submissions' ``primaryDocument``, a DTD refused."""

import pandas as pd
import pytest

from algotrade_sources.framework.series import INSIDER_COLUMNS, INSIDER_FRAME, InsiderRequest
from algotrade_sources.vendors.sec.form4_xml import (
    SecForm4Xml,
    build_frame,
    document_url,
    flag,
    number,
    parse_form4,
    raw_document,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

XML = (REPO_ROOT / "tests/fixtures/sources/sec/form4_hand_built_purchase.xml").read_bytes()
ACCESSION = "0000999001-26-000001"
FILING = ["accession", "form", "issuer_cik", "issuer_symbol", "filing_date", "period_of_report"]
FILING += ["amends_date", "plan_10b5_1"]
OWNER = ["accession", "owner_cik", "is_director", "is_officer", "is_ten_pct_owner", "is_other"]
OWNER += ["officer_title"]
LINES = ["accession", "derivative", "transaction_date", "transaction_code", "acquired_disposed"]
LINES += ["shares", "price", "shares_after", "direct_indirect"]


def test_a_filing_is_a_row_per_transaction_line_with_the_owner_and_no_holdings() -> None:
    frame = parse_form4(XML, ACCESSION)
    assert tuple(frame.columns) == INSIDER_COLUMNS and len(frame) == 3  # P, S and the option M
    by_code = frame.set_index("transaction_code")
    purchase = by_code.loc["P"]
    assert (purchase["shares"], purchase["price"], purchase["shares_after"]) == (1000, 12.5, 26000)
    assert purchase["acquired_disposed"] == "A" and purchase["direct_indirect"] == "D"
    assert purchase["transaction_date"] == pd.Timestamp("2026-09-28") and not purchase["derivative"]
    assert (
        by_code.loc["S", "direct_indirect"] == "I" and by_code.loc["S", "acquired_disposed"] == "D"
    )
    assert bool(by_code.loc["M", "derivative"]) and by_code.loc["M", "price"] == 0
    assert set(frame["owner_cik"]) == {"0000888001"} and set(frame["owner_count"]) == {1}
    assert frame["is_director"].all() and frame["is_officer"].all()  # "1" and "true"
    assert not frame["is_ten_pct_owner"].any() and not frame["is_other"].any()
    assert set(frame["officer_title"]) == {"Chief Financial Officer"}
    assert set(frame["issuer_cik"]) == {"0000999001"} and set(frame["issuer_symbol"]) == {"EXMP"}
    assert set(frame["form"]) == {"4"} and frame["filing_date"].isna().all()
    assert set(frame["period_of_report"]) == {pd.Timestamp("2026-09-28")}
    assert set(frame["plan_10b5_1"]) == {False}  # aff10b5One = 0: a checkbox ticked "no"


def test_lines_are_numbered_by_content_so_the_order_of_a_filing_does_not_matter() -> None:
    frame = parse_form4(XML, ACCESSION)
    filing = frame.drop_duplicates("accession")[FILING]
    owner = frame.drop_duplicates("owner_cik")[OWNER]
    lines = frame[LINES].iloc[::-1].reset_index(drop=True)  # the lines in the opposite order
    again = build_frame(filing, owner, lines)
    keys = ["transaction_code", "line"]
    assert frame[keys].equals(again[keys]) and sorted(frame["line"]) == [1, 2, 3]


def test_joint_owners_each_get_the_lines_and_the_count() -> None:
    two = XML.replace(
        b"</reportingOwner>",
        b"</reportingOwner><reportingOwner><reportingOwnerId><rptOwnerCik>0000888002"
        b"</rptOwnerCik></reportingOwnerId><reportingOwnerRelationship><isTenPercentOwner>1"
        b"</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>",
        1,
    )
    frame = parse_form4(two, ACCESSION)
    assert len(frame) == 6 and set(frame["owner_count"]) == {2}
    fund = frame[frame["owner_cik"] == "0000888002"]
    assert fund["is_ten_pct_owner"].all() and not fund["is_director"].any()
    assert fund["officer_title"].isna().all()


def test_an_amendment_names_its_original_and_a_missing_checkbox_is_null() -> None:
    amended = XML.replace(
        b"<documentType>4</documentType>",
        b"<documentType>4/A</documentType>"
        b"<dateOfOriginalSubmission>2026-09-30</dateOfOriginalSubmission>",
    )
    amended = amended.replace(b"<aff10b5One>0</aff10b5One>", b"")
    frame = parse_form4(amended, ACCESSION)
    assert set(frame["form"]) == {"4/A"} and set(frame["amends_date"]) == {
        pd.Timestamp("2026-09-30")
    }
    assert frame["plan_10b5_1"].isna().all()


def test_a_holdings_only_filing_has_no_lines_and_a_broken_one_is_an_error() -> None:
    start, end = XML.index(b"<nonDerivativeTable>"), XML.index(b"</derivativeTable>")
    assert parse_form4(XML[:start] + XML[end + len(b"</derivativeTable>") :], ACCESSION).empty
    with pytest.raises(ValueError, match="DTD or entity"):
        parse_form4(b'<!DOCTYPE x [<!ENTITY a "b">]><ownershipDocument/>', ACCESSION)
    with pytest.raises(ValueError, match="not an ownership document"):
        parse_form4(b"<html/>", ACCESSION)
    with pytest.raises(ValueError, match="without an issuer CIK"):
        parse_form4(
            b"<ownershipDocument><documentType>4</documentType></ownershipDocument>", ACCESSION
        )


def test_numbers_and_checkboxes_as_filed() -> None:
    assert number("1,234.5") == 1234.5 and pd.isna(number("")) and pd.isna(number("n/a"))
    assert flag("1") is True and flag("TRUE") is True and flag("0") is False and flag("") is None
    assert flag(None) is None and flag("maybe") is None


def test_the_raw_xml_is_named_without_the_stylesheet_directory() -> None:
    assert raw_document("xslF345X05/wk-form4_1759270880.xml") == "wk-form4_1759270880.xml"
    assert raw_document("form4.xml") == "form4.xml"
    with pytest.raises(ValueError, match="not an XML document"):
        raw_document("../../etc/passwd")
    with pytest.raises(ValueError, match="not an XML document"):
        raw_document("filing.htm")
    url = document_url("999001", ACCESSION, "xslF345X05/form4.xml")
    assert url.endswith("/Archives/edgar/data/999001/000099900126000001/form4.xml")
    with pytest.raises(ValueError, match="not a CIK / accession"):
        document_url("999001", "not-an-accession", "form4.xml")


def test_the_source_fetches_the_filing_and_returns_its_rows() -> None:
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        return XML

    source = SecForm4Xml(http_for(transport))
    request = InsiderRequest(key=ACCESSION, cik="0000999001", document="xslF345X05/form4.xml")
    payload = source.fetch(request)
    assert payload == XML and seen == [document_url("0000999001", ACCESSION, "form4.xml")]
    normalized = source.normalize(request, XML)
    assert normalized is not None and len(normalized.parsed[INSIDER_FRAME]) == 3
    with pytest.raises(TypeError, match="needs an InsiderRequest"):
        source.fetch(request.__class__.__mro__[1]("x"))  # a plain FetchRequest
