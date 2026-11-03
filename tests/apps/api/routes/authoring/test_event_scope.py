"""``PUT`` / ``DELETE /admin/events/scope/{symbol}`` (EV8): an admin changes the event scope list
through ``config/admin/events/scope.toml`` only; a trader is refused; both are idempotent; a symbol
the snapshot does not know or that is misspelled is a 400; the site file is never touched."""

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

URL = "/admin/events/scope"
SITE_NAMES = '[[name]]\nsymbol = "AAA"\nadded_on = 2026-10-06\n'


def admin_file(root: Path) -> dict:
    return tomllib.loads((root / "admin" / "events" / "scope.toml").read_text())


def test_an_admin_adds_a_known_name_and_a_repeat_changes_nothing(
    writer_client: TestClient, root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="algotrade_api.routes.authoring.event_scope"):
        first = writer_client.put(f"{URL}/AAA", json={"note": "memory cycle"})
    assert (first.status_code, first.json()) == (
        200,
        {"symbol": "AAA", "listed": True, "changed": True},
    )
    entry = admin_file(root)["added"][0]
    assert (entry["symbol"], entry["by"], entry["note"]) == ("AAA", "local", "memory cycle")
    assert writer_client.put(f"{URL}/aaa").json() == {
        "symbol": "AAA",
        "listed": True,
        "changed": False,
    }
    assert len(admin_file(root)["added"]) == 1
    assert "event-scope add symbol=AAA changed=True by=local" in caplog.text


def test_an_admin_removes_a_site_name_without_touching_the_site_file(
    writer_client: TestClient, root: Path
) -> None:
    events = root / "site" / "events"
    events.mkdir(parents=True)
    (events / "scope.toml").write_text(SITE_NAMES)
    gone = writer_client.delete(f"{URL}/AAA")
    assert (gone.status_code, gone.json()) == (
        200,
        {"symbol": "AAA", "listed": False, "changed": True},
    )
    assert admin_file(root)["removed"][0]["symbol"] == "AAA"
    assert (events / "scope.toml").read_text() == SITE_NAMES
    assert writer_client.delete(f"{URL}/AAA").json()["changed"] is False
    back = writer_client.put(f"{URL}/AAA")  # restored: the removal is dropped, no addition
    assert back.json() == {"symbol": "AAA", "listed": True, "changed": True}
    assert "removed" not in admin_file(root) and "added" not in admin_file(root)


def test_a_trader_is_refused_and_nothing_is_written(trader_client: TestClient, root: Path) -> None:
    assert trader_client.put(f"{URL}/AAA").status_code == 403
    assert trader_client.delete(f"{URL}/AAA").status_code == 403
    assert not (root / "admin").exists()


@pytest.mark.parametrize("symbol", ["NOPEX", "bad-sym", "EQ:AAA"])
def test_an_unknown_or_misspelled_symbol_is_a_400(
    writer_client: TestClient, root: Path, symbol: str
) -> None:
    assert writer_client.put(f"{URL}/{symbol}").status_code == 400
    assert not (root / "admin").exists()


def test_a_note_over_the_limit_is_a_400(writer_client: TestClient, root: Path) -> None:
    assert writer_client.put(f"{URL}/AAA", json={"note": "x" * 201}).status_code == 400
    assert not (root / "admin").exists()


READ = """{ eventScope { session staleDays otherNames macroDays macroReleases unresolved
  names { symbol source by lastReview stale reasons moves { share } }
  removed { symbol by reasons } } }"""


def test_the_effective_list_is_read_back_by_an_admin_and_refused_to_a_trader(
    writer_client: TestClient, trader_client: TestClient, root: Path
) -> None:
    events = root / "site" / "events"
    events.mkdir(parents=True)
    (events / "scope.toml").write_text(
        '[[name]]\nsymbol = "AAA"\nadded_on = 2026-10-06\n\n[[name]]\nsymbol = "GONE"\n'
        "added_on = 2026-10-06\n"
    )
    assert writer_client.delete(f"{URL}/AAA").status_code == 200
    assert writer_client.put(f"{URL}/AAAU", json={"note": "levered"}).status_code == 400
    body = writer_client.post("/graphql", json={"query": READ}).json()
    assert "errors" not in body, body
    scope = body["data"]["eventScope"]
    assert scope["staleDays"] == 90 and scope["macroDays"] == 90
    assert scope["unresolved"] == ["GONE"]  # the snapshot does not know it
    assert [r["symbol"] for r in scope["removed"]] == ["AAA"] and scope["removed"][0][
        "by"
    ] == "local"
    assert scope["names"] == []  # AAA removed, GONE unresolved
    refused = trader_client.post("/graphql", json={"query": READ}).json()
    assert refused["errors"][0]["extensions"]["code"] == "FORBIDDEN"
