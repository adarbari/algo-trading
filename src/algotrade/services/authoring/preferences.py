"""Save a user's preferences (``config/users/<u>/preferences.toml``; ADR 0029, 0032): the
user's views of a table, ``views.<scope>.view`` (columns, sort, decisions shown, and
``narrow_columns``: the table column ids added back on a phone, checked by shape only) and
any named ones, ``views.<scope>.views.<name>`` (a scope names a table: ``screener:<id>`` is a
screener's results; ``services.read.screens.views``). Every id must be a screen the user can
run (their own or a site preset) and listed once, and every column a feature of the user's
catalogue, so a stale or mistyped name is never saved. A view belongs to the user, never to a
screener version: saving one changes no screen and no hash. Deleting a screener forgets it here
(``forget_screener``). ``ideas.priority`` (the Ideas screener order) is retired (owner decision
2026-10-22) and never written; an old file that holds it is read without error and the entry is
only scrubbed of a deleted screener.

Read-model PR 8 moved the views from ``screeners.<id>`` to ``views."screener:<id>"``: every
preferences write moves the old tables first (``_moved``), so a saved view is never lost and
the old layout disappears with the user's next write.

``[appearance] theme`` (ADR 0085 decision 6: ``light`` / ``dark`` / ``system``, the user's
Light / Dark / System choice) is saved by ``save_appearance``; every other write keeps the table
as it is."""

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
    SURFACE_SCOPE,
    scope_parts,
    surface_exists,
)
from algotrade.services.read.users.appearance import APPEARANCE, THEMES
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
MAX_FILTERS_LENGTH = 2000  # the ``f`` string (ADR 0082, decision 4)
DECISION = re.compile(r"[A-Z][A-Z_]*")


def _checked_filters(filters: str) -> str:
    """The ``f`` string of ADR 0082's grammar: ``;``-joined ``[!]id:body`` entries, grammar and
    length only. An id no definition names is kept (a view outlives a definition change; the
    web drops it and says so)."""
    if len(filters) > MAX_FILTERS_LENGTH or not filters.isprintable():
        raise ConfigurationError(f"view.filters: at most {MAX_FILTERS_LENGTH} printable characters")
    for entry in filters.split(";"):
        head, colon, _ = entry.partition(":")
        if not colon or not head.removeprefix("!"):
            raise ConfigurationError(f"view.filters: {entry!r} is not [!]id:value")
    return filters


def _checked_view(
    writer: ConfigWriter, who: str, columns: Sequence[str], sort: str | None,
    decisions: Sequence[str], narrow_columns: Sequence[str] = (), filters: str | None = None,
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
    if len(set(narrow_columns)) != len(narrow_columns) or len(narrow_columns) > MAX_COLUMNS:
        raise ConfigurationError(f"view.narrow_columns: each column once, at most {MAX_COLUMNS}")
    for cid in narrow_columns:  # table column ids (not only catalogue fields): shape only
        if not cid or len(cid) > 200 or cid != cid.strip() or not cid.isprintable():
            raise ConfigurationError(
                "view.narrow_columns: 1 to 200 printable characters, no space at either end"
            )
    view: dict[str, Any] = {
        "columns": list(columns),
        "decisions": list(decisions),
        "narrow_columns": list(narrow_columns),
    }
    if sort is not None:  # the read side validates it against the table's columns
        view["sort"] = sort
    if filters:  # absent: no filters (a view saved before ADR 0082 has none)
        view["filters"] = _checked_filters(filters)
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
    screener or a site preset; ``surface:<name>``: a surface with a filters file)."""
    try:
        kind, ident = scope_parts(scope)
    except ValueError as error:
        raise ConfigurationError(str(error)) from None
    if kind == SCREENER_SCOPE:
        sid = screen_id(ident)
        known = {*writer.names(who, "screeners"), *writer.names(SITE_USER, "screeners")}
        if sid not in known:
            raise ConfigurationError(f"view: {sid!r} is not your screener or a site preset")
    if kind == SURFACE_SCOPE and not surface_exists(writer, ident):
        raise ConfigurationError(f"view: {ident!r} is not a surface with a filter bar")
    return scope


def save_view(
    writer: ConfigWriter, user: str, scope: str, columns: Sequence[str], sort: str | None,
    decisions: Sequence[str], name: str | None = None,
    narrow_columns: Sequence[str] | None = None, filters: str | None = None,
) -> tuple[dict[str, Any], list[str]]:  # fmt: skip
    """Replace ``user``'s view of the table ``scope``: the default one, or the one called
    ``name`` (other views and preferences are kept); returns it and the names of the named
    views. ``narrow_columns`` None (a client from before the field): the saved ones are kept;
    ``filters`` is the ``f`` string (None or empty: none saved)."""
    who = author(user).user_id
    key = view_scope(writer, who, scope)
    named = view_name(name)
    current = _load(writer, who)
    views = dict(current.get(VIEWS) or {})
    entry = dict(views.get(key) or {})
    if narrow_columns is None:
        before = entry.get("view") if named is None else dict(entry.get("views") or {}).get(named)
        narrow_columns = [str(c) for c in (before or {}).get("narrow_columns") or []]
    view = _checked_view(writer, who, columns, sort, decisions, narrow_columns, filters)
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


def save_appearance(writer: ConfigWriter, user: str, theme: str) -> str:
    """Replace ``user``'s ``[appearance] theme`` (views and other preferences are kept);
    ``theme`` is one of ``light`` / ``dark`` / ``system``. Returns it."""
    if theme not in THEMES:
        raise ConfigurationError(f"appearance.theme: one of {', '.join(THEMES)}")
    who = author(user).user_id
    current = _load(writer, who)
    current[APPEARANCE] = {**dict(current.get(APPEARANCE) or {}), "theme": theme}
    writer.save_preferences(who, current)
    return theme
