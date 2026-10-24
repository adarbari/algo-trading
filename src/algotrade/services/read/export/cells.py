"""``cell``: one CSV cell made safe to open in a spreadsheet (CSV injection), shared by every file
the read model writes (the export, the edge ledger)."""

import re

_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def cell(text: str) -> str:
    """A cell a spreadsheet cannot run as a formula (CSV injection): text that starts with ``=``,
    ``+``, ``-``, ``@``, a tab or a CR and is not a plain number is prefixed with ``'``."""
    if text.startswith(_FORMULA) and not _NUMBER.match(text):
        return "'" + text
    return text
