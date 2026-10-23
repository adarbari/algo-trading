"""``Session.dataStatus`` (ADR 0062 amendment) is public: a trader reads the state, the shares
and the public kind of a gap, with a null cause and no step or table name; an admin reading the
same field is served the cause chain behind an UNKNOWN dataset (ADR 0056)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.services.read.availability.cause import TABLE_PREFIXES
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

QUERY = """query($date: Date) { session(date: $date) { dataStatus {
  state knowledgeTs affectedScreeners totalScreeners
  datasets { name status present expected share
    unavailable { kind guideTerm kindText cause { links { level subject message } } } }
} } }"""


def _post(store: ReadStore, role: Role) -> dict[str, Any]:
    user = "ana" if role is Role.ADMIN else "local"
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user(user, role))
    response = TestClient(app).post("/graphql", json={"query": QUERY, "variables": {}})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert "errors" not in body, body
    return body["data"]["session"]["dataStatus"]  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def store(api_golden: tuple[ReadStore, dict[str, str]]) -> ReadStore:
    return api_golden[0]


def test_a_trader_reads_the_status_with_no_cause_and_no_step_or_table(store: ReadStore) -> None:
    status = _post(store, Role.TRADER)
    assert status["datasets"] and status["totalScreeners"] >= 0
    gaps = [g for d in status["datasets"] for g in d["unavailable"]]
    assert gaps, "the golden store has no run record for a dataset: UNKNOWN, with its gap"
    assert all(g["cause"] is None and g["guideTerm"] and g["kindText"] for g in gaps)
    text = json.dumps(status)
    assert [p for p in TABLE_PREFIXES if p in text] == []
    for name in ("daily_bars", "option_chains", "nightly"):
        assert name not in text
    assert all(d["share"] is None for d in status["datasets"] if d["status"] == "UNKNOWN")


def test_an_admin_reads_the_cause_behind_an_unknown_dataset(store: ReadStore) -> None:
    status = _post(store, Role.ADMIN)
    gaps = [g for d in status["datasets"] for g in d["unavailable"]]
    assert gaps and all(g["cause"]["links"] for g in gaps)
    assert {link["level"] for g in gaps for link in g["cause"]["links"]} == {"RUN"}
