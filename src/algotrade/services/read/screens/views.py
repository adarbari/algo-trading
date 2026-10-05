"""A user's saved view of a table (ADR 0032, ``TableView``): the catalogue columns they added,
the sort and the decisions they show, from ``screeners.<id>.view`` (the default view) or
``screeners.<id>.views.<name>`` of their ``preferences.toml``. Today a scope is a screener id
(its results table); read-model PR 8 widens it to every table (``views.<scope>``).

A view is the user's, never the screener's: not part of a version or a hash. Nothing saved
is not an error: ``saved`` is false and the lists are empty, so the page applies its own
defaults."""

from dataclasses import dataclass

from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.screeners import load_screener
from algotrade.storage.configs.store import ConfigStore

PREFERENCES = "preferences"


@dataclass(frozen=True)
class TableView:
    """``scope``: the table the view is of (a screener id); ``name``: None for the default
    view; ``names``: the user's named views of the scope, sorted; ``sort``: a column id, ``-``
    first for descending (None: the table's default)."""

    scope: str
    name: str | None
    saved: bool
    columns: tuple[str, ...]
    sort: str | None
    decisions: tuple[str, ...]
    names: tuple[str, ...]


def table_view(configs: ConfigStore, user: str, scope: str, name: str | None = None) -> TableView:
    """``user``'s view of ``scope`` (the default one, or the one called ``name``)."""
    doc = configs.load(user, PREFERENCES, PREFERENCES) or {}
    entry = (doc.get("screeners") or {}).get(scope) or {}
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
    )


def load_view(ctx: ReadContext, scope: str, name: str | None = None) -> TableView | None:
    """The user's view of the screener ``scope``; ``None`` for a screener they do not see."""
    if load_screener(ctx, scope) is None:
        return None
    return table_view(ctx.configs, ctx.user.user_id, scope, name)
