"""``load_event_scope`` (EV8): the effective list with where each entry came from, the dossier's
review date and the stale flag, removed names, the symbols the snapshot does not know, the other
names in scope, and the macro calendar's next 90 days."""

from collections.abc import Callable
from datetime import UTC, date, datetime

from algotrade.config.user import UserContext
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.event_scope.event_scope import load_event_scope
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.events.conftest import (
    D0,
    D1,
    factor_row,
    store_with,
    write_dossier,
)

AT = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
SITE = {
    "name": [
        {"symbol": s, "added_on": date(2026, 10, 6), "note": "site"}
        for s in ("AAA", "ETFX", "NOPE")
    ]
}
ADMIN = {
    "added": [{"symbol": "AAAU", "by": "arvinder", "at": AT, "note": "levered"}],
    "removed": [{"symbol": "ETFX", "by": "arvinder", "at": AT}],
}


def ctx(*writes: Callable[[StoreWriter], None], admin: bool = True) -> ReadContext:
    docs = {("site", "events", "scope"): SITE}
    if admin:
        docs[("admin", "events", "scope")] = ADMIN
    return open_context(store_with(*writes), MemoryConfigStore(docs), UserContext("local"))


def reviewed(known: date) -> Callable[[StoreWriter], None]:
    def write(writer: StoreWriter) -> None:
        write_dossier(writer, D0, "dossier-aaa", [factor_row("hbm", "EQ:AAA", known)], [])

    return write


def test_the_listed_names_with_their_source_review_and_the_rest() -> None:
    found = load_event_scope(ctx(reviewed(date(2026, 9, 20))))
    assert found.session == D1 and found.stale_days == 90 and found.macro_days == 90
    assert [(r.symbol, r.source, r.by) for r in found.names] == [
        ("AAA", "site", None),
        ("AAAU", "admin", "arvinder"),
    ]
    aaa, aaau = found.names
    assert aaa.reasons == ("list", "reference")  # AAAU, in the list, tracks it
    assert aaau.reasons == ("list",)
    assert (aaa.instrument_id, aaa.note) == ("EQ:AAA", "site")
    assert (aaau.at, aaau.note, aaau.added_on) == (AT, "levered", AT.date())
    assert aaa.last_review == date(2026, 9, 20) and aaa.stale is False  # 11 days before the session
    assert aaau.last_review is None and aaau.stale is True  # never reviewed
    assert found.unresolved == ("NOPE",)
    assert [(r.symbol, r.by, r.reasons) for r in found.removed] == [("ETFX", "arvinder", ())]
    assert aaa.moves is None  # two bars: not a year
    assert found.stale_count == 1  # AAAU, never reviewed


def test_a_review_older_than_ninety_days_is_stale() -> None:
    found = load_event_scope(ctx(reviewed(date(2026, 6, 1))))
    assert found.names[0].last_review == date(2026, 6, 1) and found.names[0].stale is True


def test_a_review_exactly_ninety_days_old_is_not_stale() -> None:
    found = load_event_scope(ctx(reviewed(date(2026, 7, 3))))  # D1 - 90 days
    assert found.names[0].stale is False


def test_the_macro_calendars_next_ninety_days() -> None:
    found = load_event_scope(ctx())
    assert found.macro_releases == 2 and found.macro_unknown is None  # CPI Oct 14, GDP Oct 29


def test_no_admin_document_lists_the_site_names() -> None:
    found = load_event_scope(ctx(admin=False))
    assert [r.symbol for r in found.names] == ["AAA", "ETFX"] and found.removed == ()
