"""``Table``'s shared text reads (one-line strings collapsed and required, lists of strings,
lists of tables) and ``unique``, each failure naming the file and the key."""

from collections.abc import Callable

import pytest

from algotrade.config.site.fields import Table, unique
from algotrade.core.model.errors import ConfigurationError

DOC = {
    "a": " one\n  two ",
    "empty": " ",
    "list": ["x  y", "z"],
    "blank": ["x", " "],
    "rows": [{"k": 1}],
}
T = Table(DOC, "f.toml")


def test_lines_collapse_their_whitespace() -> None:
    assert T.line("a") == "one two"
    assert T.lines("list") == ("x y", "z")
    assert T.lines("missing", required=False) == ()
    (row,) = T.tables("rows")
    assert row.raw("k") == 1 and row.where == "f.toml [[rows]][0]"
    assert T.tables("missing") == []
    unique("f.toml", "ids", ["a", "b"])  # no repeat: no error


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (lambda: T.line("empty"), "f.toml empty: expected a non-empty string"),
        (lambda: T.line("missing"), "missing: expected a non-empty string"),
        (lambda: T.lines("missing"), "missing: expected one or more non-empty strings"),
        (lambda: T.lines("blank", required=False), "blank: expected non-empty strings"),
        (lambda: T.tables("a"), r"a: expected a list of tables \(\[\[a\]\]\)"),
        (lambda: unique("f.toml", "ids", ["b", "a", "b"]), r"ids listed more than once: \['b'\]"),
    ],
)
def test_failures_name_the_file_and_key(check: Callable[[], object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        check()
