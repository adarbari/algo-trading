"""``decode_filters`` reads the ``f`` string the web codec writes (ADR 0082 decision 4)."""

from algotrade.services.read.filtering.codec import decode_filters
from algotrade.services.read.filtering.masks import FilterInput, WindowUnit, Within


def test_each_body_kind_decodes_and_a_bang_switches_the_filter_off() -> None:
    got = decode_filters("decision:QUALIFIED,WATCH;dte:..14;rsi:30..70;!liq:risk;earn:..5s;lo:5..")
    assert got == [
        FilterInput("decision", values=["QUALIFIED", "WATCH"]),
        FilterInput("dte", max=14.0),
        FilterInput("rsi", min=30.0, max=70.0),
        FilterInput("liq", values=["risk"], active=False),
        FilterInput("earn", within=Within(5.0, WindowUnit.SESSIONS)),
        FilterInput("lo", min=5.0),
    ]


def test_percent_escapes_decode_and_malformed_entries_are_dropped_not_raised() -> None:
    got = decode_filters("a:x%2Cy;nocolon;b:1..x;c:%zz;d:..;a:again;e:ok")
    assert got == [FilterInput("a", values=["x,y"]), FilterInput("e", values=["ok"])]


def test_nothing_or_garbage_is_no_filter() -> None:
    assert decode_filters(None) == [] == decode_filters("")
