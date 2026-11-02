"""Read-your-writes of the preference routes (ADR 0077 decision 16): a
table's saved view shows on the very next ``TableView`` read (cached per user),
and another user's view is untouched."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.storage.configs.writer import FileConfigWriter
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.apps.api.routes.authoring.conftest import PRESET, USERS
from tests.conftest import REPO_ROOT
from tests.contract.api.read_your_writes.conftest import Gate
from tests.helpers.api_store import as_user

VIEW = """query TableView($scope: String!, $name: String) {
  view(scope: $scope, name: $name) { scope saved columns sort decisions names }
}"""
SCOPE = "screener:vrp"
CLOSE = "rollup.price_stats@v2.close"
BODY = {"columns": [CLOSE], "sort": f"-{CLOSE}", "decisions": ["QUALIFIED"]}


def test_view_put_shows_the_saved_view(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, VIEW, scope=SCOPE, name=None)["saved"] is False
    assert gate.warm(trader_client, VIEW, scope=SCOPE, name=None)["saved"] is False
    assert c.put(f"/preferences/views/{SCOPE}/view", json=BODY).status_code == 200
    saved = gate.fresh(c, VIEW, scope=SCOPE, name=None)
    assert (saved["saved"], saved["columns"], saved["sort"]) == (True, [CLOSE], f"-{CLOSE}")
    gate.warm(c, VIEW, scope=SCOPE, name=None)
    again = {"columns": [], "sort": None, "decisions": []}
    assert c.put(f"/preferences/views/{SCOPE}/view", json=again).status_code == 200
    assert gate.fresh(c, VIEW, scope=SCOPE, name=None)["columns"] == []
    assert gate.warm(trader_client, VIEW, scope=SCOPE, name=None)["saved"] is False  # bob's own


def test_view_delete_forgets_a_named_view(gate: Gate, writer_client: TestClient) -> None:
    c = writer_client
    url = f"/preferences/views/{SCOPE}/view"
    assert c.put(url, json=BODY, params={"name": "Mine"}).status_code == 200
    assert gate.warm(c, VIEW, scope=SCOPE, name="Mine")["saved"] is True
    assert gate.warm(c, VIEW, scope=SCOPE, name=None)["names"] == ["Mine"]
    assert c.delete(url, params={"name": "Mine"}).status_code == 200
    assert gate.fresh(c, VIEW, scope=SCOPE, name="Mine")["saved"] is False
    assert gate.fresh(c, VIEW, scope=SCOPE, name=None)["names"] == []


APPEARANCE = "query Appearance { appearance { theme } }"


def test_appearance_put_shows_the_saved_theme(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, APPEARANCE)["theme"] == "system"
    assert gate.warm(trader_client, APPEARANCE)["theme"] == "system"
    assert c.put("/preferences/appearance", json={"theme": "dark"}).status_code == 200
    assert gate.fresh(c, APPEARANCE)["theme"] == "dark"
    gate.warm(c, APPEARANCE)
    assert c.put("/preferences/appearance", json={"theme": "light"}).status_code == 200
    assert gate.fresh(c, APPEARANCE)["theme"] == "light"
    assert gate.warm(trader_client, APPEARANCE)["theme"] == "system"  # bob's own


PREFS = "query TraderPreferences { traderPreferences { defaultTab watchlist { instrumentId } } }"


def test_ideas_put_shows_the_saved_default_tab(
    gate: Gate, writer_client: TestClient, trader_client: TestClient
) -> None:
    c = writer_client
    assert gate.warm(c, PREFS)["defaultTab"] is None
    assert gate.warm(trader_client, PREFS)["defaultTab"] is None
    assert c.put("/preferences/ideas", json={"default_tab": "premium"}).status_code == 200
    assert gate.fresh(c, PREFS)["defaultTab"] == "premium"
    assert gate.warm(trader_client, PREFS)["defaultTab"] is None  # bob's own


def test_watchlist_put_shows_the_saved_instruments(
    gate: Gate,
    writer_client: TestClient,
    trader_client: TestClient,
) -> None:
    c = writer_client
    one = "EQ:AAA"
    assert gate.warm(c, PREFS)["watchlist"] == []
    assert gate.warm(trader_client, PREFS)["watchlist"] == []
    assert c.put("/preferences/watchlist", json={"instruments": [one]}).status_code == 200
    assert gate.fresh(c, PREFS)["watchlist"] == [{"instrumentId": one}]
    gate.warm(c, PREFS)
    assert c.put("/preferences/watchlist", json={"instruments": []}).status_code == 200
    assert gate.fresh(c, PREFS)["watchlist"] == []
    assert gate.warm(trader_client, PREFS)["watchlist"] == []  # bob's own


POOL = """query IdeasPage($tab: IdeaTab) {
  ideas(tab: $tab) { total watchlist items { instrumentId rank } }
}"""
SETUP_IDEAS = """query SetupIdeas($tab: IdeaTab!) {
  setupIdeas(tab: $tab) { state total watchlist ideas { instrumentId } }
}"""


@pytest.fixture
def ideas_clients(
    api_golden: tuple[ReadStore, dict[str, str]], root: Path
) -> tuple[TestClient, TestClient]:
    """local and bob over the golden store's ``vrp_scanner`` run (a site preset here, with the
    ranking rule), both holding the licences its fields need so its picks are not withheld."""
    site = root / "site"
    (site / "presets" / "screeners" / "vrp_scanner").mkdir()
    preset = PRESET.replace('id = "vrp"', 'id = "vrp_scanner"').replace(
        "version = 3", "version = 1"
    )
    (site / "presets" / "screeners" / "vrp_scanner" / "v1.toml").write_text(preset)
    (site / "ranking").symlink_to(REPO_ROOT / "config" / "site" / "ranking")
    held = 'role = "admin"\nlicences = ["personal", "yahoo"]'
    trader = 'id = "bob"\nrole = "trader"\nlicences = ["personal", "yahoo"]'
    users = USERS.replace('role = "admin"', held).replace('id = "bob"\nrole = "trader"', trader)
    (site / "users.toml").write_text(users)

    def client(user: str, role: Role) -> TestClient:
        writer = FileConfigWriter(root)
        store = replace(api_golden[0], configs=writer, user=UserContext(user))
        settings = ApiSettings("memory://", str(root))
        return TestClient(create_app(settings, store, writer, authenticator=as_user(user, role)))

    return client("local", Role.ADMIN), client("bob", Role.TRADER)


def test_watchlist_put_filters_ideas_on_the_next_read(
    gate: Gate, ideas_clients: tuple[TestClient, TestClient]
) -> None:
    """ADR 0083 amendment (c): a watchlist write filters the very next Ideas read (the tab's
    pool and its setup list), though no publish or run moved; another user's Ideas are not."""
    c, bob = ideas_clients
    every = gate.warm(c, POOL, tab="STOCKS")
    listed = gate.warm(c, SETUP_IDEAS, tab="STOCKS")
    assert every["watchlist"] is None and listed["watchlist"] is None
    assert len(every["items"]) > 1, "the fixture's pool lists ideas"
    second = every["items"][1]
    gate.warm(bob, POOL, tab="STOCKS")
    assert (
        c.put("/preferences/watchlist", json={"instruments": [second["instrumentId"]]}).status_code
        == 200
    )
    mine = gate.fresh(c, POOL, tab="STOCKS")
    assert (mine["items"], mine["total"], mine["watchlist"]) == ([second], 1, every["total"])
    assert gate.fresh(c, SETUP_IDEAS, tab="STOCKS")["state"] == listed["state"]
    assert gate.warm(bob, POOL, tab="STOCKS") == every  # bob's own
    assert c.put("/preferences/watchlist", json={"instruments": []}).status_code == 200
    assert gate.fresh(c, POOL, tab="STOCKS") == every
