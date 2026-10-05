"""A user's saved view of a screener's results (ADR 0032): the catalogue columns they added, the
sort and the decisions they show, from ``screeners.<id>.view`` of their ``preferences.toml``.

Read-only. A view is the user's, not the screener's: it is never part of a version or a hash.
A screener has a default view and any number of named ones ("VRP review", "Earnings check").
Nothing saved is not an error: the view is empty and ``saved`` is false, so the page applies
its own defaults."""

from dataclasses import dataclass

from algotrade.config.user import UserContext
from algotrade.services.explore.ideas.ranking import PREFERENCES
from algotrade.services.explore.store import ReadStore
from algotrade.services.read.ops.configs import resolved_for


@dataclass(frozen=True)
class ScreenerView:
    screener_id: str
    name: str | None  # None: the default view
    saved: bool  # false: the user has not saved this view
    columns: list[str]  # catalogue features added to the table, in order
    sort: str | None  # a ``/screens/{id}/table`` sort, None: the table's default
    decisions: list[str]  # decisions shown (none: the page's default)
    names: list[str]  # the user's named views of this screener, sorted


def screener_view(
    store: ReadStore, user: str | None, screener_id: str, name: str | None = None
) -> ScreenerView:
    """``user``'s (default: the store's) view of ``screener_id``: the default one, or the one
    called ``name``. ``NotFoundError`` for a screener the user cannot see."""
    resolved_for(store.configs, store.user, screener_id)
    who = UserContext(user).user_id if user else store.user.user_id
    doc = store.configs.load(who, PREFERENCES, PREFERENCES) or {}
    entry = (doc.get("screeners") or {}).get(screener_id) or {}
    named = dict(entry.get("views") or {})
    names = sorted(named)
    view = entry.get("view") if name is None else named.get(name)
    if not view:
        return ScreenerView(screener_id, name, False, [], None, [], names)
    sort = view.get("sort")
    return ScreenerView(
        screener_id,
        name,
        True,
        [str(c) for c in view.get("columns") or []],
        None if sort is None else str(sort),
        [str(d) for d in view.get("decisions") or []],
        names,
    )
