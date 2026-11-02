"""``Instrument.optionGrid`` over the golden API store: the union answers the grid or an
``Unknown`` with its code and public kind (never a cause to a trader), the cell union carries
derived figures only and the request is read for the session."""

from tests.apps.api.graphql.conftest import Graph

GRID = """query($key: String!, $date: Date) {
  instrument(key: $key, date: $date) {
    optionGrid {
      __typename
      ... on Unknown { code kind guideTerm cause { links { subject } } }
      ... on OptionGrid {
        underlyingId session pricedAt qKnown bands
        columns { bucket expiry days reportInside reportInsideUnknown { code } gap { code } }
        puts { __typename ... on GridCell { band strike delta mid roc yieldAnn } }
        calls { __typename ... on Unknown { code } }
      }
    }
  }
}"""


def test_the_grid_is_a_grid_or_an_unknown_with_its_code(graph: Graph) -> None:
    body = graph(GRID, {"key": "AAA"})
    assert "errors" not in body, body
    found = body["data"]["instrument"]["optionGrid"]
    assert found["__typename"] in ("OptionGrid", "Unknown")
    if found["__typename"] == "Unknown":  # no Treasury curve in the golden store: not r = 0
        assert found["code"] in ("NO_PARTITION", "NO_ROW") and found["kind"]
        # the golden store's caller is the local admin: the chain behind the gap, served by
        # AdminCause (a trader gets null there: tests/apps/api/graphql/test_causes.py)
        assert found["cause"]["links"][0]["subject"] == "rates/treasury"


def test_a_name_without_a_chain_for_the_session_is_an_unknown(graph: Graph) -> None:
    found = graph(GRID, {"key": "BBB"})["data"]["instrument"]["optionGrid"]
    assert found["__typename"] == "Unknown" and found["code"] in ("NO_PARTITION", "NO_ROW")


def test_the_schema_has_no_raw_quote_on_the_grid_types(graph: Graph) -> None:
    body = graph("""{ __type(name: "GridCell") { fields { name } } }""")
    names = {f["name"] for f in body["data"]["__type"]["fields"]}
    assert not names & {"bid", "ask", "last", "size"} and "mid" in names
