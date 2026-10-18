"""10-K / 10-Q HTML -> text -> Item sections (edge build D10) over two synthetic filings shaped like
inline-XBRL ones (a hidden XBRL header, a table of contents, page numbers, "Table of Contents"
back-links, an Item header split over two spans, a cross-reference, a repeated header): the longest
candidate per item beats the contents' entry, the part of a 10-Q item comes from its PART line, and
nothing is guessed (NOT_FOUND, NO_ITEMS)."""

import pytest

from algotrade_sources.framework.series import DEFAULT_10K, DEFAULT_10Q, items_for
from algotrade_sources.vendors.sec.filing_items import (
    MAX_CHARS,
    MIN_CHARS,
    NO_ITEMS,
    NOT_FOUND,
    OK,
    SHORT,
    TRUNCATED,
    decode,
    extract_items,
    html_to_text,
    sections,
)
from tests.conftest import REPO_ROOT

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
TEN_K = (SEC / "10k_items_trimmed.htm").read_bytes()
TEN_Q = (SEC / "10q_items_trimmed.htm").read_bytes()


def rows(document: bytes, form: str, wanted: tuple[str, ...]) -> dict[str | None, dict]:
    return {r["item"]: r for r in extract_items(document, form, wanted)}


def test_text_drops_the_hidden_header_page_numbers_and_contents_links() -> None:
    text = html_to_text(TEN_K)
    assert "HIDDEN XBRL FACTS" not in text and "aapl-20240928" not in text  # header, title
    assert "Table of Contents" not in text
    assert "\n12\n" not in text and "\n1\n" not in text  # page numbers on a line of their own
    assert "Item 1A.Risk Factors" in text  # the two spans of a header join without a space
    assert "\u00a0" not in text and "  " not in text


def test_a_ten_k_splits_into_its_items_and_the_body_beats_the_contents() -> None:
    found = rows(TEN_K, "10-K", DEFAULT_10K)
    assert list(found) == ["1", "1A", "3", "7", "7A", "9A"]
    assert found["1A"]["quality"] == OK and found["1A"]["text"].startswith(
        "Risk Factors\nThe Company faces"
    )
    assert "Table of Contents" not in found["1A"]["text"] and "Item 1B" not in found["1A"]["text"]
    assert found["7"]["quality"] == OK and "Net sales increased" in found["7"]["text"]
    # a header repeated inside the section and a cross-reference do not cut it
    assert (
        "Item 7. Management" in found["7"]["text"]
        and "risks described in Item 1A" in found["7"]["text"]
    )
    assert found["9A"]["text"].startswith("Controls and Procedures\nManagement evaluated")
    assert all(r["parser_version"] == 1 and r["method"] == "item_headers" for r in found.values())


def test_a_short_section_is_kept_and_flagged_never_dropped() -> None:
    found = rows(TEN_K, "10-K", ("3", "7A"))
    assert found["3"]["quality"] == SHORT and "None." in found["3"]["text"]
    assert found["3"]["char_count"] == len(found["3"]["text"]) < MIN_CHARS
    assert found["3"]["reason"] == f"{found['3']['char_count']} characters"
    assert (
        found["7A"]["quality"] == OK
        and "Not applicable for smaller reporting" in found["7A"]["text"]
    )


def test_the_last_entry_of_the_contents_does_not_swallow_the_body() -> None:
    # Item 10 is the contents' last entry: its span must not run through the whole body
    found = rows(TEN_K, "10-K", ("10",))
    assert found["10"]["quality"] == SHORT and "Incorporated by reference" in found["10"]["text"]
    assert found["10"]["char_count"] < 400


def test_a_wanted_item_without_a_header_is_a_not_found_row_with_no_text() -> None:
    found = rows(TEN_K, "10-K", ("1", "2", "9"))
    assert found["2"] == {
        "item": "2", "text": None, "char_count": 0, "quality": NOT_FOUND,
        "reason": "no header for this item", "method": "item_headers", "parser_version": 1,
    }  # fmt: skip
    assert found["9"]["quality"] == NOT_FOUND and found["1"]["quality"] == OK


def test_a_ten_q_carries_the_part_in_the_item_id() -> None:
    found = rows(TEN_Q, "10-Q", DEFAULT_10Q)
    assert list(found) == ["I-2", "I-3", "II-1", "II-1A"]
    assert found["I-2"]["text"].startswith("Management\u2019s Discussion and Analysis of Financial")
    assert "Revenue for the quarter grew" in found["I-2"]["text"]
    assert found["II-1"]["text"] == "Legal Proceedings\nNone." and found["II-1"]["quality"] == SHORT
    assert "no material changes to the risk factors" in found["II-1A"]["text"]
    assert "Exhibits" not in found["II-1A"]["text"]  # Part II Item 6 is a later item


def test_a_ten_q_without_part_lines_starts_part_ii_when_the_numbers_start_over() -> None:
    body = "x " * 400
    text = (
        "Item 1. Financial Statements\n" + body + "\nItem 2. Management Discussion\n" + body
        + "\nItem 3. Market Risk\n" + body + "\nItem 4. Controls\n" + body
        + "\nItem 1. Legal Proceedings\n" + body + "\nItem 1A. Risk Factors\n" + body
        + "\nItem 6. Exhibits\n" + body
    )  # fmt: skip
    assert set(sections(text, "10-Q")) == {"I-1", "I-2", "I-3", "I-4", "II-1", "II-1A", "II-6"}


def test_a_cross_reference_line_is_no_header() -> None:
    body = "word " * 300
    text = (
        "Item 7. Management Discussion\n" + body
        + "\nItem 8 of this Annual Report holds the statements\n" + body
        + "\nSee Item 7A. Market Risk for more\n" + body + "\nItem 7A. Market Risk\n" + body
    )  # fmt: skip
    found = sections(text, "10-K")
    assert "Item 8 of this Annual Report" in found["7"] and "8" not in found
    assert found["7"].count("word") == 900 and found["7A"].count("word") == 300


def test_a_document_without_any_header_is_one_null_item_row() -> None:
    page = (
        b"<html><body>"
        + b"<p>The company filed an amendment to add exhibits.</p>" * 5
        + b"</body></html>"
    )
    only = extract_items(page, "10-K/A", DEFAULT_10K)
    assert len(only) == 1 and only[0]["item"] is None and only[0]["text"] is None
    assert only[0]["quality"] == NO_ITEMS and only[0]["reason"] and only[0]["char_count"] == 0


def test_a_runaway_section_is_cut_and_flagged() -> None:
    big = "<p>" + "w " * (MAX_CHARS // 2 + 10) + "</p>"
    document = (
        f"<html><body><p>Item 1A. Risk Factors</p>{big}<p>Item 1B. Unresolved</p></body></html>"
    )
    found = rows(document.encode(), "10-K", ("1A",))
    assert found["1A"]["quality"] == TRUNCATED and found["1A"]["char_count"] == MAX_CHARS


@pytest.mark.parametrize("wanted", [(), ("I-2",), ("1A", "7")])
def test_items_for_keeps_the_family_ids_else_the_form_default(wanted: tuple[str, ...]) -> None:
    assert items_for("10-K", wanted) == (("1A", "7") if wanted == ("1A", "7") else DEFAULT_10K)
    assert items_for("10-Q/A", wanted) == (("I-2",) if wanted == ("I-2",) else DEFAULT_10Q)


def test_the_encoding_falls_back_to_windows_1252() -> None:
    assert decode("café".encode("cp1252")) == "café"
    assert decode("café".encode()) == "café"
