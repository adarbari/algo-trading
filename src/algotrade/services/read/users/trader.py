"""``TraderPreferences``: the trader site's two stored choices (ADR 0083, amendment 2026-11-01):
``[ideas] default_tab`` (``stocks`` / ``premium``, the one sign-up answer; ``None`` until the
user answered, which is what shows the onboarding question) and ``[watchlist] instruments``
(instrument ids only, never a position, size, basis or account). Per user, read through the
``ConfigStore``, never from ``Viewer``; session-free (a ``Stores``), and when the context has a
session each id also carries its ticker. A malformed stored value reads as absent. Written by
``services.authoring.preferences.save_watchlist`` / ``save_ideas_tab``."""

from dataclasses import dataclass

from algotrade.data.reference import resolver
from algotrade.services.read.context import ReadContext, Stores
from algotrade.services.read.screens.views import PREFERENCES

IDEAS_TABS = ("stocks", "premium")
WATCHLIST = "watchlist"
MAX_WATCHLIST = 50


@dataclass(frozen=True)
class WatchedInstrument:
    instrument_id: str
    symbol: str | None  # None: no session, or the snapshot no longer lists it


@dataclass(frozen=True)
class TraderPreferences:
    default_tab: str | None  # one of IDEAS_TABS, None: not answered yet
    watchlist: tuple[WatchedInstrument, ...]


def load_trader_preferences(ctx: Stores) -> TraderPreferences:
    """``ctx.user``'s default Ideas tab and watchlist (at most 50 ids, in saved order)."""
    doc = ctx.configs.load(ctx.user.user_id, PREFERENCES, PREFERENCES) or {}
    ideas = doc.get("ideas")
    tab = ideas.get("default_tab") if isinstance(ideas, dict) else None
    table = doc.get(WATCHLIST)
    raw = table.get("instruments") if isinstance(table, dict) else None
    ids = [i for i in raw if isinstance(i, str)] if isinstance(raw, list) else []
    names = resolver(ctx.reader, ctx.session.date) if isinstance(ctx, ReadContext) else None
    return TraderPreferences(
        tab if isinstance(tab, str) and tab in IDEAS_TABS else None,
        tuple(
            WatchedInstrument(i, names.symbol_for(i) if names is not None else None)
            for i in dict.fromkeys(ids)
        )[:MAX_WATCHLIST],
    )
