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
    scores { macroRisk { value unknown { code } feature coverageFeature threshold }
             marketStress { value unknown { code } feature coverageFeature threshold }
             fragility { value unknown { code } } }
    sizing { label multiplier enabled unknownMultiplier multipliers { label multiplier }
             screeners { screenerId name enabled pauseIn } }
    indicators { key pace plainName technicalName oneLiner whyItMatters whatOnMeans
      before { episode line } leadTime falseAlarms links { title url } feature
      value unknown { code } format status changed range { min max } threshold direction
      how { text url } verdictFeature
      sources { label series cadence releaseLagDays url licence terms lastObservation
                vintageDate vintageKind firstVintage active } }
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


def test_each_card_explains_its_value_from_code_config_and_lineage(graph: Graph) -> None:
    regime = _data(graph(REGIME, {"date": END.isoformat()}))["regime"]
    curve = regime["indicators"][0]
    assert curve["range"] == {"min": -0.02, "max": 0.04}
    assert (curve["threshold"], curve["direction"]) == (0.0, "LOWER_IS_RISK")
    assert curve["verdictFeature"] == "market.regime_indicators@v1.curve_10y3m_on"
    linked = [(p["text"], p["url"]) for p in curve["how"] if p["url"]]
    assert linked == [
        ("10-year Treasury yield", "https://fred.stlouisfed.org/series/DGS10"),
        ("3-month bill", "https://fred.stlouisfed.org/series/DGS3MO"),
    ]
    treasury, fred = curve["sources"]
    assert (treasury["label"], treasury["series"], treasury["releaseLagDays"]) == (
        "Treasury daily par yield curve", None, None,
    )  # fmt: skip
    assert (fred["label"], fred["series"], fred["cadence"]) == ("FRED T10Y3M", "T10Y3M", "daily")
    assert fred["url"] == "https://fred.stlouisfed.org/series/T10Y3M" and fred["terms"]
    assert fred["lastObservation"] is None and fred["firstVintage"] is None  # none stored here
    assert treasury["active"] and fred["active"]  # no per-session switch on this card
    spx = next(c for c in regime["indicators"] if c["key"] == "spx_trend_200d")
    assert [s["active"] for s in spx["sources"]] == [False, False, False]  # no source stored
    macro = regime["scores"]["macroRisk"]
    assert (macro["feature"], macro["coverageFeature"], macro["threshold"]) == (
        "market.regime@v3.macro_risk", "market.regime@v3.macro_coverage", 50.0,
    )  # fmt: skip


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
