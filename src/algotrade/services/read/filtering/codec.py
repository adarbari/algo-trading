"""``decode_filters``: the ``f`` search parameter as ``FilterInput`` values (ADR 0082 decision 4).

The web's codec (``apps/web/src/features/filter-bar/model/codec.ts``) writes it, a file route
reads it here, so a file is filtered by the very string the page shows. Grammar: filters joined by
``;``, each ``[!]id:body`` (``!``: switched off); a body is pick values (``QUALIFIED,WATCH``), a
range (``30..70``, ``..14``, ``5..``) or a window (``..5s`` sessions, ``..14d`` days); ``%XX``
escapes a ``,`` ``;`` ``:`` ``%``. A malformed entry is dropped, never raised; the first entry of a
repeated id wins; order is kept. Pure."""

import re
from urllib.parse import unquote

from algotrade.services.read.filtering.masks import FilterInput, WindowUnit, Within

_WINDOW = re.compile(r"^\.\.(\d+)([ds])$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?(e[+-]?\d+)?$")
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _unescape(text: str) -> str | None:
    if _BAD_ESCAPE.search(text):
        return None
    try:
        return unquote(text, errors="strict")
    except UnicodeDecodeError:
        return None


def _bound(text: str) -> float | bool | None:
    """The number ``text`` is, None when empty, False when it is not a number."""
    if text == "":
        return None
    return float(text) if _NUMBER.match(text) else False


def _body(id_: str, body: str, active: bool) -> FilterInput | None:
    window = _WINDOW.match(body)
    if window:
        unit = WindowUnit.SESSIONS if window.group(2) == "s" else WindowUnit.DAYS
        return FilterInput(id_, within=Within(float(window.group(1)), unit), active=active)
    at = body.find("..")
    if at >= 0 and "," not in body:
        lo, hi = _bound(body[:at]), _bound(body[at + 2 :])
        if lo is False or hi is False or (lo is None and hi is None):
            return None
        return FilterInput(
            id_,
            min=lo if isinstance(lo, float) else None,
            max=hi if isinstance(hi, float) else None,
            active=active,
        )
    values: list[str] = []
    for raw in body.split(","):
        if raw == "":
            continue
        value = _unescape(raw)
        if value is None:
            return None
        values.append(value)
    return FilterInput(id_, values=values, active=active)


def decode_filters(f: str | None) -> list[FilterInput]:
    """The filter inputs ``f`` holds (none for an empty or garbled string)."""
    if not f:
        return []
    seen: set[str] = set()
    out: list[FilterInput] = []
    for entry in f.split(";"):
        colon = entry.find(":")
        if colon < 0:
            continue
        head = entry[:colon]
        active = not head.startswith("!")
        id_ = _unescape(head if active else head[1:])
        parsed = _body(id_, entry[colon + 1 :], active) if id_ else None
        if not id_ or parsed is None or id_ in seen:
            continue
        seen.add(id_)
        out.append(parsed)
    return out
