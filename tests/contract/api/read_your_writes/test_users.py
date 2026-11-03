"""Read-your-writes of ``POST /users`` (ADR 0077 decision 16; ID5): the onboarded user is on the
very next ``UserRegistry`` read (never cached: the Admin Users page always shows the registry as
it is), as a trader still waiting for the provider account."""

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

REGISTRY = "query UserRegistry { userRegistry { people { id role licences pendingProvider } } }"
BODY = {"user_id": "zoe", "email": "zoe@example.com", "name": "Zoe"}


def test_onboarding_shows_the_new_trader_on_the_next_registry_read(
    gate: Gate, writer_client: TestClient
) -> None:
    before = gate.read(writer_client, REGISTRY)["people"]
    assert "zoe" not in [p["id"] for p in before]
    assert writer_client.post("/users", json=BODY).status_code == 200
    people = {p["id"]: p for p in gate.read(writer_client, REGISTRY)["people"]}
    assert people["zoe"] == {
        "id": "zoe", "role": "trader", "licences": [], "pendingProvider": True,
    }  # fmt: skip
    assert people["alice"]["pendingProvider"] is False  # a users.toml entry is not pending
