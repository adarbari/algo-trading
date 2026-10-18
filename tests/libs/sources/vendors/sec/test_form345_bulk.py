"""SEC Insider Transactions Data Sets: a quarter's zip (built from the readme's table and column
names) gives the Form 4 / 4/A rows with each line and owner, dates as ``DD-MON-YYYY``, roles from
``RPTOWNER_RELATIONSHIP``; Forms 3 and filings without an owner or a line are left out; a missing
quarter is ``None``; a zip without a table is an error."""

import io
import zipfile

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.series import INSIDER_COLUMNS, INSIDER_FRAME, InsiderRequest
from algotrade_sources.vendors.sec.form4_xml import parse_form4
from algotrade_sources.vendors.sec.form345_bulk import SecForm345Bulk, parse_bulk, zip_url
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import sec as payloads

FIRST, AMENDED = "0000999001-26-000001", "0000999001-26-000002"


def test_a_quarter_gives_the_form_4_rows_of_each_line_and_owner() -> None:
    frame = parse_bulk(payloads.example_quarter())
    assert tuple(frame.columns) == INSIDER_COLUMNS
    assert set(frame["form"]) == {"4", "4/A"}  # the Form 3 is left out
    assert "0000999001-26-000003" not in set(frame["accession"])  # no owner row: nothing says whose
    first = frame[frame["accession"] == FIRST]
    assert len(first) == 3 and first["line"].tolist() == [1, 2, 3]
    buy = first[first["transaction_code"] == "P"].iloc[0]
    assert (buy["shares"], buy["price"], buy["shares_after"]) == (1000, 12.5, 26000)
    assert buy["transaction_date"] == pd.Timestamp("2026-09-28")
    assert buy["period_of_report"] == pd.Timestamp("2026-09-28")
    assert buy["filing_date"] == pd.Timestamp("2026-09-30") and pd.isna(buy["amends_date"])
    assert buy["issuer_cik"] == "0000999001" and buy["owner_cik"] == "0000888001"
    assert buy["is_director"] and buy["is_officer"] and not buy["is_ten_pct_owner"]
    assert buy["officer_title"] == "Chief Financial Officer"
    assert buy["owner_name"] == "Doe Jane"  # as filed, whitespace trimmed
    assert first[first["transaction_code"] == "M"]["derivative"].tolist() == [True]
    assert first["plan_10b5_1"].isna().all()


def test_an_amendment_names_its_original_and_carries_the_plan_checkbox() -> None:
    frame = parse_bulk(payloads.example_quarter())
    amended = frame[frame["accession"] == AMENDED]
    assert set(amended["form"]) == {"4/A"} and set(amended["plan_10b5_1"]) == {True}
    assert set(amended["amends_date"]) == {pd.Timestamp("2026-09-30")}


def test_the_same_filing_has_the_same_line_numbers_whichever_source_read_it() -> None:
    xml = (REPO_ROOT / "tests/fixtures/sources/sec/form4_hand_built_purchase.xml").read_bytes()
    from_xml = parse_form4(xml, FIRST).set_index("transaction_code")["line"]
    bulk = parse_bulk(payloads.example_quarter())
    from_bulk = bulk[bulk["accession"] == FIRST].set_index("transaction_code")["line"]
    assert from_xml.to_dict() == from_bulk.to_dict()


def test_the_url_names_the_quarter() -> None:
    assert zip_url("2019q2").endswith("/insider-transactions-data-sets/2019q2_form345.zip")
    with pytest.raises(ValueError, match="not a quarter label"):
        zip_url("2019q5")


def test_a_quarter_not_published_yet_is_none() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(404)

    source = SecForm345Bulk(http_for(transport, RetryPolicy(tries=1)))
    assert source.fetch(InsiderRequest(key="2026q4")) is None


def test_the_source_reads_a_quarter_and_a_zip_without_a_table_is_an_error() -> None:
    source = SecForm345Bulk(http_for(lambda url: payloads.example_quarter()))
    request = InsiderRequest(key="2026q3")
    payload = source.fetch(request)
    assert payload is not None
    normalized = source.normalize(request, payload)
    assert normalized is not None and len(normalized.parsed[INSIDER_FRAME]) == 5
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\n")
    with pytest.raises(ValueError, match="lacks columns"):
        parse_bulk(buffer.getvalue())
    only = io.BytesIO()
    with zipfile.ZipFile(only, "w") as archive:
        archive.writestr("SUBMISSION.tsv", payloads.FORM345_TABLES["SUBMISSION"].replace(" ", "\t"))
    with pytest.raises(ValueError, match="has no REPORTINGOWNER table"):
        parse_bulk(only.getvalue())
    with pytest.raises(TypeError, match="needs an InsiderRequest"):
        source.fetch(FetchRequest("2026q3"))
