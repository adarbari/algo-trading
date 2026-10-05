"""A user's saved view of a screener's results (ADR 0032): the catalogue columns they added, the
sort and the decisions they show, from ``screeners.<id>.view`` of their ``preferences.toml``.

Read-only. A view is the user's, not the screener's: it is never part of a version or a hash.
Nothing saved is not an error: the view is empty and ``saved`` is false, so the page applies
its own defaults."""

from dataclasses import dataclass

from algotrade.config.user import UserContext
from algotrade.services.explore.configs import resolved
from algotrade.services.explore.ideas.ranking import PREFERENCES
from algotrade.services.explore.store import ReadStore


@dataclass(frozen=True)
class ScreenerView:
    screener_id: str
    saved: bool  # false: the user has not saved a view of this screener
    columns: list[str]  # catalogue features added to the table, in order
    sort: str | None  # a ``/screens/{id}/table`` sort, None: the table's default
    decisions: list[str]  # decisions shown (none: the page's default)


def screener_view(store: ReadStore, user: str | None, screener_id: str) -> ScreenerView:
    """``user``'s (default: the store's) saved view of ``screener_id``. ``NotFoundError``
    for a screener the user cannot see."""
    resolved(store, screener_id)
    who = UserContext(user).user_id if user else store.user.user_id
    doc = store.configs.load(who, PREFERENCES, PREFERENCES) or {}
    view = ((doc.get("screeners") or {}).get(screener_id) or {}).get("view")
    if not view:
        return ScreenerView(screener_id, False, [], None, [])
    sort = view.get("sort")
    return ScreenerView(
        screener_id,
        True,
        [str(c) for c in view.get("columns") or []],
        None if sort is None else str(sort),
        [str(d) for d in view.get("decisions") or []],
    )
