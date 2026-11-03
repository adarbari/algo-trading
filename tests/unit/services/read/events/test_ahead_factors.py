"""The dossier on the forward calendar (EV8a, ADR 0050): dated occurrences of the latest import
known by the session join ``load_ahead`` as ``factor`` events (past ones and a retired factor's
excluded), watch windows are a separate list, and a store with no dossier at all is a gap."""

from datetime import date

from algotrade.services.read.events.ahead import FACTOR, load_ahead
from algotrade.services.read.events.event_calendar import load_event_calendar
from algotrade.services.read.events.instrument_events import load_instrument_events
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.events.conftest import (
    D0,
    D1,
    context,
    factor_row,
    occurrence_row,
    store_with,
    write_dossier,
)

AAA = "EQ:AAA"
FDA = date(2026, 10, 20)


def dossier(writer: StoreWriter) -> None:
    write_dossier(
        writer,
        D1,
        "dossier-aaa",
        [factor_row("hbm", AAA, D1), factor_row("old", AAA, D1, "retired", "litigation")],
        [
            occurrence_row("hbm", FDA, D1, "FDA advisory committee"),
            occurrence_row("hbm", date(2026, 9, 24), D1, "SK Hynix results"),  # behind us
            occurrence_row("old", date(2026, 10, 22), D1, "Court date"),  # a retired factor
            occurrence_row("hbm", date(2026, 12, 1), D1, "Korean export data", date(2026, 12, 20)),
            occurrence_row("hbm", date(2026, 9, 1), D1, "Old window", date(2026, 9, 10)),
            occurrence_row("hbm", date(2027, 6, 1), D1, "Far window", date(2027, 6, 20)),
        ],
    )


def test_dated_occurrences_join_the_ahead_events_and_watch_windows_stay_apart() -> None:
    ahead = load_ahead(context(store_with(dossier)), [AAA], date(2026, 12, 31))
    factors = [e for e in ahead.by_name[AAA] if e.kind == FACTOR]
    assert [(e.date, e.label, e.factor_id, e.factor_kind) for e in factors] == [
        (FDA, "FDA advisory committee", "hbm", "commodity")
    ]
    assert (factors[0].subject_id, factors[0].source, factors[0].known_from) == (AAA, "dossier", D1)
    assert [(w.label, w.expected_from, w.expected_to) for w in ahead.watch[AAA]] == [
        ("Korean export data", date(2026, 12, 1), date(2026, 12, 20))
    ]
    assert ahead.market_gaps == () and ahead.watch.keys() == {AAA}


def test_a_session_before_the_import_sees_no_dossier_events() -> None:
    found = load_instrument_events(context(store_with(dossier), D0), [AAA])[AAA]
    assert [e for e in found.ahead if e.kind == FACTOR] == []
    assert found.watch == ()


def test_the_instrument_and_the_calendar_both_show_the_factor_event() -> None:
    reader = store_with(dossier)
    found = load_instrument_events(context(reader), [AAA])[AAA]
    assert [e.label for e in found.ahead if e.kind == FACTOR] == ["FDA advisory committee"]
    assert [w.label for w in found.watch] == ["Korean export data"]
    calendar = load_event_calendar(context(reader), [AAA], 30)
    day = next(d for d in calendar.days if d.date == FDA)
    assert [(e.instrument_id, e.symbol, e.event.factor_id) for e in day.events] == [
        (AAA, "AAA", "hbm")
    ]
    assert calendar.watch == ()  # the window opens on 2026-12-01, past the 30 days


def test_a_session_before_every_import_is_a_market_wide_gap() -> None:
    # the store's only dossier (an unlisted name) was stored on D0; the session before it
    found = load_ahead(context(store_with(), date(2026, 9, 29)), [AAA], date(2026, 10, 30))
    gaps = {g.part: (g.instrument_id, g.unknown.code.value) for g in found.market_gaps}
    assert gaps["factor"] == (None, "NO_PARTITION")
