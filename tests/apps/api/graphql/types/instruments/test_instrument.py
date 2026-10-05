"""The Explore detail pane over ``POST /graphql`` on the golden API store: an instrument's
events, option chain and quotes, ETF holdings, price and feature series, each for the request's
session (chains exactly that session, holdings as of the issuer's date it sees), through the
request's dataloaders (a batch of instruments reads each once)."""

from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import END, PREVIOUS

EVENTS = """query($key: String!, $start: Date, $end: Date) {
  instrument(key: $key) { events(start: $start, end: $end) { table kind date ts values } }
}"""
CHAIN = """query($key: String!, $expiry: Date!, $date: Date) {
  instrument(key: $key, date: $date) {
    features(names: ["rollup.iv30@v1.iv30"]) { value }
    chain {
      underlyingId session status expiries { date days } strikes
      quotes(expiry: $expiry) { instrumentId expiry right strike bid ask iv delta openInterest }
    }
  }
}"""
HOLDINGS = """query($key: String!, $top: Int, $date: Date) {
  instrument(key: $key, date: $date) {
    isEtf
    holdings(top: $top) {
      fundId asOf source total
      items { rank name symbol instrumentId weight assetClass instrument { symbol } }
    }
  }
}"""
PRICES = """query($key: String!, $start: Date!, $end: Date, $adjustment: Adjustment) {
  instrument(key: $key) {
    prices(start: $start, end: $end, adjustment: $adjustment) {
      instrumentId adjustment start end bars { session open high low close volume vwap }
    }
  }
}"""
SERIES = """query($key: String!, $names: [FeatureName!]!, $start: Date!) {
  instrument(key: $key) { series(names: $names, start: $start) { names start end points {
    session values } } }
}"""
CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"


def test_events_by_event_date_across_tables(graph: Graph) -> None:
    body = graph(EVENTS, {"key": "AAA"})
    assert "errors" not in body
    events = body["data"]["instrument"]["events"]
    assert [(e["table"], e["kind"]) for e in events] == [
        ("events/split", "split"),
        ("events/dividend", "dividend"),
    ]
    assert events[0]["date"] == "2022-06-01" and events[0]["values"]["ratio"] == 2.0
    assert "run_id" not in events[0]["values"]  # point-in-time stamps are not values
    later = graph(EVENTS, {"key": "AAA", "start": "2022-07-01"})["data"]["instrument"]["events"]
    assert [e["kind"] for e in later] == ["dividend"]
    none = graph(EVENTS, {"key": "AAA", "end": "2022-05-01"})["data"]["instrument"]["events"]
    assert none == []


def test_the_chain_for_the_session_with_one_expiry_of_quotes(graph: Graph) -> None:
    body = graph(CHAIN, {"key": "AAA", "expiry": "2022-12-23"})
    assert "errors" not in body
    instrument = body["data"]["instrument"]
    assert instrument["features"] == [{"value": 0.24}]  # our IV30: a feature, not a chain field
    chain = instrument["chain"]
    assert (chain["underlyingId"], chain["session"], chain["status"]) == (
        "EQ:AAA",
        END.isoformat(),
        "OK",
    )
    assert chain["expiries"] == [
        {"date": "2022-12-23", "days": 30},
        {"date": "2023-01-22", "days": 60},
    ]
    assert chain["strikes"][0] == 80.0
    quotes = chain["quotes"]
    assert len(quotes) == 9 * 2 and {q["expiry"] for q in quotes} == {"2022-12-23"}
    assert [(q["strike"], q["right"]) for q in quotes[:2]] == [(80.0, "C"), (80.0, "P")]
    assert quotes[0]["instrumentId"].endswith("C80")


def test_no_chain_for_the_session_is_null_never_an_older_one(graph: Graph) -> None:
    other = graph(CHAIN, {"key": "BBB", "expiry": "2022-12-23"})
    assert "errors" not in other and other["data"]["instrument"]["chain"] is None
    before = graph(CHAIN, {"key": "AAA", "expiry": "2022-12-23", "date": PREVIOUS.isoformat()})
    assert "errors" not in before and before["data"]["instrument"]["chain"] is None
    gone = graph(CHAIN, {"key": "AAA", "expiry": "2022-12-30"})["data"]["instrument"]["chain"]
    assert gone["quotes"] == []  # an expiry not listed: no quotes


