"""The recent-filings view a text-comparison group reads: a filing accepted after the close is
invisible on its day and visible the next session (no lookahead), the year-ago comparator comes
with a recent filing, a company with no recent filing or no instrument at the session is not in
the view, amendments are left out, the id-fill versions of a filing are one filing, and the
constants equal the group's (``comparison.py``)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.feature_inputs import load_input
from algotrade.data.filing_text import reading, recent
from algotrade.features.rollups.text import comparison
from algotrade.features.rollups.text import filing_text_change as ftc
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped
from tests.unit.features.rollups.text.test_comparison import body, words

SNAPSHOT = date(2026, 1, 1)
ACCEPTED = pd.Timestamp("2026-09-29T21:30:00Z")  # Tuesday 17:30 New York: public from Wednesday
KNOWN = date(2026, 9, 30)
TEXT = body(words(150), 600)


def item(accession: str, form: str, accepted: pd.Timestamp, report: date, name: str, **kw: object
         ) -> dict[str, object]:  # fmt: skip
    day = accepted.date()
    return {"instrument_id": None, "ts": accepted, "known_from": day, "cik": "0000000001",
            "form": form, "accession": accession, "filing_date": day, "report_date": report,
            "item": name, "parser_version": 1, "text": TEXT, "char_count": len(TEXT),
            "quality": "OK", "reason": None, "method": "item_headers", **kw}  # fmt: skip


def filing(accession: str, form: str, accepted: pd.Timestamp, report: date, **kw: object
           ) -> list[dict[str, object]]:  # fmt: skip
    return [item(accession, form, accepted, report, n, **kw) for n in ("I-2", "II-1A")]


def store(rows: list[dict[str, object]], companies: tuple[tuple[str, str], ...]) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    by_day: dict[date, list[dict[str, object]]] = {}
    for r in rows:
        by_day.setdefault(pd.Timestamp(r["ts"]).date(), []).append(r)  # type: ignore[arg-type]
    for day, part in by_day.items():
        writer.write_table(reading.TABLE, day, f"r-{day}", stamped(part, day, f"r-{day}", T0))
    if companies:
        co = [
            {"instrument_id": i, "symbol": i[3:], "cik": cik, "name": i, "sic": "1",
             "sector": "x", "fetched_on": SNAPSHOT}
            for i, cik in companies
        ]  # fmt: skip
        writer.write_table("instruments/company", SNAPSHOT, "co", stamped(co, SNAPSHOT, "co"))
    return StoreReader(writer._backend)


YEAR_AGO = pd.Timestamp("2025-08-05T20:00:00Z")
RECENT = filing("NEW", "10-Q", ACCEPTED, date(2026, 6, 30)) + filing(
    "OLD", "10-Q", YEAR_AGO, date(2025, 6, 30)
)


def test_a_filing_accepted_after_the_close_is_invisible_that_day_and_visible_the_next() -> None:
    reader = store(RECENT, (("EQ:AAA", "1"),))
    assert recent.recent_filing_texts(reader, date(2026, 9, 29)) is None
    view = recent.recent_filing_texts(reader, KNOWN)
    assert view is not None
    assert set(view["accession"]) == {"NEW", "OLD"}  # the year-ago comparator comes with it
    assert set(view["instrument_id"]) == {"EQ:AAA"} and "text" in view.columns
    assert set(view["known_from"]) == {KNOWN, date(2025, 8, 6)}


def test_a_company_with_no_recent_filing_or_no_instrument_is_not_in_the_view() -> None:
    old_only = store(filing("OLD", "10-Q", YEAR_AGO, date(2025, 6, 30)), (("EQ:AAA", "1"),))
    assert recent.recent_filing_texts(old_only, KNOWN) is None
    delisted = store(RECENT, (("EQ:ZZZ", "9"),))  # the company snapshot has no such cik
    assert recent.recent_filing_texts(delisted, KNOWN) is None
    nothing = store(RECENT, ())
    assert recent.recent_filing_texts(nothing, KNOWN) is None


def test_amendments_are_not_read_and_a_filing_is_one_filing_across_its_id_versions() -> None:
    amendment = filing("AMD", "10-Q/A", ACCEPTED, date(2026, 6, 30))
    filled = [r | {"instrument_id": "EQ:AAA", "parser_version": 2} for r in RECENT]
    view = recent.recent_filing_texts(store(RECENT + amendment + filled, (("EQ:AAA", "1"),)), KNOWN)
    assert view is not None and "AMD" not in set(view["accession"])
    assert len(view) == 4  # NEW and OLD, two items each, one version of each item


def test_the_view_feeds_the_group_through_the_input_loader_one_session_at_a_time() -> None:
    reader = store(RECENT, (("EQ:AAA", "1"),))
    loaded = load_input(reader, recent.TABLE, [KNOWN], 0)
    view = loaded.at(KNOWN, 0)  # type: ignore[attr-defined]
    assert view is not None
    with pytest.raises(ValueError, match="lookback"):
        loaded.at(KNOWN, 5)  # type: ignore[attr-defined]
    [row] = ftc.compute({ftc.FILING_TEXT: view}, KNOWN, None).to_dict("records")
    assert row["ftc_status"] == "OK" and row["ftc_cosine"] == 1.0
    assert row["ftc_accession"] == "NEW" and row["ftc_prior_accession"] == "OLD"
    assert loaded.at(date(2026, 9, 29), 0) is None  # D: accepted after the close, not known


def test_the_reader_constants_equal_the_groups() -> None:
    assert recent.RECENT_SESSIONS == comparison.RECENT_SESSIONS
    assert recent.FORMS == comparison.PERIODIC
    assert set(recent.ITEMS) == {i for items in comparison.ITEMS.values() for i in items}
    assert comparison.OK_QUALITY == reading.OK  # the group's "OK" is the reader's
    assert max(comparison.WINDOW_DAYS) + 60 <= recent.LOOKBACK_DAYS  # a late filer's margin


def test_a_reparsed_old_filing_is_not_recent_news() -> None:
    """Review of #720: a parser re-run stores an old filing with a late ``known_from``; it is not
    a recent filing, and the rows carry the acceptance session."""
    old = pd.Timestamp("2026-02-20 15:00", tz="UTC")
    reparsed = filing("OLDK", "10-K", old, date(2025, 12, 31), known_from=KNOWN)
    reader = store(reparsed, (("EQ:AAA", "1"),))
    assert recent.recent_filing_texts(reader, KNOWN) is None
    view = recent.recent_filing_texts(store(RECENT, (("EQ:AAA", "1"),)), KNOWN)
    assert view is not None and set(view["accepted_session"]) == {KNOWN, date(2025, 8, 6)}


def _write(reader: StoreReader, rows: list[dict[str, object]], run: str) -> None:
    """Commit ``rows`` into their acceptance-day partitions as run ``run`` (a commit sequence)."""
    writer = StoreWriter(reader._backend)
    by_day: dict[date, list[dict[str, object]]] = {}
    for r in rows:
        by_day.setdefault(pd.Timestamp(r["ts"]).date(), []).append(r)  # type: ignore[arg-type]
    for day, part in by_day.items():
        frame = stamped(part, day, run, T0)
        writer.write_table(reading.TABLE, day, run, frame, pending=True)
    reader._backend.tables.commit_run(run, datetime.now(UTC))  # a commit sequence per run


def test_the_rolling_view_equals_the_fresh_view_over_a_run_of_sessions() -> None:
    """The rolling light read changes no row: session after session (a filing leaving the
    five-session window, a late-arriving filing in a new partition before the last session, a
    restated old partition, a re-extraction known only from its stamp) every view equals
    the stateless one, only the new partitions are read when nothing behind moved, and the read
    log of each session is that of the full read."""
    reader = store([], (("EQ:AAA", "1"), ("EQ:BBB", "2")))
    _write(reader, RECENT, "first")
    reads: list[tuple[date, date]] = []
    real = StoreReader.table_range

    def spy(self: StoreReader, table: str, start: date, end: date, *a: object) -> object:
        reads.append((start, end))
        return real(self, table, start, end, *a)  # type: ignore[arg-type]

    StoreReader.table_range = spy  # type: ignore[method-assign]
    try:
        logging, fresh = reader.recording(), reader.recording()
        rolling = recent.RecentFilings(logging)
        sessions = [date(2026, 9, d) for d in (30,)] + [
            date(2026, 10, d) for d in (1, 2, 5, 6, 7, 8, 9, 12)
        ]
        spans: list[list[tuple[date, date]]] = []
        seen: list[bool] = []
        for s in sessions:
            if s == date(2026, 10, 6):  # a late filing lands in an earlier, new partition
                late = filing(
                    "LATE",
                    "10-Q",
                    pd.Timestamp("2026-10-02T15:00:00Z"),
                    date(2026, 6, 30),
                    cik="0000000002",
                )
                old = filing("LATEOLD", "10-Q", YEAR_AGO, date(2025, 6, 30), cik="0000000002")
                _write(reader, late + old, "late")
            if s == date(
                2026, 10, 8
            ):  # a restated partition: a re-extraction known only from its stamp
                fix = [
                    r
                    | {
                        "parser_version": 2,
                        "known_from": date(2026, 10, 8),
                        "text": body(words(150, 50), 600),
                    }
                    for r in filing("NEW", "10-Q", ACCEPTED, date(2026, 6, 30))
                ]
                _write(reader, fix, "fix")
            reads.clear()
            with logging.attribute(s):
                got = rolling.at(s)
            spans.append(list(reads))
            reads.clear()
            with fresh.attribute(s):
                want = recent.recent_filing_texts(fresh, s)
            assert logging.reads(s) == fresh.reads(s)  # the same dependencies are recorded
            seen.append(got is not None)
            if want is None:
                assert got is None
            else:
                assert got is not None
                pd.testing.assert_frame_equal(got, want, check_exact=True)
    finally:
        StoreReader.table_range = real  # type: ignore[method-assign]
    assert any(seen) and not all(seen)  # filings enter and leave the view
    long = [
        s for s, r in zip(sessions, spans, strict=True) if any((b - a).days > 100 for a, b in r)
    ]
    # the long window is read whole on the first session and after a partition behind it moved
    # (the late filing's new one, the restated one); every other session reads only what is new
    assert long == [date(2026, 9, 30), date(2026, 10, 6), date(2026, 10, 8)]
