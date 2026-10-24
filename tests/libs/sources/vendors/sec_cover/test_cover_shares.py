"""The SEC cover-shares adapter: per-class shares from a filing's XBRL cover (multi-class,
unlisted class with a null symbol, single class, a 40-F with no cover tags), the instance fetched
only when the filing's index.json lists it, and malformed or hostile XML a typed error."""

import json
from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest, TransientFetchError
from algotrade_sources.framework.http import HttpError
from algotrade_sources.framework.series import (
    COVER_SHARES_COLUMNS,
    COVER_SHARES_FRAME,
    FilingTextRequest,
)
from algotrade_sources.vendors.sec_cover.cover_shares import (
    ClassShares,
    CoverParseError,
    SecCoverShares,
    archive_url,
    instance_name,
    parse_cover_shares,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
CIK, ACCN = "1652044", "0001652044-24-000022"
BASE = "https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/"


def fixture(name: str) -> bytes:
    return (SEC / f"cover_{name}_synthetic.xml").read_bytes()


def test_multiclass_parse_sorted_with_custom_members() -> None:
    rows = parse_cover_shares(fixture("multiclass"), CIK, ACCN)
    assert [r.class_member for r in rows] == [
        "goog:CapitalClassAMember",
        "goog:CapitalClassCMember",
        "us-gaap:CommonClassBMember",
    ]
    a, c, b = rows
    assert (a.shares, a.trading_symbol, a.as_of) == (5_800_000_000, "GOOGL", date(2024, 1, 24))
    assert a.security_title == "Class A Common Stock, $0.001 par value"
    assert (c.shares, c.trading_symbol) == (5_000_000, "GOOG")  # a comma is read
    assert (b.shares, b.trading_symbol, b.security_title) == (870_000_000, None, None)
    assert {r.period_end for r in rows} == {date(2023, 12, 31)}
    assert {(r.cik, r.accession) for r in rows} == {("0001652044", ACCN)}
    assert rows == parse_cover_shares(fixture("multiclass"), CIK, ACCN)  # deterministic


def test_latest_count_wins_for_a_member() -> None:
    rows = parse_cover_shares(fixture("multiclass"), CIK, ACCN)
    assert rows[-1].shares == 870_000_000  # not the 2023-12-31 fact of the same member


def test_unlisted_class_keeps_a_null_symbol() -> None:
    listed, unlisted = parse_cover_shares(fixture("unlisted_class"), CIK, ACCN)
    assert (listed.trading_symbol, listed.shares) == ("ERIE", 46_000_000)
    assert unlisted == ClassShares(
        cik="0001652044",
        accession=ACCN,
        class_member="us-gaap:CommonClassBMember",
        shares=2500,
        as_of=date(2024, 7, 25),
        period_end=date(2024, 6, 30),
        trading_symbol=None,
        security_title=None,
    )


def test_single_class_filer_has_no_member() -> None:
    (row,) = parse_cover_shares(fixture("single_class"), CIK, ACCN)
    assert (row.class_member, row.shares, row.trading_symbol) == (None, 15_115_823_000, "AAPL")
    assert row.period_end == date(2024, 9, 28) and row.as_of == date(2024, 10, 18)


def test_40f_without_cover_tags_is_empty() -> None:
    assert parse_cover_shares(fixture("40f_no_shares"), CIK, ACCN) == ()


@pytest.mark.parametrize(
    "xml",
    [
        b"<xbrli:xbrl",
        b"",
        b'<!DOCTYPE x [<!ENTITY a "b">]><x/>',
    ],
)
def test_malformed_or_hostile_xml_raises_typed_error(xml: bytes) -> None:
    with pytest.raises(CoverParseError):
        parse_cover_shares(xml, CIK, ACCN)


@pytest.mark.parametrize("text", ["12.5", "many", "-3"])
def test_bad_share_count_raises_typed_error(text: str) -> None:
    xml = fixture("single_class").replace(b"15115823000", text.encode())
    with pytest.raises(CoverParseError):
        parse_cover_shares(xml, CIK, ACCN)


def test_names_and_urls() -> None:
    assert instance_name("goog-20231231.htm") == "goog-20231231_htm.xml"
    assert archive_url(CIK, ACCN, "index.json") == BASE + "index.json"
    for bad in ("../x.htm", "a/b.htm", "doc.pdf"):
        with pytest.raises(ValueError):
            instance_name(bad)
    with pytest.raises(ValueError):
        archive_url("x", ACCN, "index.json")


def index(*names: str) -> bytes:
    return json.dumps({"directory": {"item": [{"name": n} for n in names]}}).encode()


def source(files: dict[str, bytes], urls: list[str]) -> SecCoverShares:
    def transport(url: str) -> bytes:
        urls.append(url)
        if url not in files:
            raise HttpError(404)
        return files[url]

    return SecCoverShares(http_for(transport))


def test_read_reads_index_then_instance() -> None:
    urls: list[str] = []
    files = {
        BASE + "index.json": index("goog-20231231.htm", "goog-20231231_htm.xml"),
        BASE + "goog-20231231_htm.xml": fixture("multiclass"),
    }
    rows = source(files, urls).read(CIK, ACCN, "goog-20231231.htm")
    assert rows is not None and len(rows) == 3
    assert urls == [BASE + "index.json", BASE + "goog-20231231_htm.xml"]


def test_read_none_when_instance_unlisted_or_filing_missing() -> None:
    urls: list[str] = []
    listed_without = {BASE + "index.json": index("goog-20231231.htm")}
    assert source(listed_without, urls).read(CIK, ACCN, "goog-20231231.htm") is None
    assert urls == [BASE + "index.json"]  # the instance was not asked for
    assert source({}, []).read(CIK, ACCN, "goog-20231231.htm") is None


def test_read_block_page_or_bad_index_raises() -> None:
    block = {BASE + "index.json": b"Request Rate Threshold Exceeded"}
    with pytest.raises(TransientFetchError):
        source(block, []).read(CIK, ACCN, "goog-20231231.htm")
    with pytest.raises(CoverParseError):
        source({BASE + "index.json": b"[1]"}, []).read(CIK, ACCN, "goog-20231231.htm")


def test_fetch_and_normalize_give_the_frame() -> None:
    files = {
        BASE + "index.json": index("goog-20231231_htm.xml"),
        BASE + "goog-20231231_htm.xml": fixture("unlisted_class"),
    }
    request = FilingTextRequest(
        key=ACCN, cik=CIK, form="10-Q", primary_document="goog-20231231.htm"
    )
    src = source(files, [])
    payload = src.fetch(request)
    assert payload is not None
    normalized = src.normalize(request, payload)
    assert normalized is not None
    frame = normalized.parsed[COVER_SHARES_FRAME]
    assert list(frame.columns) == list(COVER_SHARES_COLUMNS)
    assert frame["shares"].tolist() == [46_000_000, 2500]
    assert frame["trading_symbol"].tolist() == ["ERIE", None]
    assert frame["as_of"].iloc[0] == date(2024, 7, 25)
    assert src.fetch(request.__class__(**{**request.__dict__, "primary_document": "x.htm"})) is None


def test_fetch_refuses_other_requests_and_forms() -> None:
    src = source({}, [])
    with pytest.raises(TypeError):
        src.fetch(FetchRequest("x"))
    bad = FilingTextRequest(key=ACCN, cik=CIK, form="8-K", primary_document="a.htm")
    with pytest.raises(ValueError):
        src.fetch(bad)


def test_conflicting_duplicate_facts_raise_but_identical_ones_do_not() -> None:
    base = fixture("single_class")
    tag = b"dei:EntityCommonStockSharesOutstanding"
    fact = b"<" + tag + b' contextRef="s-1" unit="shares">%s</' + tag + b">"
    same = base.replace(b"</xbrli:xbrl>", fact % b"15115823000" + b"</xbrli:xbrl>")
    assert len(parse_cover_shares(same, CIK, ACCN)) == 1
    other = base.replace(b"</xbrli:xbrl>", fact % b"1" + b"</xbrli:xbrl>")
    with pytest.raises(CoverParseError):
        parse_cover_shares(other, CIK, ACCN)
    symbol = b'<dei:TradingSymbol contextRef="s-1">AAPL2</dei:TradingSymbol>'
    with pytest.raises(CoverParseError):
        parse_cover_shares(base.replace(b"</xbrli:xbrl>", symbol + b"</xbrli:xbrl>"), CIK, ACCN)


def test_utf16_and_uppercase_doctype_are_refused() -> None:
    hostile = '<?xml version="1.0" encoding="utf-16"?><!DocType x [<!ENTITY a "b">]><x/>'
    with pytest.raises(CoverParseError):
        parse_cover_shares(hostile.encode("utf-16"), CIK, ACCN)
    with pytest.raises(CoverParseError):
        parse_cover_shares(b"<!doctype x><x/>", CIK, ACCN)


def test_class_axis_is_found_by_namespace_not_prefix() -> None:
    renamed = (
        fixture("unlisted_class")
        .replace(b"us-gaap:", b"gaap:")
        .replace(
            b'xmlns:us-gaap="http://fasb.org/us-gaap/2024"',
            b'xmlns:gaap="http://fasb.org/us-gaap/2024"',
        )
    )
    assert [r.shares for r in parse_cover_shares(renamed, CIK, ACCN)] == [46_000_000, 2500]
