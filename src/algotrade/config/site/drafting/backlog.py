"""``feature_backlog.toml``: the curated list of features traders ask for that the catalogue
does not have yet, typed and validated (an unknown key or a bad value names the file and entry).

Each ``[[item]]`` has a ``key`` (slug), a one-line ``description``, a ``feasibility`` (can it be
rolled up from stored data, does it need a new source, or is that unclear), ``aliases`` (other
slugs that mean it), a ``status`` and, once built, the catalogue feature it ``promoted_to``;
``closest`` names the catalogue features that come nearest. Whether the catalogue names exist is
checked against the catalogue by a fitness test, not here (the loader has no catalogue)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

FEASIBILITY = ("ROLLUP_FROM_STORED", "NEEDS_SOURCE", "UNCLEAR")
STATUS = ("OPEN", "PROMOTED", "WONT_DO")
ITEM_KEYS = ("key", "description", "feasibility", "aliases", "status", "promoted_to", "closest")
SLUG = re.compile(r"^[a-z0-9_]+$")
PROMPT_LIMIT = 60


@dataclass(frozen=True)
class BacklogItem:
    """One missing feature: what it is, how hard, and where it stands."""

    key: str
    description: str
    feasibility: str
    status: str = "OPEN"
    aliases: tuple[str, ...] = ()
    promoted_to: str = ""
    closest: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureBacklogSettings:
    """``feature_backlog.toml``: the items in file order (none without the file)."""

    items: tuple[BacklogItem, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "FeatureBacklogSettings":
        where = "feature_backlog.toml"
        root = Table(doc, where)
        root.only(("item",))
        raw = root.raw("item") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{where} item: expected a list of tables ([[item]])")
        items = tuple(_item(Table(e, f"{where} [[item]][{i}]")) for i, e in enumerate(raw))
        _check_unique(items, where)
        return cls(items)


def _slug(t: Table, name: str, value: str) -> str:
    if not SLUG.match(value):
        raise ConfigurationError(
            f"{t.where} {name}: expected a slug of a-z, 0-9 and _, got {value!r}"
        )
    return value


def _item(t: Table) -> BacklogItem:
    t.only(ITEM_KEYS)
    key = _slug(t, "key", t.text("key", ""))
    status = t.choice("status", "OPEN", STATUS)
    promoted = t.text("promoted_to", "")
    if (status == "PROMOTED") != bool(promoted):
        raise ConfigurationError(
            f"{t.where} promoted_to: required when status is PROMOTED and only then ({key})"
        )
    aliases = tuple(_slug(t, "aliases", a) for a in t.strings("aliases", ()))
    return BacklogItem(
        key=key,
        description=t.line("description"),
        feasibility=t.choice("feasibility", "", FEASIBILITY),
        status=status,
        aliases=aliases,
        promoted_to=promoted,
        closest=t.strings("closest", ()),
    )


def _check_unique(items: tuple[BacklogItem, ...], where: str) -> None:
    """Every key and alias names one item: no key twice, no alias twice or equal to any key."""
    owner = {item.key: item.key for item in items}
    if len(owner) != len(items):
        dup = sorted({i.key for i in items if [j.key for j in items].count(i.key) > 1})
        raise ConfigurationError(f"{where}: key appears twice: {dup}")
    for item in items:
        for alias in item.aliases:
            if alias in owner:
                raise ConfigurationError(
                    f"{where}: alias {alias!r} of {item.key!r} is already a key or alias of "
                    f"{owner[alias]!r}"
                )
            owner[alias] = item.key


def open_keys(
    settings: FeatureBacklogSettings, limit: int = PROMPT_LIMIT
) -> tuple[tuple[str, str], ...]:
    """The OPEN items as (key, description), sorted by key and capped at ``limit``: the list a
    prompt may show."""
    open_items = sorted((i for i in settings.items if i.status == "OPEN"), key=lambda i: i.key)
    return tuple((i.key, i.description) for i in open_items[:limit])
