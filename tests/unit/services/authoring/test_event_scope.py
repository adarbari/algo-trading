"""The admin's changes to the event scope list (EV8): add and remove through
``config/admin/events/scope.toml``, idempotent, admin only, an added symbol known to the session's
reference snapshot, a site name removed and restored."""

from datetime import UTC, date, datetime

import pytest

from algotrade.config.site.events.scope import effective_list, load_admin_scope
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError, PermissionDeniedError
from algotrade.services.authoring.event_scope import add_scope_name, remove_scope_name
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.configs.writer import FileConfigWriter, MemoryConfigWriter
from tests.unit.services.read.events.conftest import store_with

USERS = {"user": [{"id": "local", "role": "admin"}, {"id": "tom", "role": "trader"}]}
SITE = {"name": [{"symbol": "ETFX", "added_on": date(2026, 10, 6), "note": "site"}]}


@pytest.fixture
def configs() -> MemoryConfigWriter:
    return MemoryConfigWriter(
        {("site", "settings", "users"): USERS, ("site", "events", "scope"): SITE}
    )


@pytest.fixture
def ctx(configs: MemoryConfigWriter) -> ReadContext:
    return open_context(store_with(), configs, UserContext("local"))


def symbols(configs: MemoryConfigWriter) -> tuple[str, ...]:
    return effective_list(configs).symbols


def test_an_admin_adds_a_known_name_once(configs: MemoryConfigWriter, ctx: ReadContext) -> None:
    before = datetime.now(UTC).replace(microsecond=0)
    first = add_scope_name(configs, ctx, "local", " aaa ", " a  note ")
    assert (first.symbol, first.listed, first.changed) == ("AAA", True, True)
    entry = load_admin_scope(configs).added[0]
    assert (entry.symbol, entry.by, entry.note) == ("AAA", "local", "a note")
    assert before <= entry.at <= datetime.now(UTC)
    assert symbols(configs) == ("ETFX", "AAA")
    again = add_scope_name(configs, ctx, "local", "AAA")
    assert (again.listed, again.changed) == (True, False) and len(
        load_admin_scope(configs).added
    ) == 1


def test_a_name_already_on_the_site_list_is_a_no_op(
    configs: MemoryConfigWriter, ctx: ReadContext
) -> None:
    assert add_scope_name(configs, ctx, "local", "ETFX").changed is False
    assert load_admin_scope(configs).added == ()


def test_removing_a_site_name_records_it_and_adding_it_back_restores_it(
    configs: MemoryConfigWriter, ctx: ReadContext
) -> None:
    done = remove_scope_name(configs, "local", "ETFX", "no longer wanted")
    assert (done.listed, done.changed) == (False, True)
    assert (
        symbols(configs) == () and load_admin_scope(configs).removed[0].note == "no longer wanted"
    )
    assert remove_scope_name(configs, "local", "ETFX").changed is False  # idempotent
    back = add_scope_name(configs, ctx, "local", "ETFX")
    assert (back.listed, back.changed) == (True, True)
    assert symbols(configs) == ("ETFX",) and load_admin_scope(configs).added == ()  # no duplicate
    assert load_admin_scope(configs).removed == ()


def test_removing_an_admin_addition_drops_it_without_a_removal_entry(
    configs: MemoryConfigWriter, ctx: ReadContext
) -> None:
    add_scope_name(configs, ctx, "local", "AAA")
    assert remove_scope_name(configs, "local", "AAA").changed is True
    scope = load_admin_scope(configs)
    assert scope.added == () and scope.removed == () and symbols(configs) == ("ETFX",)


def test_removing_a_name_not_on_the_list_changes_nothing(configs: MemoryConfigWriter) -> None:
    done = remove_scope_name(configs, "local", "QQQ")
    assert (done.listed, done.changed) == (False, False)
    assert configs.load("admin", "events", "scope") is None  # nothing was written


@pytest.mark.parametrize("symbol", ["", "eq:aaa", "BRK-B", "TOOLONGSYM", "A B", "EQ:BBG000C2V3D6"])
def test_a_badly_spelled_symbol_is_refused(
    configs: MemoryConfigWriter, ctx: ReadContext, symbol: str
) -> None:
    with pytest.raises(ConfigurationError, match="expected a listed ticker"):
        add_scope_name(configs, ctx, "local", symbol)
    with pytest.raises(ConfigurationError, match="expected a listed ticker"):
        remove_scope_name(configs, "local", symbol)


def test_a_symbol_the_reference_snapshot_does_not_know_is_refused_with_the_session(
    configs: MemoryConfigWriter, ctx: ReadContext
) -> None:
    with pytest.raises(
        ConfigurationError, match=r"NOPE is not in the reference snapshot.*2026-10-01"
    ):
        add_scope_name(configs, ctx, "local", "NOPE")
    assert configs.load("admin", "events", "scope") is None


def test_only_an_admin_changes_the_list(configs: MemoryConfigWriter, ctx: ReadContext) -> None:
    for who in ("tom", "stranger"):
        with pytest.raises(PermissionDeniedError):
            add_scope_name(configs, ctx, who, "AAA")
        with pytest.raises(PermissionDeniedError):
            remove_scope_name(configs, who, "ETFX")
    assert symbols(configs) == ("ETFX",)


def test_a_long_or_unprintable_note_is_refused(
    configs: MemoryConfigWriter, ctx: ReadContext
) -> None:
    with pytest.raises(ConfigurationError, match="note"):
        add_scope_name(configs, ctx, "local", "AAA", "x" * 201)
    with pytest.raises(ConfigurationError, match="note"):
        remove_scope_name(configs, "local", "ETFX", "bell\x07")


def test_the_file_writer_keeps_the_site_file_untouched_and_the_admin_file_apart(
    tmp_path, ctx: ReadContext
) -> None:
    site = tmp_path / "site" / "events"
    site.mkdir(parents=True)
    (site / "scope.toml").write_text('[[name]]\nsymbol = "ETFX"\nadded_on = 2026-10-06\n')
    (tmp_path / "site" / "users.toml").write_text('[[user]]\nid = "local"\nrole = "admin"\n')
    writer = FileConfigWriter(tmp_path)
    remove_scope_name(writer, "local", "ETFX")
    assert (site / "scope.toml").read_text().count("ETFX") == 1  # the PR-reviewed file is as it was
    written = (tmp_path / "admin" / "events" / "scope.toml").read_text()
    assert written.startswith("removed = ") and 'by = "local"' in written
    assert effective_list(FileConfigWriter(tmp_path)).symbols == ()
