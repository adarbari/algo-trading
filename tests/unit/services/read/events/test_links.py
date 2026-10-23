"""``source_link``: a filing to its sec.gov index, a report stored from an 8-K to the Item 2.02
filing it came from (at that instant, else that day; none: no link), a macro release key to the
agency page of the config, every other kind and every malformed id to None; and the reads that
carry the link (a filing, a report row, a macro release)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.read.context import open_context
from algotrade.services.read.events.ahead import load_ahead
from algotrade.services.read.events.filings import load_filings, load_results_filings
from algotrade.services.read.events.links import (
    FilingRef,
    filing_url,
    results_filing,
    source_link,
)
from algotrade.services.read.events.stored import load_events
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.events.conftest import D1, FILING, filing_row, store_with

INDEX = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000070/0000320193-26-000070-index.htm"
ACCEPTED = datetime(2026, 8, 14, 20, 10, tzinfo=UTC)
RESULTS = FilingRef("0000320193", "0000320193-26-000070", ACCEPTED, "8-K")
MACRO = {"CPI": "https://www.bls.gov/cpi/"}


def test_a_filing_links_to_its_sec_index() -> None:
    assert source_link("filing", cik="0000320193", accession="0000320193-26-000070") == INDEX
    assert filing_url("320193", "0000320193-26-000070") == INDEX  # leading zeros either way


@pytest.mark.parametrize(
    ("cik", "accession"),
    [
        ("../x", "0000320193-26-000070"),
        ("320193", "0000320193-26-000070/../../x"),
        ("320193", "0001-2026-07-30"),
        ("", "0000320193-26-000070"),
        ("320193", ""),
        ("32019 3", "0000320193-26-000070"),
    ],
)
def test_ids_that_are_not_the_digits_sec_writes_give_no_link(cik: str, accession: str) -> None:
    assert filing_url(cik, accession) is None
    assert source_link("filing", cik=cik, accession=accession) is None


def test_a_filing_with_a_missing_id_has_no_link() -> None:
    assert source_link("filing", cik="320193") is None
    assert source_link("filing") is None


def test_a_report_from_an_8k_links_to_the_item_202_filing_of_that_instant() -> None:
    other = FilingRef("0000320193", "0000320193-26-000071", ACCEPTED.replace(hour=22), "8-K")
    found = source_link("earnings", source="sec_8k", at=ACCEPTED, filings=[other, RESULTS])
    assert found == INDEX


def test_a_midnight_acceptance_stored_one_second_later_still_matches() -> None:
    at = datetime(2026, 8, 14, 20, 10, 1, tzinfo=UTC)
    assert source_link("earnings", source="sec_8k", at=at, filings=[RESULTS]) == INDEX


def test_without_the_same_instant_the_same_day_matches_an_8k_before_its_amendment() -> None:
    amended = FilingRef("0000320193", "0000320193-26-000072", ACCEPTED.replace(hour=1), "8-K/A")
    at = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)  # a calendar-style midnight row of the day
    assert results_filing(at, [amended, RESULTS]) == RESULTS
    assert results_filing(at, [amended]) == amended


def test_no_filing_of_that_day_is_no_link() -> None:
    later = FilingRef("0000320193", "0000320193-26-000073", ACCEPTED.replace(day=15), "8-K")
    assert source_link("earnings", source="sec_8k", at=ACCEPTED, filings=[later]) is None
    assert source_link("earnings", source="sec_8k", at=ACCEPTED) is None


def test_a_calendar_only_report_has_no_link_even_beside_a_filing() -> None:
    assert source_link("earnings", source="nasdaq", at=ACCEPTED, filings=[RESULTS]) is None
    assert source_link("earnings", at=ACCEPTED, filings=[RESULTS]) is None


def test_a_macro_release_links_to_the_configured_agency_page() -> None:
    assert source_link("macro_release", release_key="CPI", macro_links=MACRO) == MACRO["CPI"]


def test_an_unknown_macro_key_or_no_config_has_no_link() -> None:
    assert source_link("macro_release", release_key="NOPE", macro_links=MACRO) is None
    assert source_link("macro_release", release_key="CPI") is None
    assert source_link("macro_release", macro_links=MACRO) is None


@pytest.mark.parametrize("kind", ["dividend", "split", "market_structure", "reference_change"])
def test_kinds_with_nothing_stored_to_link_to_have_none(kind: str) -> None:
    assert (
        source_link(kind, cik="320193", accession="0000320193-26-000070", release_key="CPI") is None
    )


def _valid_filings(writer: StoreWriter) -> None:
    rows = [
        {**filing_row("2026-08-14 20:10", "2.02,9.01", date(2026, 8, 14)),
         "cik": "320193", "accession": "0000320193-26-000070"},
        {**filing_row("2026-09-15 13:00", "5.02", date(2026, 9, 15)),
         "cik": "320193", "accession": "0000320193-26-000090"},
    ]  # fmt: skip
    writer.write_table(FILING, D1, "valid", stamped(rows, D1, "valid", source="sec"))


def _earnings(writer: StoreWriter) -> None:
    def row(ts: str) -> dict[str, object]:
        return {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(ts, tz="UTC"), "known_from": D1,
                "carried_from": None}  # fmt: skip

    for source, ts in (("sec_8k", "2026-08-14 20:10"), ("nasdaq", "2026-04-30 00:00")):
        run = f"earn-{source}"
        writer.write_table("events/earnings", D1, run, stamped([row(ts)], D1, run, source=source))


def test_a_filing_read_carries_its_index_and_a_malformed_id_none() -> None:
    reader = store_with(_valid_filings)
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), D1)
    found, _ = load_filings(ctx, ["EQ:AAA"], 24)
    urls = [f.source_url for f in found["EQ:AAA"]]
    assert INDEX in urls
    assert any(u and u.endswith("/000032019326000090/0000320193-26-000090-index.htm") for u in urls)
    assert urls.count(None) == 2  # the fixture's two older 8-Ks carry a placeholder accession


def test_the_results_filings_are_the_item_202_ones_known_by_the_session() -> None:
    reader = store_with(_valid_filings)
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), D1)
    refs = load_results_filings(ctx, ["EQ:AAA", "EQ:BBB"])
    mine = [(r.accession, r.accepted) for r in refs["EQ:AAA"] if r.cik == "320193"]
    assert mine == [("0000320193-26-000070", ACCEPTED)]  # not the 5.02 one
    assert refs["EQ:BBB"] == ()
    assert load_results_filings(ctx, []) == {}


def test_a_report_row_stored_from_an_8k_has_the_link_and_a_calendar_row_none() -> None:
    reader = store_with(_valid_filings, _earnings)
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), D1)
    events = load_events(ctx, ["EQ:AAA"], None, None, ("earnings",))["EQ:AAA"]
    assert {e.date: e.source_url for e in events} == {
        date(2026, 4, 30): None,
        date(2026, 8, 14): INDEX,
    }


def test_a_macro_release_ahead_carries_the_agency_page() -> None:
    reader = store_with()
    configs = MemoryConfigStore({("site", "events", "links"): {"macro": MACRO}})
    ctx = open_context(reader, configs, UserContext("local"), D1)
    ahead = load_ahead(ctx, ["EQ:AAA"], date(2026, 12, 31))
    urls = {e.label: e.source_url for e in ahead.market if e.kind == "macro_release"}
    assert urls == {"CPI": MACRO["CPI"], "GDP": None}  # GDP has no configured page
