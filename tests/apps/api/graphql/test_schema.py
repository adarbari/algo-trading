"""The schema at ``POST /graphql``: the committed snapshot is fresh (READ 6), the session and
an instrument's identity and feature values for exactly the session, GET off, GraphiQL only in
debug, and an empty store answers nulls, not errors."""

from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade.services.read.session import NewerSession, NewerState
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.graphql.schema import sdl
from algotrade_api.graphql.types.session import NewerSession as GraphNewer
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import FACTS, Graph
from tests.helpers.api_store import END, PREVIOUS, as_user, store_over

REPO = Path(__file__).resolve().parents[4]
CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"
NEXT = "rollup.earnings@v1.next_earnings_date"
TIME = "rollup.earnings@v1.earnings_time"


def test_committed_schema_is_up_to_date() -> None:
    committed = (REPO / "apps" / "api" / "schema.graphql").read_text()
    assert committed == sdl(), "run scripts/export_graphql_schema.py and commit the result"


def test_an_instrument_and_its_values_for_the_latest_session(graph: Graph) -> None:
    body = graph(FACTS, {"key": "AAA", "names": [CLOSE, NEXT, TIME, "instrument.sector"]})
    assert "errors" not in body
    session, instrument = body["data"]["session"], body["data"]["instrument"]
    assert (session["date"], session["isLatest"], session["preSnapshot"]) == (
        END.isoformat(), True, False,
    )  # fmt: skip
    assert instrument["instrumentId"] == "EQ:AAA"
    assert (instrument["symbol"], instrument["name"], instrument["isEtf"]) == (
        "AAA",
        "AAA Corp",
        False,
    )
    assert instrument["description"] == "AAA makes widgets."
    values = {v["name"]: v for v in instrument["features"]}
    assert [v["name"] for v in instrument["features"]] == [CLOSE, NEXT, TIME, "instrument.sector"]
    assert values[CLOSE]["value"] == 101.0 and values[CLOSE]["info"]["format"] == "CURRENCY"
    assert values[NEXT]["value"] == "2022-12-01" and values[NEXT]["info"]["format"] == "DATE"
    assert values[TIME]["info"]["format"] == "CATEGORY"
    assert values["instrument.sector"]["value"] == "Technology"


def test_an_earlier_session_never_shows_a_later_or_older_partition(graph: Graph) -> None:
    body = graph(FACTS, {"key": "CCC", "names": [CLOSE, HV20, NEXT], "date": PREVIOUS.isoformat()})
    assert "errors" not in body
    assert body["data"]["session"]["date"] == PREVIOUS.isoformat()
    assert body["data"]["session"]["unavailable"]
    values = {v["name"]: v for v in body["data"]["instrument"]["features"]}
    assert values[CLOSE]["value"] == 102.0  # PREVIOUS's close for CCC (99 + 3)
    assert values[HV20]["unknown"]["code"] == "NULL"
    assert values[NEXT]["value"] is None
    assert values[NEXT]["unknown"] == {"code": "NO_PARTITION", "kind": "SYSTEM"}
    assert values[NEXT]["info"] == {"format": "DATE", "unit": "date"}


def test_no_such_instrument_is_null_not_an_error(graph: Graph) -> None:
    body = graph(FACTS, {"key": "NOPE", "names": [CLOSE]})
    assert body["data"]["instrument"] is None and "errors" not in body


def test_an_empty_store_answers_nulls() -> None:
    store = store_over(MemoryBackend(), MemoryConfigStore({}), UserContext("local"))
    client = TestClient(
        create_app(ApiSettings("memory://", "config"), store, authenticator=as_user())
    )
    body = client.post("/graphql", json={"query": FACTS, "variables": {"key": "A", "names": []}})
    assert body.json() == {"data": {"session": None, "instrument": None}}


def test_get_is_off_and_graphiql_only_in_debug(client: TestClient) -> None:
    assert client.get("/graphql").status_code == 404
    store = store_over(MemoryBackend(), MemoryConfigStore({}), UserContext("local"))
    debug = TestClient(
        create_app(ApiSettings("memory://", "config", debug=True), store, authenticator=as_user())
    )
    page = debug.get("/graphql", headers={"accept": "text/html"})
    assert page.status_code == 200 and "graphiql" in page.text.lower()
    query = debug.get("/graphql", params={"query": "{ session { date } }"})
    assert query.status_code != 200 or "errors" in query.json()  # queries never via GET


def test_a_session_discloses_its_workflow_state_and_the_newer_incomplete_session(
    graph: Graph,
) -> None:
    """ADR 0062: the golden store's latest session is complete and nothing is newer;
    ``Session.of`` carries a newer session's state and public kind."""
    served = graph("{ session { complete newer { date } } }")["data"]["session"]
    assert served == {"complete": True, "newer": None}
    mapped = GraphNewer.of(NewerSession(END, NewerState.FAILED_RETRYING, UnavailableKind.SYSTEM))
    assert (mapped.date, mapped.state.value, mapped.kind) == (
        END,
        "FAILED_RETRYING",
        UnavailableKind.SYSTEM,
    )
