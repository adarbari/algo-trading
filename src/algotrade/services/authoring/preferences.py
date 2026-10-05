"""Save a user's preferences (``config/users/<u>/preferences.toml``; ADR 0029, 0032): the
Ideas screener priority, ``ideas.priority`` (screener ids, best first), and the user's views of
a table, ``views.<scope>.view`` (columns, sort, decisions shown) and any named ones,
``views.<scope>.views.<name>`` (a scope names a table: ``screener:<id>`` is a screener's
results; ``services.read.screens.views``). Every id must be a screen the user can run (their
own or a site preset) and listed once, and every column a feature of the user's catalogue, so a
stale or mistyped name is never saved. A view belongs to the user, never to a screener version:
saving one changes no screen and no hash. Deleting a screener forgets it here
(``forget_screener``).

Read-model PR 8 moved the views from ``screeners.<id>`` to ``views."screener:<id>"``: every
preferences write moves the old tables first (``_moved``), so a saved view is never lost and
the old layout disappears with the user's next write."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import ScreenNotFoundError, author, screen_id
from algotrade.services.configs import catalog_of
from algotrade.services.features import catalogue
from algotrade.services.read.screens.views import (
    LEGACY_SCREENERS,
    SCREENER_SCOPE,
    scope_parts,
)
from algotrade.storage.configs.writer import ConfigWriter

PREFERENCES = "preferences"
VIEWS = "views"


def _moved(document: Mapping[str, Any] | None) -> dict[str, Any]:
    """``document`` with its pre-PR 8 ``screeners.<id>`` views under
    ``views."screener:<id>"`` (a view already saved there wins)."""
    current: dict[str, Any] = dict(document or {})
    legacy = dict(current.pop(LEGACY_SCREENERS, None) or {})
    if legacy:
        views = dict(current.get(VIEWS) or {})
        for ident, entry in legacy.items():
            scope = f"{SCREENER_SCOPE}:{ident}"
            views[scope] = {**dict(entry or {}), **dict(views.get(scope) or {})}
        current[VIEWS] = views
    return current


def _load(writer: ConfigWriter, user: str) -> dict[str, Any]:
    return _moved(writer.load(user, PREFERENCES, PREFERENCES))


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
    current = _load(writer, who)
    current["ideas"] = {**dict(current.get("ideas") or {}), "priority": ids}
    writer.save_preferences(who, current)
    return ids


def forget_screener(writer: ConfigWriter, user: str, name: str) -> None:
    """Drop ``name`` from ``user``'s preferences: ``ideas.priority`` and its views."""
    stored = writer.load(user, PREFERENCES, PREFERENCES) or {}
    current = _moved(stored)
    ideas = dict(current.get("ideas") or {})
    views = dict(current.get(VIEWS) or {})
    priority = list(ideas.get("priority") or [])
    scope = f"{SCREENER_SCOPE}:{name}"
    if name not in priority and scope not in views and current == stored:
        return
    if "priority" in ideas:
        ideas["priority"] = [i for i in priority if i != name]
        current["ideas"] = ideas
    views.pop(scope, None)
    if VIEWS in current:
        current[VIEWS] = views
    writer.save_preferences(user, current)


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
    """A named view's name (None: the table's default view): 1 to 40 characters, no control
    characters, no space at either end."""
    if name is None:
        return None
    if not name or name != name.strip() or len(name) > MAX_VIEW_NAME or not name.isprintable():
        raise ConfigurationError(
            f"view name: 1 to {MAX_VIEW_NAME} printable characters, no space at either end"
        )
    return name


def view_scope(writer: ConfigWriter, who: str, scope: str) -> str:
    """``scope`` checked: a known kind naming a table the user has (``screener:<id>``: their
    screener or a site preset)."""
    try:
        kind, ident = scope_parts(scope)
    except ValueError as error:
        raise ConfigurationError(str(error)) from None
    if kind == SCREENER_SCOPE:
        sid = screen_id(ident)
        known = {*writer.names(who, "screeners"), *writer.names(SITE_USER, "screeners")}
        if sid not in known:
            raise ConfigurationError(f"view: {sid!r} is not your screener or a site preset")
    return scope


def save_view(
    writer: ConfigWriter, user: str, scope: str, columns: Sequence[str], sort: str | None,
    decisions: Sequence[str], name: str | None = None,
) -> tuple[dict[str, Any], list[str]]:  # fmt: skip
    """Replace ``user``'s view of the table ``scope``: the default one, or the one called
    ``name`` (other views and preferences are kept); returns it and the names of the named
    views."""
    who = author(user).user_id
    key = view_scope(writer, who, scope)
    named = view_name(name)
    view = _checked_view(writer, who, columns, sort, decisions)
    current = _load(writer, who)
    views = dict(current.get(VIEWS) or {})
    entry = dict(views.get(key) or {})
    if named is None:
        entry["view"] = view
    else:
        entry["views"] = {**dict(entry.get("views") or {}), named: view}
    views[key] = entry
    current[VIEWS] = views
    writer.save_preferences(who, current)
    return view, sorted(entry.get("views") or {})


def delete_view(writer: ConfigWriter, user: str, scope: str, name: str) -> list[str]:
    """Remove ``user``'s view of ``scope`` called ``name`` (the default view is replaced, not
    removed); returns the names of the views left. ``ScreenNotFoundError``: no such view."""
    who = author(user).user_id
    key = view_scope(writer, who, scope)
    named = view_name(name)
    current = _load(writer, who)
    views = dict(current.get(VIEWS) or {})
    entry = dict(views.get(key) or {})
    named_views = dict(entry.get("views") or {})
    if named is None or named not in named_views:
        raise ScreenNotFoundError(f"{key}: no view called {name!r}")
    del named_views[named]
    entry["views"] = named_views
    views[key] = entry
    current[VIEWS] = views
    writer.save_preferences(who, current)
    return sorted(named_views)
