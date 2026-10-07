"""``Query.eventCalendar`` over ``POST /graphql`` on the golden API store: the names' events by
day for the request's session, the market-wide ones once, the ids the snapshot lacks listed."""

from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import END

CALENDAR = """query($ids: [String!]!, $days: Int) {
  eventCalendar(instrumentIds: $ids, days: $days) {
    session end names { instrumentId symbol } missing unresolved
    days { date isSession events { instrumentId symbol event { kind label } } }
    gaps { instrumentId part unknown { code } }
  }
}"""


def test_the_event_calendar(graph: Graph) -> None:
    body = graph(CALENDAR, {"ids": ["EQ:AAA", "EQ:NOPE"], "days": 14})
    assert "errors" not in body
    calendar = body["data"]["eventCalendar"]
    assert (calendar["session"], calendar["end"]) == (END.isoformat(), "2022-12-07")
    assert calendar["names"] == [{"instrumentId": "EQ:AAA", "symbol": "AAA"}]
    assert calendar["missing"] == ["EQ:NOPE"] and calendar["unresolved"] == []
    days = {d["date"]: d for d in calendar["days"]}
    assert days["2022-12-01"]["events"] == [
        {
            "instrumentId": "EQ:AAA",
            "symbol": "AAA",
            "event": {"kind": "own_earnings", "label": "Earnings"},
        }
    ]
    assert "2022-11-24" not in days  # Thanksgiving, with nothing on it
    assert {(g["instrumentId"], g["part"]) for g in calendar["gaps"]} == {(None, "macro_release")}
