"""The expiry ladder: the listed expiries 7 to 90 days out, each spanning the events on or
before it (an after-close report on the expiry date is inside it); clear when it spans none
but market-structure days."""

from datetime import date

from algotrade.services.read.events.ahead import MARKET_STRUCTURE, OWN_EARNINGS, AheadEvent
from algotrade.services.read.events.ladder import ladder
from algotrade.services.read.instruments.chains import OptionExpiry

REPORT = date(2026, 10, 23)


def _event(day: date, kind: str, time: str = "close") -> AheadEvent:
    return AheadEvent(day, time, kind, kind, kind, None, "test", None)


def test_the_spanning_rule_and_the_clear_state() -> None:
    expiries = [OptionExpiry(date(2026, 10, 23), 22), OptionExpiry(date(2026, 10, 6), 5),
                OptionExpiry(date(2026, 10, 16), 15), OptionExpiry(date(2026, 10, 8), 7),
                OptionExpiry(date(2026, 12, 31), 91)]  # fmt: skip
    expiry_day = _event(date(2026, 10, 16), MARKET_STRUCTURE)
    report = _event(REPORT, OWN_EARNINGS, "after_hours")
    rungs = ladder(expiries, [expiry_day, report])
    assert [(r.expiry, r.days) for r in rungs] == [
        (date(2026, 10, 8), 7), (date(2026, 10, 16), 15), (REPORT, 22),
    ]  # fmt: skip
    assert [r.spans for r in rungs] == [(), (expiry_day,), (expiry_day, report)]
    assert [r.clear for r in rungs] == [True, True, False]  # the report after the close counts
    assert [r.marked for r in rungs] == [False, True, False]  # the last clear rung


def test_no_clear_rung_none_marked() -> None:
    rungs = ladder([OptionExpiry(REPORT, 22)], [_event(REPORT, OWN_EARNINGS)])
    assert [(r.clear, r.marked) for r in rungs] == [(False, False)]


def test_no_expiries_no_rungs() -> None:
    assert ladder([], [_event(REPORT, OWN_EARNINGS)]) == ()
