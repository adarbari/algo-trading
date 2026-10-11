"""``GET /files/edges/{id}/trades.csv`` (ADR 0064 decision 11) serves the rows ``Query.edgeTrades``
serves: the same basis, the same licence redaction (a personal score is its public kind to anyone
but the licence holder), the same withheld out-of-sample trades, the order the server sorts;
a ledger that cannot be read is a 404 naming a public kind, never a cause; the route is
authenticated like every other."""

import csv
import io
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import StubAuthenticator, store_over
from tests.helpers.rollup_store import write_bars
from tests.unit.services.read.edge_desk.conftest import store, trade
from tests.unit.services.read.edge_ledger.conftest import LEDGER, SESSION, USERS
from tests.unit.services.read.evaluation.conftest import DOCS, FROZEN, write_run

Make = Callable[..., TestClient]
GRAPH = """query T($id: String!, $period: TradePeriod!, $sort: TradeSort!, $desc: Boolean!) {
  edgeTrades(edgeId: $id, period: $period, sort: $sort, descending: $desc) {
    basis total oosHidden unknown { code kind }
    rows {
      instrumentId symbol { value unknown { kind } } status excludedReason
      score { value unknown { kind } } value { value }
    }
  }
}"""


def backend_with_run(trades: list[dict[str, Any]] | None = LEDGER) -> MemoryBackend:
    backend = MemoryBackend()
    write_bars(StoreWriter(backend), {"EQ:A": [1.0]}, end=SESSION)  # the session to read
    write_run(backend, "site1", FROZEN, 0.6, trades=trades)
    return backend


@pytest.fixture
def make() -> Callable[..., TestClient]:
    def build(user: str, role: Role, backend: MemoryBackend | None = None) -> TestClient:
        configs = MemoryConfigStore({**DOCS, ("site", "settings", "users"): USERS})
        app = create_app(
            ApiSettings("memory://", "config"),
            store_over(backend or backend_with_run(), configs, UserContext(user)),
            authenticator=StubAuthenticator(UserRecord(user, role)),
        )
        return TestClient(app)

    return build


def file_rows(client: TestClient, period: str = "all") -> list[dict[str, str]]:
    response = client.get("/files/edges/drift/trades.csv", params={"period": period})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(response.text)))


