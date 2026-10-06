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
    sizing { label multiplier }
    indicators { key pace plainName technicalName oneLiner whyItMatters whatOnMeans
      before { episode line } leadTime falseAlarms links { title url } feature
      value unknown { code } format status changed }
  }
}"""
BANDS = """query B($start: Date!, $end: Date!, $date: Date) {
  regime(date: $date) { bands(start: $start, end: $end) { start end label } }
}"""
MARKET = """query M($names: [String!]!, $date: Date) {
  market(date: $date) { session marketId features(names: $names) { name value } }
}"""


def _data(body: dict[str, Any]) -> dict[str, Any]:
    assert "errors" not in body, body
    data: dict[str, Any] = body["data"]
    return data


def test_the_regime_is_unknown_until_the_groups_exist(graph: Graph) -> None:
    regime = _data(graph(REGIME, {"date": END.isoformat()}))["regime"]
    assert (regime["session"], regime["label"]) == (END.isoformat(), "UNKNOWN")
    assert (regime["plainLabel"], regime["headline"]) == ("Not computed yet", "Not computed yet")
    assert regime["unknownReason"]["code"] == "NOT_IN_CATALOGUE"
    assert regime["sizing"] == {"label": "UNKNOWN", "multiplier": None}
    assert regime["scores"]["fragility"] == {
        "value": None, "unknown": {"code": "NOT_IN_CATALOGUE"},
    }  # fmt: skip
    cards = regime["indicators"]
    assert len(cards) == 8 and cards[0]["key"] == "curve_10y3m"
    first = cards[0]
    assert first["feature"] == "market.regime_indicators@v1.curve_10y3m"
    assert (first["value"], first["format"], first["status"], first["changed"]) == (
        None, None, "UNKNOWN", None,
    )  # fmt: skip
    assert first["unknown"]["code"] == "NOT_IN_CATALOGUE"
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
