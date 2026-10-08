"""A user's saved view of a table (ADR 0032, ``TableView``): the catalogue columns they added,
the sort and the decisions they show, from ``views.<scope>.view`` (the default view) or
``views.<scope>.views.<name>`` of their ``preferences.toml`` (read-model PR 8 generalised it
from ``screeners.<id>``). A scope names a table: ``screener:<id>`` is a screener's results
(``SCOPE_KINDS``). A view saved before PR 8 under ``screeners.<id>`` is still read as
``screener:<id>``'s until the user's next preferences write moves it
(``services.authoring.preferences``).

A view is the user's, never the screener's: not part of a version or a hash. Nothing saved
is not an error: ``saved`` is false and the lists are empty, so the page applies its own
defaults."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.screeners import load_screener
from algotrade.storage.configs.store import ConfigStore

PREFERENCES = "preferences"
SCREENER_SCOPE = "screener"  # ``screener:<id>``: a screener's results
SCOPE_KINDS = (SCREENER_SCOPE,)
LEGACY_SCREENERS = "screeners"  # where PR 5-7 saved a screener's views (``screeners.<id>``)


@dataclass(frozen=True)
class TableView:
    """``scope``: the table the view is of (``screener:<id>``); ``name``: None for the default
    view; ``names``: the user's named views of the scope, sorted; ``sort``: a column id, ``-``
    first for descending (None: the table's default); ``narrow_columns``: the table column ids
    the user added back on a narrow (phone) table."""

    scope: str
    name: str | None
    saved: bool
    columns: tuple[str, ...]
    sort: str | None
    decisions: tuple[str, ...]
    names: tuple[str, ...]
    narrow_columns: tuple[str, ...] = ()


def scope_parts(scope: str) -> tuple[str, str]:
    """``(kind, id)`` of ``scope`` (``screener:vrp_scanner`` -> ``("screener",
    "vrp_scanner")``); ``ValueError`` for a scope of no known kind."""
    kind, _, ident = scope.partition(":")
    if kind not in SCOPE_KINDS or not ident:
        raise ValueError(f"view scope {scope!r}: expected one of {', '.join(SCOPE_KINDS)}:<id>")
    return kind, ident


def view_entry(doc: Mapping[str, Any], scope: str) -> Mapping[str, Any]:
    """The ``views.<scope>`` table of a preferences document (else the pre-PR 8
    ``screeners.<id>`` one of a screener scope; else empty)."""
    entry = (doc.get("views") or {}).get(scope)
    if entry:
        return dict(entry)
    kind, ident = scope_parts(scope)
    legacy = (doc.get(LEGACY_SCREENERS) or {}).get(ident) if kind == SCREENER_SCOPE else None
    return dict(legacy or {})


def table_view(configs: ConfigStore, user: str, scope: str, name: str | None = None) -> TableView:
    """``user``'s view of ``scope`` (the default one, or the one called ``name``)."""
    doc = configs.load(user, PREFERENCES, PREFERENCES) or {}
    entry = view_entry(doc, scope)
    named = dict(entry.get("views") or {})
    names = tuple(sorted(named))
    view = entry.get("view") if name is None else named.get(name)
    if not view:
        return TableView(scope, name, False, (), None, (), names)
    sort = view.get("sort")
    return TableView(
        scope=scope,
        name=name,
        saved=True,
        columns=tuple(str(c) for c in view.get("columns") or []),
        sort=None if sort is None else str(sort),
        decisions=tuple(str(d) for d in view.get("decisions") or []),
        names=names,
        narrow_columns=tuple(str(c) for c in view.get("narrow_columns") or []),
    )


def load_view(ctx: ReadContext, scope: str, name: str | None = None) -> TableView | None:
    """The user's view of the table ``scope``; ``None`` for a scope of no known kind or a
    screener they do not see."""
    try:
        kind, ident = scope_parts(scope)
    except ValueError:
        return None
    if kind == SCREENER_SCOPE and load_screener(ctx, ident) is None:
        return None
    return table_view(ctx.configs, ctx.user.user_id, scope, name)
