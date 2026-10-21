"""``config_generation``: the response-cache component of a user's configs (ADR 0077 15)."""

from algotrade.services.configs import config_generation
from algotrade.storage.configs.writer import MemoryConfigWriter


def test_a_user_sees_their_own_generation_and_an_admin_everyones() -> None:
    writer = MemoryConfigWriter()
    generation = config_generation(writer)
    writer.save_preferences("alice", {"x": 1})
    writer.save_preferences("bob", {"x": 1})
    alice, admin = generation("alice", False), generation("local", True)
    assert alice == 2 and admin == 4  # an admin's moves with any user's write
    writer.save_preferences("bob", {"x": 2})
    assert generation("alice", False) == alice  # a trader's key ignores another user's write
    assert generation("local", True) == admin + 2


def test_nothing_is_cached_while_any_users_write_is_in_flight_for_an_admin() -> None:
    writer = MemoryConfigWriter()
    writer.save_preferences("alice", {"x": 1})
    writer._generations["bob"] = 3  # a write of bob's is in flight (odd)
    generation = config_generation(writer)
    assert generation("alice", False) == 2  # alice's own key is unaffected
    assert generation("local", True) is None  # an admin's depends on bob's configs too
