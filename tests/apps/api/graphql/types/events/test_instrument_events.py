"""``Instrument.eventStudy`` over ``POST /graphql`` on the golden API store (no macro calendar
or filings stored there: those parts are gaps), for the request's session."""

from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import END

STUDY = """query($key: String!, $days: Int) {
  instrument(key: $key) { eventStudy(days: $days) {
    instrumentId session days months
    ahead { date time kind label name subjectId source knownFrom }
    filings { accepted form items label }
    ladder { expiry days clear marked spans { date kind label } }
    reference { instrumentId symbol kind source status }
    gaps { instrumentId part unknown { code detail } }
  } }
}"""


def test_what_is_coming_for_a_stock(graph: Graph) -> None:
    body = graph(STUDY, {"key": "AAA"})
    assert "errors" not in body
    study = body["data"]["instrument"]["eventStudy"]
    assert (study["instrumentId"], study["session"], study["days"], study["months"]) == (
        "EQ:AAA", END.isoformat(), 90, 24,
    )  # fmt: skip
    assert [(e["date"], e["kind"], e["label"]) for e in study["ahead"]] == [
        ("2022-12-01", "own_earnings", "Earnings"),
        ("2022-12-16", "market_structure", "Quarterly expiry"),
        ("2022-12-30", "market_structure", "Quarter end"),
        ("2023-01-20", "market_structure", "Monthly expiry"),
        ("2023-02-17", "market_structure", "Monthly expiry"),
    ]
    assert study["ahead"][0]["time"] == "pre_market" and study["ahead"][0]["knownFrom"] is None
    assert [(r["expiry"], r["days"], r["clear"], r["marked"]) for r in study["ladder"]] == [
        ("2022-12-23", 30, False, False), ("2023-01-22", 60, False, False),
    ]  # fmt: skip
    assert [s["label"] for s in study["ladder"][0]["spans"]] == ["Earnings", "Quarterly expiry"]
    assert study["reference"] is None and study["filings"] == []
    gaps = {g["part"]: g["unknown"]["code"] for g in study["gaps"]}
    assert gaps == {"macro_release": "NO_PARTITION", "filings": "NO_ROW"}


def test_days_is_capped(graph: Graph) -> None:
    body = graph(STUDY, {"key": "AAA", "days": 400})
    assert body["errors"][0]["message"] == "days: at most 366, got 400"
