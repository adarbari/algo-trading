"""Read-your-writes of ``PUT`` / ``DELETE /admin/events/scope/{symbol}`` (ADR 0077 decision 16;
EV8): the very next cached ``EventCalendar`` read over the scope list shows the admin's change,
because the admin scope's counter (``config/admin/.generation``) is in every response key."""

from fastapi.testclient import TestClient

from tests.contract.api.read_your_writes.conftest import Gate

CALENDAR = """query EventCalendar($ids: [String!]!, $scope: Boolean!) {
  eventCalendar(instrumentIds: $ids, scope: $scope) { names { symbol } unresolved }
}"""
URL = "/admin/events/scope/AAA"


def listed(gate: Gate, client: TestClient, fresh: bool = False) -> list[str]:
    read = gate.fresh if fresh else gate.warm
    return [n["symbol"] for n in read(client, CALENDAR, ids=[], scope=True)["names"]]


def test_add_shows_the_name_on_the_next_scoped_calendar(
    gate: Gate, writer_client: TestClient
) -> None:
    assert listed(gate, writer_client) == []  # warm: the repeat is a cache hit
    assert writer_client.put(URL).status_code == 200
    assert listed(gate, writer_client, fresh=True) == ["AAA"]


def test_remove_drops_the_name_from_the_next_scoped_calendar(
    gate: Gate, writer_client: TestClient
) -> None:
    assert writer_client.put(URL).status_code == 200
    assert listed(gate, writer_client) == ["AAA"]
    assert writer_client.delete(URL).status_code == 200
    assert listed(gate, writer_client, fresh=True) == []
