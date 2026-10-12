"""``Query.acceptedFormulas``: the Admin page's grouped list; an admin is served, a trader
refused (ADR 0040), and the type exposes counts only, never a user (ADR 0066)."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.types.ops.accepted_formulas import AcceptedFormula, AcceptedFormulaList
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

QUERY = """{ acceptedFormulas { today days rows { fingerprint canonical expression unit
  description acceptedCount users firstAccepted lastAccepted duplicateOf backlogKey } } }"""
FORBIDDEN_WORDS = ("user_id", "userid", "who", "accepter", "email")


def _graph(role: Role) -> Callable[[str], dict[str, Any]]:
    store = ReadStore(StoreReader(MemoryBackend()), MemoryConfigStore({}), UserContext("local"))
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("u", role))
    client = TestClient(app)

    def post(query: str) -> dict[str, Any]:
        body: dict[str, Any] = client.post("/graphql", json={"query": query}).json()
        return body

    return post


def test_an_admin_reads_an_empty_list() -> None:
    body = _graph(Role.ADMIN)(QUERY)
    assert "errors" not in body, body
    assert body["data"]["acceptedFormulas"]["rows"] == []
    assert body["data"]["acceptedFormulas"]["days"] == 365


def test_a_trader_is_forbidden() -> None:
    body = _graph(Role.TRADER)(QUERY)
    [error] = body["errors"]
    assert error["extensions"]["code"] == "FORBIDDEN"


def test_the_types_expose_no_user_field() -> None:
    names = [
        f.python_name
        for t in (AcceptedFormulaList, AcceptedFormula)
        for f in t.__strawberry_definition__.fields
    ]
    assert not [n for n in names if any(w in n.lower() for w in FORBIDDEN_WORDS)], names
    assert "users" in names and "accepted_count" in names  # counts are
