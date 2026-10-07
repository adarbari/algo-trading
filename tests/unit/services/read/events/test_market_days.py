"""The market-structure days of a window by rule: the monthly expiries (quarterly in March,
June, September and December), the quarter ends and the Russell reconstitution in June, each
moved to the session before when the exchange is closed on the rule's day."""

from datetime import date

from algotrade.services.read.events.market_days import MarketDay, market_days


def test_a_quarter_with_the_reconstitution() -> None:
    found = market_days(date(2026, 5, 20), date(2026, 7, 31))
    assert [(d.date, d.label) for d in found] == [
        (date(2026, 6, 18), "Quarterly expiry"),  # the third Friday is Juneteenth
        (date(2026, 6, 26), "Russell reconstitution"),
        (date(2026, 6, 30), "Quarter end"),
        (date(2026, 7, 17), "Monthly expiry"),
    ]  # May's expiry (the 15th) is before the window
    assert found[2].name.startswith("Last session of Q2 2026")
    assert [(d.label, d.expiry) for d in found] == [
        ("Quarterly expiry", True),
        ("Russell reconstitution", False),
        ("Quarter end", False),
        ("Monthly expiry", True),
    ]  # only the option expiry days are flagged


def test_the_window_is_inclusive_and_spans_years() -> None:
    found = market_days(date(2026, 12, 18), date(2027, 1, 15))
    assert found == (
        MarketDay(date(2026, 12, 18), "Quarterly expiry", found[0].name, True),
        MarketDay(date(2026, 12, 31), "Quarter end", found[1].name, False),
        MarketDay(date(2027, 1, 15), "Monthly expiry", found[2].name, True),
    )
    assert market_days(date(2026, 10, 17), date(2026, 10, 31)) == ()
