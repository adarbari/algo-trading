"""The cross-name event calendar: every session of the window as a day, the names' own events
on their rows and the market-wide ones once; names from the caller and, with ``scope``, the
site list (unknown symbols returned); ids the snapshot lacks are listed as missing."""

from datetime import date

from algotrade.config.user import UserContext
from algotrade.services.read.context import open_context
from algotrade.services.read.events.ahead import MACRO_RELEASE, OWN_EARNINGS, REFERENCE_EARNINGS
from algotrade.services.read.events.event_calendar import CalendarName, load_event_calendar
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.events.conftest import D1, REPORT, context, store_with

SCOPE = {("site", "events", "scope"): {"name": [
    {"symbol": s, "added_on": date(2026, 10, 1)} for s in ("AAAU", "NOPE")
]}}  # fmt: skip


def test_names_by_day_and_the_market_once() -> None:
    found = load_event_calendar(context(store_with()), ["EQ:AAA", "EQ:AAAU", "EQ:ZZZ"], 30)
    assert (found.session, found.end) == (D1, date(2026, 10, 31))
    assert found.names == (CalendarName("EQ:AAA", "AAA"), CalendarName("EQ:AAAU", "AAAU"))
    assert found.missing == ("EQ:ZZZ",) and found.unresolved == ()
    days = {d.date: d for d in found.days}
    assert days[D1].is_session and days[D1].events == ()  # an empty session is still a day
    assert date(2026, 10, 3) not in days  # a Saturday with nothing on it
    report = [(e.instrument_id, e.symbol, e.event.kind) for e in days[REPORT].events]
    assert report == [("EQ:AAA", "AAA", OWN_EARNINGS), ("EQ:AAAU", "AAAU", REFERENCE_EARNINGS)]
    cpi = days[date(2026, 10, 14)].events
    assert [(e.instrument_id, e.event.kind, e.event.label) for e in cpi] == [
        (None, MACRO_RELEASE, "CPI")
    ]
    assert {(g.instrument_id, g.part) for g in found.gaps} == {("EQ:AAAU", OWN_EARNINGS)}


def test_the_scope_list_adds_its_names() -> None:
    reader = store_with()
    ctx = open_context(reader, MemoryConfigStore(SCOPE), UserContext("local"), None)
    found = load_event_calendar(ctx, ["EQ:AAA"], 10, scope=True)
    assert [n.symbol for n in found.names] == ["AAA", "AAAU"]
    assert found.unresolved == ("NOPE",)
