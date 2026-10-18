"""The Guide's order and grouping (``config/site/guide/sections.toml``, ADR 0051; spec
``docs/ui/guide.md`` section 3): the ``sections`` in order (``id`` one of ``SECTIONS``, a
``title`` and a one-line ``purpose``), the field ``theme_groups`` in the order a screen uses
them (each an ordered list of field-guide themes), the playbook ``families`` (each an
ordered list of site rule-screen preset ids) and the two ``edge_groups`` of the Edges section
that no edge document carries (``set_aside``, ``not_built``: each an ``id``, ``title`` and
``purpose``).

The loader checks shape only: known section ids, no id, theme or preset twice, no empty text
or list. That every field-guide theme is in exactly one group and every site preset in exactly
one family (and every listed preset exists) are fitness tests over the shipped files."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide"
NAME = "sections"
SECTIONS = ("start", "regime", "edges", "playbooks", "fields", "situations", "glossary")
SECTION_KEYS = ("id", "title", "purpose")
GROUP_KEYS = ("id", "title", "themes")
FAMILY_KEYS = ("id", "title", "presets")
EDGE_GROUP_KEYS = ("id", "title", "purpose")
EDGE_GROUPS = ("set_aside", "not_built")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class GuideSectionEntry:
    """One section of the Guide: ``id`` (one of ``SECTIONS``: what it lists), ``title``,
    ``purpose`` (one line)."""

    id: str
    title: str
    purpose: str


@dataclass(frozen=True)
class ThemeGroup:
    """Field-guide ``themes`` grouped under one ``title``, in reading order."""

    id: str
    title: str
    themes: tuple[str, ...]


@dataclass(frozen=True)
class PlaybookFamily:
    """Site rule-screen ``presets`` (ids) of one family, in reading order."""

    id: str
    title: str
    presets: tuple[str, ...]


@dataclass(frozen=True)
class EdgeGroup:
    """A group of the Edges section beside the mechanisms: ``id`` (one of ``EDGE_GROUPS``),
    ``title`` and ``purpose`` (one line)."""

    id: str
    title: str
    purpose: str


@dataclass(frozen=True)
class GuideSections:
    """``sections.toml``: the sections, theme groups and families in file order (none
    without the file)."""

    sections: tuple[GuideSectionEntry, ...] = ()
    theme_groups: tuple[ThemeGroup, ...] = ()
    families: tuple[PlaybookFamily, ...] = ()
    edge_groups: tuple[EdgeGroup, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "GuideSections":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("section", "theme_group", "family", "edge_group"))
        sections = tuple(_section(t) for t in root.tables("section"))
        groups = tuple(
            ThemeGroup(*_head(t, GROUP_KEYS), t.lines("themes")) for t in root.tables("theme_group")
        )
        families = tuple(
            PlaybookFamily(*_head(t, FAMILY_KEYS), t.lines("presets"))
            for t in root.tables("family")
        )
        edge_groups = tuple(_edge_group(t) for t in root.tables("edge_group"))
        unique(where, "edge group ids", (g.id for g in edge_groups))
        unique(where, "section ids", (s.id for s in sections))
        unique(where, "theme group ids", (g.id for g in groups))
        unique(where, "themes", (t for g in groups for t in g.themes))
        unique(where, "family ids", (f.id for f in families))
        unique(where, "presets", (p for f in families for p in f.presets))
        return cls(sections, groups, families, edge_groups)

    @property
    def presets(self) -> tuple[str, ...]:
        """Every preset id the families list, in Guide order."""
        return tuple(p for f in self.families for p in f.presets)


def load_guide_sections(configs: Documents) -> GuideSections:
    """``config/site/guide/sections.toml``; missing: no sections, groups or families."""
    return GuideSections.from_document(configs.load("site", FOLDER, NAME))


def _head(t: Table, keys: tuple[str, ...]) -> tuple[str, str]:
    t.only(keys)
    return t.line("id"), t.line("title")


def _section(t: Table) -> GuideSectionEntry:
    t.only(SECTION_KEYS)
    section = t.choice("id", "", SECTIONS) if t.raw("id") is not None else ""
    if not section:
        raise ConfigurationError(f"{t.where} id: expected one of {', '.join(SECTIONS)}")
    return GuideSectionEntry(section, t.line("title"), t.line("purpose"))


def _edge_group(t: Table) -> EdgeGroup:
    t.only(EDGE_GROUP_KEYS)
    group = t.choice("id", "", EDGE_GROUPS) if t.raw("id") is not None else ""
    if not group:
        raise ConfigurationError(f"{t.where} id: expected one of {', '.join(EDGE_GROUPS)}")
    return EdgeGroup(group, t.line("title"), t.line("purpose"))
