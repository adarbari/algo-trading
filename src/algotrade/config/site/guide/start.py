"""The Guide's Start here pages (``config/site/guide/start.toml``, ADR 0051; spec
``docs/ui/guide.md`` section 3, "Start here"): numbered how-to pages, one ``[[page]]`` each:
``id`` (its page's key), ``order`` (its number, from 1), ``title``, ``summary`` (one line, the
index's), ``[[page.section]]`` (``title`` and ``body``, one paragraph each, in reading order;
catalogue names in a body are linked) and ``links`` (``{kind, id}``: the Guide entries the page
sends the reader on to, ``kind`` one of ``ENTRY_KINDS``).

``ENTRY_KINDS`` are the kinds of Guide entry a reference names, in the Guide's section order:
the one list of them (search groups its results by it).

The loader checks shape only: known keys and kinds, snake_case ids (``entry_id``, the glossary's
too), non-empty text, at least one section, no
id or order twice, no link twice, no secrets; pages come in ``order``. That every link names an
existing entry of its kind and every catalogue name in the prose exists are fitness tests over
the shipped file."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide"  # the config store's kind: site/guide/start.toml
NAME = "start"
ID = re.compile(r"^[a-z0-9_]+$")  # a written entry's id: snake_case, as every Guide id
ENTRY_KINDS = ("start", "indicator", "episode", "playbook", "field", "situation", "term")
PAGE_KEYS = ("id", "order", "title", "summary", "section", "links")
SECTION_KEYS = ("title", "body")
LINK_KEYS = ("kind", "id")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class EntryRef:
    """A Guide entry by ``kind`` (one of ``ENTRY_KINDS``) and ``id`` (for a field, its
    catalogue name; a situation, its slug; an indicator or episode, its key)."""

    kind: str
    id: str


@dataclass(frozen=True)
class StartSection:
    title: str
    body: str


@dataclass(frozen=True)
class StartPage:
    """One numbered page (module docstring)."""

    id: str
    order: int
    title: str
    summary: str
    sections: tuple[StartSection, ...]
    links: tuple[EntryRef, ...] = ()

    @classmethod
    def from_table(cls, t: Table) -> "StartPage":
        t.only(PAGE_KEYS)
        if t.raw("order") is None:
            raise ConfigurationError(f"{t.where} order: required (the page's number, from 1)")
        sections = tuple(_section(s) for s in t.tables("section"))
        if not sections:
            raise ConfigurationError(f"{t.where} section: expected one or more [[page.section]]")
        links = tuple(_link(link) for link in t.tables("links"))
        unique(t.where, "links", (f"{link.kind}:{link.id}" for link in links))
        return cls(
            id=entry_id(t),
            order=t.integer("order", 1, minimum=1),
            title=t.line("title"),
            summary=t.line("summary"),
            sections=sections,
            links=links,
        )


@dataclass(frozen=True)
class GuideStart:
    """Every page, in ``order`` (none without the file)."""

    pages: tuple[StartPage, ...] = ()

    def get(self, page_id: str) -> StartPage | None:
        return next((p for p in self.pages if p.id == page_id), None)

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "GuideStart":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("page",))
        pages = tuple(StartPage.from_table(t) for t in root.tables("page"))
        unique(where, "page ids", (p.id for p in pages))
        unique(where, "page orders", (str(p.order) for p in pages))
        return cls(tuple(sorted(pages, key=lambda p: p.order)))


def load_guide_start(configs: Documents) -> GuideStart:
    """``config/site/guide/start.toml``; missing: no pages."""
    return GuideStart.from_document(configs.load("site", FOLDER, NAME))


def entry_id(t: Table) -> str:
    """``t``'s ``id``: required, snake_case (``ID``), the page's key in a URL."""
    value = t.line("id")
    if not ID.match(value):
        raise ConfigurationError(f"{t.where} id: expected snake_case (a-z, 0-9, _), got {value!r}")
    return value


def _section(t: Table) -> StartSection:
    t.only(SECTION_KEYS)
    return StartSection(t.line("title"), t.line("body"))


def _link(t: Table) -> EntryRef:
    t.only(LINK_KEYS)
    if t.raw("kind") is None:
        raise ConfigurationError(f"{t.where} kind: expected one of {', '.join(ENTRY_KINDS)}")
    return EntryRef(t.choice("kind", "", ENTRY_KINDS), t.line("id"))