def test_etf_holdings_as_of_the_issuer_date_with_links(graph: Graph) -> None:
    body = graph(HOLDINGS, {"key": "bull", "top": 4})
    assert "errors" not in body
    holdings = body["data"]["instrument"]["holdings"]
    assert (holdings["fundId"], holdings["asOf"], holdings["source"], holdings["total"]) == (
        "EQ:BULL",
        "2022-11-22",
        "test",
        40,
    )
    items = holdings["items"]
    assert [(i["rank"], i["symbol"], i["instrumentId"]) for i in items] == [
        (1, "AAA", "EQ:AAA"),
        (2, "BBB", "EQ:BBB"),
        (3, "CAT", None),  # printed with a ticker the universe does not have
        (4, None, None),  # cash: name only
    ]
    assert items[0]["instrument"] == {"symbol": "AAA"} and items[2]["instrument"] is None
    assert items[0]["weight"] == 0.25 and items[0]["assetClass"] == "Equity"
    default = graph(HOLDINGS, {"key": "BULL"})["data"]["instrument"]["holdings"]
    assert len(default["items"]) == 10  # the top ten by default
    every = graph(HOLDINGS, {"key": "BULL", "top": 100})["data"]["instrument"]["holdings"]
    assert "Old Holding" not in {i["name"] for i in every["items"]}  # the latest read wins


def test_no_holdings_for_a_stock_and_top_is_bounded(graph: Graph) -> None:
    stock = graph(HOLDINGS, {"key": "AAA"})["data"]["instrument"]
    assert (stock["isEtf"], stock["holdings"]) == (False, None)
    bad = graph(HOLDINGS, {"key": "BULL", "top": 0})
    assert bad["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
    over = graph(HOLDINGS, {"key": "BULL", "top": 1001})
    assert over["errors"][0]["extensions"]["code"] == "BAD_REQUEST"


def test_prices_over_an_explicit_window_split_adjusted_unless_asked(graph: Graph) -> None:
    window = {"key": "AAA", "start": "2022-05-27", "end": "2022-06-02"}
    adjusted = graph(PRICES, window)["data"]["instrument"]["prices"]
    raw = graph(PRICES, {**window, "adjustment": "NONE"})["data"]["instrument"]["prices"]
    assert (adjusted["adjustment"], raw["adjustment"]) == ("SPLITS", "NONE")
    before = [b for b in adjusted["bars"] if b["session"] < "2022-06-01"]
    raw_before = [b for b in raw["bars"] if b["session"] < "2022-06-01"]
    assert before and before[0]["close"] == raw_before[0]["close"] / 2
    to_session = graph(PRICES, {"key": "AAA", "start": "2022-11-01"})["data"]["instrument"]
    assert to_session["prices"]["end"] == END.isoformat()  # end: the session's date
    assert to_session["prices"]["bars"][-1]["session"] == END.isoformat()
    empty = graph(PRICES, {"key": "AAA", "start": "2010-01-01", "end": "2010-02-01"})
    assert empty["data"]["instrument"]["prices"]["bars"] == []


def test_feature_series_per_stored_session(graph: Graph) -> None:
    body = graph(SERIES, {"key": "AAA", "names": [CLOSE, HV20], "start": "2022-11-01"})
    assert "errors" not in body
    series = body["data"]["instrument"]["series"]
    assert (series["names"], series["end"]) == ([CLOSE, HV20], END.isoformat())
    assert [p["session"] for p in series["points"]] == [PREVIOUS.isoformat(), END.isoformat()]
    assert series["points"][1]["values"][0] == 101.0
    names = ["feature.liquidity_class"]
    label = graph(SERIES, {"key": "BBB", "names": names, "start": "2022-11-01"})
    points = label["data"]["instrument"]["series"]["points"]
    assert [p["values"] for p in points] == [["UNKNOWN"], ["MEDIUM"]]


def test_feature_series_refuses_unknown_and_instrument_names(graph: Graph) -> None:
    bad = graph(SERIES, {"key": "AAA", "names": ["rollup.nope@v1.x"], "start": "2022-11-01"})
    assert bad["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    fact = graph(SERIES, {"key": "AAA", "names": ["instrument.sector"], "start": "2022-11-01"})
    assert fact["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
