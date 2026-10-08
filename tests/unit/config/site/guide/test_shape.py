"""The Guide sources' shared shape checks: one-line strings collapsed and required, lists of
strings, lists of tables and values listed once, each failure naming where."""

from collections.abc import Callable

import pytest

from algotrade.config.site.fields import Table
from algotrade.config.site.guide.shape import line, lines, once, tables
from algotrade.core.model.errors import ConfigurationError

T = Table({"a": " one\n  two ", "empty": " ", "list": ["x  y", "z"], "rows": [{"k": 1}]}, "f.toml")


def test_lines_collapse_their_whitespace() -> None:
    assert line(T, "a") == "one two"
    assert lines(T, "list") == ("x y", "z")
    assert lines(T, "missing", required=False) == ()
    (row,) = tables(T, "rows")
    assert row.raw("k") == 1 and row.where == "f.toml [[rows]][0]"
    assert tables(T, "missing") == []


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (lambda: line(T, "empty"), "f.toml empty: expected a non-empty string"),
        (lambda: line(T, "missing"), "missing: expected a non-empty string"),
        (lambda: lines(T, "missing"), "missing: expected one or more"),
        (lambda: tables(T, "a"), "a: expected a list of tables"),
        (lambda: once("f.toml", "ids", ["b", "a", "b"]), "ids listed more than once: \\['b'\\]"),
    ],
)
def test_failures_name_the_file_and_key(check: Callable[[], object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        check()
