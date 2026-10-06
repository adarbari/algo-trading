"""``Query.viewer``: the caller as the registry knows them."""

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user

VIEWER = "{ viewer { id name role workspaces } }"


def test_the_viewer_is_the_caller(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    for user, role, workspaces in (
        ("ana", Role.ADMIN, ["admin", "trader"]),
        ("tom", Role.TRADER, ["trader"]),
    ):
        app = create_app(
            ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user(user, role)
        )
        body = TestClient(app).post("/graphql", json={"query": VIEWER}).json()
        assert body == {
            "data": {
                "viewer": {"id": user, "name": "", "role": role.value, "workspaces": workspaces}
            }
        }