def graph_rows(client: TestClient, period: str, sort: str = "DECISION") -> list[dict[str, Any]]:
    body = client.post(
        "/graphql",
        json={
            "query": GRAPH,
            "variables": {"id": "drift", "period": period, "sort": sort, "desc": False},
        },
    ).json()
    assert "errors" not in body, body
    return body["data"]["edgeTrades"]["rows"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(("user", "role"), [("owner", Role.ADMIN), ("me", Role.TRADER)])
@pytest.mark.parametrize("period", ["all", "in_sample", "out_of_sample"])
def test_the_csv_has_the_rows_the_graph_serves(
    make: Make, user: str, role: Role, period: str
) -> None:
    client = make(user, role)
    from_file, from_graph = file_rows(client, period), graph_rows(client, period.upper())
    assert [r["instrument_id"] for r in from_file] == [r["instrumentId"] for r in from_graph]
    assert [r["status"] for r in from_file] == [r["status"] for r in from_graph]
    assert [r["excluded_reason"] for r in from_file] == [
        r["excludedReason"] or "" for r in from_graph
    ]
    for f, g in zip(from_file, from_graph, strict=True):
        unknown = g["score"]["unknown"]
        assert f["score"] == (unknown["kind"] if unknown else str(g["score"]["value"] or ""))
        # the store has no reference snapshot: the ticker is Unknown in both, never the id
        assert g["symbol"]["value"] is None and f["symbol"] == g["symbol"]["unknown"]["kind"]
        assert f["symbol"] != f["instrument_id"]


def test_a_personal_score_is_its_public_kind_in_the_file_for_anyone_but_the_holder(
    make: Make,
) -> None:
    mine = {r["instrument_id"]: r for r in file_rows(make("me", Role.TRADER))}
    assert mine["EQ:A"]["score"] == "LICENCE" and mine["EQ:A"]["value"] == "0.02"
    assert mine["EQ:B"]["score"] == "6.0"  # its recorded licence is open
    owner = {r["instrument_id"]: r for r in file_rows(make("owner", Role.ADMIN))}
    assert owner["EQ:A"]["score"] == "3.0"


def test_the_file_has_the_basis_only_and_keeps_excluded_picks(make: Make) -> None:
    rows = file_rows(make("owner", Role.ADMIN))
    assert {r["instrument_id"] for r in rows} == {"EQ:A", "EQ:B", "EQ:C", "EQ:D"}
    gone = next(r for r in rows if r["instrument_id"] == "EQ:C")
    assert (gone["status"], gone["excluded_reason"], gone["value"]) == (
        "excluded", "NO_ENTRY_BAR", ""
    )  # fmt: skip


def test_a_ledger_that_cannot_be_read_is_a_404_with_a_public_kind(make: Make) -> None:
    client = make("me", Role.TRADER, backend_with_run(trades=None))
    response = client.get("/files/edges/drift/trades.csv")
    assert response.status_code == 404
    assert "table" not in response.text and "run site1" not in response.text  # no cause
    assert client.get("/files/edges/nope/trades.csv").status_code == 404


def test_the_file_needs_the_caller_to_be_let_in() -> None:
    class Refuse:
        def authenticate(self, request: object) -> UserRecord:
            from algotrade_api.auth.protocol import UnauthenticatedError  # noqa: PLC0415

            raise UnauthenticatedError("no token")

    configs = MemoryConfigStore({**DOCS, ("site", "settings", "users"): USERS})
    app = create_app(
        ApiSettings("memory://", "config"),
        store_over(backend_with_run(), configs, UserContext("me")),
        authenticator=Refuse(),  # type: ignore[arg-type]
    )
    assert TestClient(app).get("/files/edges/drift/trades.csv").status_code == 401


def test_the_graph_sorts_on_the_server_and_masks_a_licensed_sort(make: Make) -> None:
    client = make("me", Role.TRADER)
    by_score = graph_rows(client, "IN_SAMPLE", "SCORE")
    assert [r["instrumentId"] for r in by_score] == ["EQ:B", "EQ:A"]  # A's score is LICENCE: last
    assert by_score[1]["score"]["unknown"]["kind"] == "LICENCE"


def test_a_pre_ledger_run_is_unknown_in_the_graph(make: Make) -> None:
    client = make("me", Role.TRADER, backend_with_run(trades=None))
    body = client.post(
        "/graphql",
        json={
            "query": GRAPH,
            "variables": {"id": "drift", "period": "ALL", "sort": "DECISION", "desc": False},
        },
    ).json()
    page = body["data"]["edgeTrades"]
    assert page["rows"] == [] and page["unknown"]["code"] == "NOT_STORED"
    assert "cause" not in str(body)


def test_the_variant_grid_marks_the_basis(make: Make) -> None:
    client = make("me", Role.TRADER)
    query = (
        '{ edgeVariants(edgeId: "drift") '
        "{ basis oosHidden rows { variant official notPreChosen } } }"
    )
    body = client.post("/graphql", json={"query": query}).json()
    assert "errors" not in body, body
    grid = body["data"]["edgeVariants"]
    assert grid["basis"] == "momo, 20 trading days" and grid["oosHidden"] is False
    assert grid["rows"] == [{"variant": "momo", "official": True, "notPreChosen": False}]


def test_the_file_takes_the_pages_session_for_live_rows(make: Make) -> None:

    backend = backend_with_run()
    store(backend, [trade("EQ:L", date(2026, 9, 1), "won", sell=date(2026, 9, 30))])
    client = make("me", Role.TRADER, backend)
    asked = {"period": "live", "date": SESSION.isoformat()}
    rows = list(
        csv.DictReader(io.StringIO(client.get("/files/edges/drift/trades.csv", params=asked).text))
    )
    assert [r["instrument_id"] for r in rows] == ["EQ:L"] and rows[0]["source"] == "live"
