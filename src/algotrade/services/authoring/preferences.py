"""Save a user's preferences (``config/users/<u>/preferences.toml``; ADR 0029, 0032): the
Ideas screener priority, ``ideas.priority`` (screener ids, best first), and the user's view of
a screener's results, ``screeners.<id>.view`` (columns, sort, decisions shown) and any named
ones, ``screeners.<id>.views.<name>``. Every id must be
a screen the user can run (their own or a site preset) and listed once, and every column a
feature of the user's catalogue, so a stale or mistyped name is never saved. A view belongs to
the user, never to a screener version: saving one changes no screen and no hash."""

import re
from collections.abc import Sequence
from typing import Any

from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import ScreenNotFoundError, author, screen_id
from algotrade.services.configs import catalog_of
from algotrade.services.features import catalogue
from algotrade.storage.configs.writer import ConfigWriter

PREFERENCES = "preferences"


def save_ideas_priority(writer: ConfigWriter, user: str, priority: Sequence[str]) -> list[str]:
    """Replace ``user``'s ``ideas.priority`` (other preferences are kept); returns it."""
    who = author(user).user_id
    ids = [screen_id(i) for i in priority]
    if len(set(ids)) != len(ids):
        raise ConfigurationError("ideas.priority lists a screener twice")
    known = {*writer.names(who, "screeners"), *writer.names(SITE_USER, "screeners")}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ConfigurationError(f"ideas.priority: not your screeners or site presets: {unknown}")
    current: dict[str, Any] = dict(writer.load(who, PREFERENCES, PREFERENCES) or {})
    current["ideas"] = {**dict(current.get("ideas") or {}), "priority": ids}
    writer.save_preferences(who, current)
    return ids


MAX_COLUMNS = 40
MAX_VIEW_NAME = 40
MAX_DECISIONS = 12
DECISION = re.compile(r"[A-Z][A-Z_]*")


def _checked_view(
    writer: ConfigWriter, who: str, columns: Sequence[str], sort: str | None,
    decisions: Sequence[str],
) -> dict[str, Any]:  # fmt: skip
    if len(set(columns)) != len(columns) or len(columns) > MAX_COLUMNS:
        raise ConfigurationError(f"view.columns: each column once, at most {MAX_COLUMNS}")
    known = catalog_of(catalogue(writer, who))
    for name in columns:
        known.check_field(name, "view.columns")
    if len(set(decisions)) != len(decisions) or len(decisions) > MAX_DECISIONS:
        raise ConfigurationError(f"view.decisions: each decision once, at most {MAX_DECISIONS}")
    bad = [d for d in decisions if not DECISION.fullmatch(d)]
    if bad:
        raise ConfigurationError(f"view.decisions: not decisions: {bad}")
    if sort is not None and (not sort.strip() or len(sort) > 200 or sort != sort.strip()):
        raise ConfigurationError("view.sort: a column name, with '-' in front for descending")
    view: dict[str, Any] = {"columns": list(columns), "decisions": list(decisions)}
    if sort is not None:  # the read side validates it against the table's columns
        view["sort"] = sort
    return view


def view_name(name: str | None) -> str | None:
    """A named view's name (None: the screener's default view): 1 to 40 characters, no control
    characters, no space at either end."""
    if name is None:
        return None
    if not name or name != name.strip() or len(name) > MAX_VIEW_NAME or not name.isprintable():
        raise ConfigurationError(
            f"view name: 1 to {MAX_VIEW_NAME} printable characters, no space at either end"
        )
    return name


def _known_screener(writer: ConfigWriter, who: str, screener: str) -> str:
    sid = screen_id(screener)
    known = {*writer.names(who, "screeners"), *writer.names(SITE_USER, "screeners")}
    if sid not in known:
        raise ConfigurationError(f"view: {sid!r} is not your screener or a site preset")
    return sid


def save_screener_view(
    writer: ConfigWriter, user: str, screener: str, columns: Sequence[str], sort: str | None,
    decisions: Sequence[str], name: str | None = None,
) -> tuple[dict[str, Any], list[str]]:  # fmt: skip
    """Replace ``user``'s view of ``screener``: the default one, or the one called ``name``
    (other views and preferences are kept); returns it and the names of the named views."""
    who = author(user).user_id
    sid = _known_screener(writer, who, screener)
    key = view_name(name)
    view = _checked_view(writer, who, columns, sort, decisions)
    current: dict[str, Any] = dict(writer.load(who, PREFERENCES, PREFERENCES) or {})
    screeners = dict(current.get("screeners") or {})
    entry = dict(screeners.get(sid) or {})
    if key is None:
        entry["view"] = view
    else:
        entry["views"] = {**dict(entry.get("views") or {}), key: view}
    screeners[sid] = entry
    current["screeners"] = screeners
    writer.save_preferences(who, current)
    return view, sorted(entry.get("views") or {})


def delete_screener_view(writer: ConfigWriter, user: str, screener: str, name: str) -> list[str]:
    """Remove ``user``'s view of ``screener`` called ``name`` (the default view is replaced, not
    removed); returns the names of the views left. ``ScreenNotFoundError``: no such view."""
    who = author(user).user_id
    sid = _known_screener(writer, who, screener)
    key = view_name(name)
    current: dict[str, Any] = dict(writer.load(who, PREFERENCES, PREFERENCES) or {})
    screeners = dict(current.get("screeners") or {})
    entry = dict(screeners.get(sid) or {})
    views = dict(entry.get("views") or {})
    if key is None or key not in views:
        raise ScreenNotFoundError(f"{sid}: no view called {name!r}")
    del views[key]
    entry["views"] = views
    screeners[sid] = entry
    current["screeners"] = screeners
    writer.save_preferences(who, current)
    return sorted(views)
