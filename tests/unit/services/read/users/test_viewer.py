"""The viewer: the registry user, role and workspaces, never the identity."""

from algotrade.config.site.users import Role, UserRecord
from algotrade.services.read.users.viewer import Viewer, load_viewer


def test_an_admin_opens_both_workspaces_a_trader_one() -> None:
    ana = UserRecord("ana", Role.ADMIN, "Ana", "ana@example.com")
    assert load_viewer(ana) == Viewer("ana", "Ana", "admin", ("admin", "trader"))
    assert load_viewer(UserRecord("tom", Role.TRADER)) == Viewer("tom", "", "trader", ("trader",))
