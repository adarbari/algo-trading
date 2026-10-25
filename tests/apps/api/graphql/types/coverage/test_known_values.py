"""``Query.knownCoverage``: the fundamentals share count known against the rows stored, admin
only (a trader gets FORBIDDEN: its causes name a source step), NOT_RUN for a session whose
records carry no breakdown."""

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import as_user

QUERY = """query($date: Date) { knownCoverage(date: $date) {
  session runId byType { securityType names rows known share } gaps { gap names }
  unknown { code kind }
} }"""


def test_the_breakdown_of_the_latest_session(graph: Graph) -> None:
    body = graph(QUERY)
    assert "errors" not in body
    found = body["data"]["knownCoverage"]
    assert found["session"] == "2022-11-23" and found["unknown"] is None
    etf = next(t for t in found["byType"] if t["securityType"] == "ETF")
    assert (etf["rows"], etf["known"], etf["share"]) == (4, 0, 0.0)  # rows stored, no value
    assert found["gaps"] == [{"gap": "BLANK_CHECK", "names": 1}]


def test_a_session_with_no_record_is_not_run(graph: Graph) -> None:
    body = graph(QUERY, {"date": "2022-11-22"})
    assert "errors" not in body
    found = body["data"]["knownCoverage"]
    assert found["unknown"]["code"] == "NOT_RUN" and found["byType"] == []


def test_a_trader_is_forbidden(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    app = create_app(
        ApiSettings("memory://", "config"),
        api_golden[0],
        authenticator=as_user("local", Role.TRADER),
    )
    body = TestClient(app).post("/graphql", json={"query": QUERY, "variables": {}}).json()
    assert body["data"]["knownCoverage"] is None
    assert body["errors"][0]["extensions"]["code"] == "FORBIDDEN"
