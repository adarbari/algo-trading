"""`scripts/check_rest_allowlist.py`: the REST GET allow-list only shrinks (ADR 0037)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_rest_allowlist.py"
_spec = importlib.util.spec_from_file_location("check_rest_allowlist", SCRIPT)
assert _spec and _spec.loader
check_rest_allowlist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_rest_allowlist)

HEALTH = '[[route]]\nmethod = "GET"\npath = "/health"\nkeep = true\nreason = "liveness"\n'
IDEAS = '[[route]]\nmethod = "GET"\npath = "/ideas"\nkeep = false\nretire_in = "PR 5"\n'


def allowlist(tmp_path: Path, count: int, *routes: str) -> Path:
    (tmp_path / "architecture").mkdir()
    path = tmp_path / "architecture" / "rest_allowlist.toml"
    path.write_text(f"# header\nmax_get_routes = {count}\n\n" + "\n".join(routes))
    return path


def test_the_committed_allowlist_passes() -> None:
    code, message = check_rest_allowlist.check(SCRIPT.parents[1], update=False)
    assert code == 0, message


def test_an_entry_beyond_the_committed_count_fails(tmp_path: Path) -> None:
    allowlist(tmp_path, 1, HEALTH, IDEAS)
    code, message = check_rest_allowlist.check(tmp_path, update=False)
    assert code == 1
    assert "only shrinks" in message and "add-graphql-field" in message


def test_update_refuses_to_raise_the_count(tmp_path: Path) -> None:
    path = allowlist(tmp_path, 1, HEALTH, IDEAS)
    assert check_rest_allowlist.check(tmp_path, update=True)[0] == 1
    assert "max_get_routes = 1\n" in path.read_text()


def test_a_removed_entry_fails_until_the_count_is_lowered(tmp_path: Path) -> None:
    path = allowlist(tmp_path, 2, HEALTH)
    code, message = check_rest_allowlist.check(tmp_path, update=False)
    assert code == 1 and "make rest-allowlist-update" in message
    assert check_rest_allowlist.check(tmp_path, update=True)[0] == 0
    assert "max_get_routes = 1\n" in path.read_text()
    assert check_rest_allowlist.check(tmp_path, update=False)[0] == 0


def test_malformed_entries_are_named(tmp_path: Path) -> None:
    allowlist(
        tmp_path,
        3,
        '[[route]]\nmethod = "POST"\npath = "/x"\nkeep = true\nreason = "r"\n',
        '[[route]]\nmethod = "GET"\npath = "/y"\nkeep = true\n',
        '[[route]]\nmethod = "GET"\npath = "/y"\nkeep = false\n',
    )
    code, message = check_rest_allowlist.check(tmp_path, update=False)
    assert code == 1
    for expected in ("/x: method must be GET", "/y: listed twice", "needs its reason", "retire_in"):
        assert expected in message


def test_main_exits_with_the_check_result(tmp_path: Path) -> None:
    allowlist(tmp_path, 1, HEALTH)
    assert check_rest_allowlist.main(["--root", str(tmp_path)]) == 0
