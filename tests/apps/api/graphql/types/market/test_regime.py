"""``Query.regime`` and ``Query.market`` over the golden API store (ADR 0047): the market groups
are not computed there yet, so the regime is UNKNOWN with its reason, every indicator card is
served with its text and UNKNOWN value, the bands are one UNKNOWN band, and a market feature
name outside the catalogue is an UNKNOWN_FEATURE error."""

from typing import Any

from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import END, PREVIOUS

REGIME = """query R($date: Date) {
  regime(date: $date) {
    session label plainLabel headline unknownReason { code detail }
    scores { macroRisk { value unknown { code } } marketStress { value unknown { code } }
             fragility { value unknown { code } } }
    sizing { label multiplier enabled unknownMultiplier multipliers { label multiplier }
             screeners { screenerId name enabled pauseIn } }
    indicators { key pace plainName technicalName oneLiner whyItMatters whatOnMeans
      before { episode line } leadTime falseAlarms links { title url } feature
      value unknown { code } format status changed }
  }
}"""
BANDS = """query B($start: Date!, $end: Date!, $date: Date) {
  regime(date: $date) { bands(start: $start, end: $end) { start end label } }
}"""
EPISODES = """query E($date: Date) {
  regime(date: $date) {
    episodes { key name kind peak trough recovered spxDrawdown nasdaqDrawdown recession
               nberStart nberEnd cause notes knownFrom }
    recessions { start end announcedStart announcedEnd }
  }
}"""
HISTORY = """query H($names: [String!]!, $start: Date!, $end: Date!, $points: Int, $date: Date) {
  market(date: $date) {
    history(names: $names, start: $start, end: $end, points: $points) {
      name bucketSessions points { session value } segments { start end value }
    }
  }
}"""
MARKET = """query M($names: [String!]!, $date: Date) {
  market(date: $date) { session marketId features(names: $names) { name value } }
}"""


def _data(body: dict[str, Any]) -> dict[str, Any]:
    assert "errors" not in body, body
    data: dict[str, Any] = body["data"]
    return data


def test_the_regime_is_unknown_until_it_is_computed(graph: Graph) -> None:
    regime = _data(graph(REGIME, {"date": END.isoformat()}))["regime"]
    assert (regime["session"], regime["label"]) == (END.isoformat(), "UNKNOWN")
    assert (regime["plainLabel"], regime["headline"]) == ("Not computed yet", "Not computed yet")
    assert regime["unknownReason"]["code"] == "NO_PARTITION"  # the groups exist, no rows yet
    sizing = regime["sizing"]
    assert (sizing["label"], sizing["multiplier"], sizing["enabled"]) == ("UNKNOWN", None, False)
    assert sizing["unknownMultiplier"] == 0.0  # fail closed
    assert [(m["label"], m["multiplier"]) for m in sizing["multipliers"]] == [
        ("CALM", 1.0), ("CAUTION", 0.75), ("STRESS", 0.5), ("CRISIS", 0.25)
    ]  # fmt: skip
    vrp = next(g for g in sizing["screeners"] if g["screenerId"] == "vrp_scanner")
    assert vrp["pauseIn"] == ["STRESS", "CRISIS"] and not vrp["enabled"]  # the preset's, gate off
    assert regime["scores"]["fragility"] == {
        "value": None, "unknown": {"code": "NO_PARTITION"},
    }  # fmt: skip
    cards = regime["indicators"]
    assert len(cards) == 8 and cards[0]["key"] == "curve_10y3m"
    first = cards[0]
    assert first["feature"] == "market.regime_indicators@v1.curve_10y3m"
    assert (first["value"], first["format"], first["status"], first["changed"]) == (
        None, "PERCENT", "UNKNOWN", None,
    )  # fmt: skip
    assert first["unknown"]["code"] == "NO_PARTITION"
    assert first["plainName"] and first["whyItMatters"] and first["technicalName"]
    assert [b["episode"] for b in first["before"]] == ["2008", "2020", "2022"]
    assert all(link["url"].startswith("https://") for link in first["links"])


def test_the_bands_are_unknown_sessions_merged(graph: Graph) -> None:
    body = graph(BANDS, {"start": PREVIOUS.isoformat(), "end": END.isoformat()})
    bands = _data(body)["regime"]["bands"]
    assert bands == [{"start": PREVIOUS.isoformat(), "end": END.isoformat(), "label": "UNKNOWN"}]


def test_a_window_past_the_session_is_an_error(graph: Graph) -> None:
    body = graph(
        BANDS, {"start": PREVIOUS.isoformat(), "end": END.isoformat(), "date": PREVIOUS.isoformat()}
    )
    assert body["errors"] and "after the session" in body["errors"][0]["message"]


def test_the_market_values_by_name_are_checked_against_the_market_catalogue(graph: Graph) -> None:
    market = _data(graph(MARKET, {"names": []}))["market"]
    assert market["marketId"] == "MKT:US" and market["features"] == []
    body = graph(MARKET, {"names": ["market.nope@v1.x"]})
    assert body["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"


def test_the_episodes_and_recessions_are_those_the_session_knew(graph: Graph) -> None:
    regime = _data(graph(EPISODES, {"date": END.isoformat()}))["regime"]
    episodes = {e["key"]: e for e in regime["episodes"]}
    assert len(episodes) == 11 and "tariffs_2025" not in episodes  # its trough is in 2025
    assert episodes["covid_2020"]["name"] == "Covid crash, early 2020"
    assert episodes["covid_2020"]["recovered"] == "2020-08-18"
    assert episodes["hikes_2022"]["recovered"] is None  # regained only in 2024
    assert episodes["gfc_2007"]["spxDrawdown"] == -0.57 and episodes["gfc_2007"]["recession"]
    assert [r["start"] for r in regime["recessions"]][-1] == "2020-02-01"
    assert regime["recessions"][-1]["announcedEnd"] == "2021-07-19"
    old = _data(graph(EPISODES, {"date": PREVIOUS.isoformat()}))["regime"]
    assert len(old["episodes"]) == 11  # the same on the previous session


def test_the_history_of_a_stored_market_field(graph: Graph) -> None:
    variables = {"start": PREVIOUS.isoformat(), "end": "2030-01-01", "date": END.isoformat()}
    flag = _data(graph(HISTORY, {**variables, "names": ["market.regime@v2.label"]}))
    [label] = flag["market"]["history"]
    assert label["segments"] == [
        {"start": PREVIOUS.isoformat(), "end": END.isoformat(), "value": "UNKNOWN"}
    ]  # `end` is cut to the session; nothing is stored, so one UNKNOWN run
    assert label["points"] == [] and label["bucketSessions"] == 1
    number = _data(graph(HISTORY, {**variables, "names": ["market.regime@v2.macro_risk"]}))
    [score] = number["market"]["history"]
    assert score["points"] == [{"session": PREVIOUS.isoformat(), "value": None}]  # one gap
    assert score["segments"] == []


def test_a_history_of_a_computed_or_unknown_name_is_refused(graph: Graph) -> None:
    variables = {"start": PREVIOUS.isoformat(), "end": END.isoformat()}
    body = graph(HISTORY, {**variables, "names": ["feature.anything"]})
    assert body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
    assert "feature.* expression" in body["errors"][0]["message"]
    body = graph(HISTORY, {**variables, "names": ["market.nope@v1.x"]})
    assert body["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    body = graph(HISTORY, {**variables, "names": [], "points": 1})
    assert body["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
