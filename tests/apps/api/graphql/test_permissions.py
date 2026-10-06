"""Admin-only fields (ADR 0040): every field of the Admin area (the types under ``types/ops``
but the trader ones: runs, quality, ingestion and review) is refused to a trader with
``FORBIDDEN`` and answers an admin. The fields are found in the schema, so a new Admin field
without ``AdminOnly`` fails here."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from strawberry.utils.str_converters import to_camel_case

from algotrade.config.site.users import Role
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.permissions import MESSAGE, AdminOnly
from algotrade_api.graphql.types.query import Query
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import as_user

# Every module under types/ops/ is ops data (an Admin type) except these trader ones: the
# strategy configs and saved backtests the Backtests page reads.
OPS = "algotrade_api.graphql.types.ops."
TRADER_OPS = (OPS + "backtest", OPS + "config")
# The arguments each Admin field needs, for a call that selects only ``__typename``.
CALLS = {
    "nightly_runs": "nightlyRuns(limit: 1)",
    "run": 'run(runId: "x")',
    "run_items": 'runItems(runId: "x")',
    "quality": "quality",
    "verification": "verification",
    "completeness": "completeness",
    "ingestion_cell": 'ingestionCell(dataset: "bars", date: "2022-11-23")',
    "figi_review": "figiReview",
    "leverage_review": "leverageReview",
}


def _query_fields() -> list[Any]:
    return list(Query.__strawberry_definition__.fields)


def _target(field: Any) -> Any:
    """The object type ``field`` returns (lists and optionals unwrapped), else ``None``."""
    kind = field.type
    while hasattr(kind, "of_type"):
        kind = kind.of_type
    return getattr(kind, "__strawberry_definition__", None)


def _is_admin(definition: Any) -> bool:
    module = str(definition.origin.__module__)
    return module.startswith(OPS) and module not in TRADER_OPS


ADMIN_FIELDS = sorted(
    f.python_name for f in _query_fields() if (d := _target(f)) is not None and _is_admin(d)
)


def test_no_ops_type_is_reachable_without_going_through_an_admin_field() -> None:
    """Walk the graph from ``Query`` through the fields that are not ``AdminOnly``: an Admin
    type found there (a nested field returning one) would be readable by a trader."""
    seen: set[str] = set()
    pending = [
        f for f in _query_fields() if not any(isinstance(e, AdminOnly) for e in f.extensions)
    ]
    leaked: list[str] = []
    while pending:
        field = pending.pop()
        target = _target(field)
        if target is None:
            continue
        if _is_admin(target):
            leaked.append(f"{field.python_name} -> {target.name}")
        elif target.name not in seen:
            seen.add(target.name)
            pending.extend(target.fields)
    assert leaked == []


def test_the_admin_fields_are_the_ops_reads() -> None:
    assert sorted(CALLS) == ADMIN_FIELDS, "a new Admin field needs a CALLS entry here"


@pytest.mark.parametrize("name", ADMIN_FIELDS)
def test_every_admin_field_is_admin_only(name: str) -> None:
    field = next(f for f in _query_fields() if f.python_name == name)
    assert any(isinstance(e, AdminOnly) for e in field.extensions), f"Query.{name}: no AdminOnly"


@pytest.fixture(scope="module")
def as_role(api_golden: tuple[ReadStore, dict[str, str]]) -> Callable[[Role], Graph]:
    def graph_for(role: Role) -> Graph:
        user = "ana" if role is Role.ADMIN else "bob"
        app = create_app(
            ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user(user, role)
        )
        client = TestClient(app)

        def post(query: str) -> dict[str, Any]:
            response = client.post("/graphql", json={"query": query})
            assert response.status_code == 200, response.text
            body: dict[str, Any] = response.json()
            return body

        return post

    return graph_for


@pytest.mark.parametrize("name", ADMIN_FIELDS)
def test_a_trader_is_forbidden_and_an_admin_is_served(
    as_role: Callable[[Role], Graph], name: str
) -> None:
    query = f"{{ {CALLS[name]} {{ __typename }} }}"
    refused = as_role(Role.TRADER)(query)
    [error] = refused["errors"]
    assert error["extensions"]["code"] == "FORBIDDEN" and error["message"] == MESSAGE
    assert refused["data"] is None or refused["data"][to_camel_case(name)] is None
    served = as_role(Role.ADMIN)(query)
    assert "errors" not in served, served


def test_a_trader_still_reads_everything_else(as_role: Callable[[Role], Graph]) -> None:
    trader = as_role(Role.TRADER)
    body = trader(
        "{ viewer { id role } configs { __typename } backtests { __typename } session { date } }"
    )
    assert "errors" not in body and body["data"]["viewer"]["role"] == "trader"
