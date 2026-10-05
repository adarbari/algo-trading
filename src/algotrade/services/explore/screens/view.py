"""A user's saved view of a screener's results (ADR 0032) for the REST GET, until read-model
PR 8 moves the screener pages to GraphQL: the view itself is ``services.read.screens.views``
(``table_view``, one reading of ``preferences.toml``); this adds the explore user default and
``NotFoundError`` for a screener the user cannot see."""

from dataclasses import dataclass

from algotrade.config.user import UserContext
from algotrade.services.explore.store import ReadStore
from algotrade.services.read.ops.configs import resolved_for
from algotrade.services.read.screens.views import table_view


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
    view = table_view(store.configs, who, screener_id, name)
    return ScreenerView(
        screener_id,
        view.name,
        view.saved,
        list(view.columns),
        view.sort,
        list(view.decisions),
        list(view.names),
    )
