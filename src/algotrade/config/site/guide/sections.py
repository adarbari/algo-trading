"""The Guide's order and grouping (``config/site/guide/sections.toml``, ADR 0051; spec
``docs/ui/guide.md`` section 3): the ``sections`` in order (``id`` one of ``SECTIONS``, a
``title`` and a one-line ``purpose``), the field ``theme_groups`` in the order a screen uses
them (each an ordered list of field-guide themes) and the playbook ``families`` (each an
ordered list of site rule-screen preset ids).

The loader checks shape only: known section ids, no id, theme or preset twice, no empty text
or list. That every field-guide theme is in exactly one group and every site preset in exactly
one family (and every listed preset exists) are fitness tests over the shipped files."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide"
NAME = "sections"
SECTIONS = ("start", "regime", "playbooks", "fields", "situations", "glossary")
SECTION_KEYS = ("id", "title", "purpose")
GROUP_KEYS = ("id", "title", "themes")
FAMILY_KEYS = ("id", "title", "presets")


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
class GuideSections:
    """``sections.toml``: the sections, theme groups and families in file order (none
    without the file)."""

    sections: tuple[GuideSectionEntry, ...] = ()
    theme_groups: tuple[ThemeGroup, ...] = ()
    families: tuple[PlaybookFamily, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "GuideSections":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("section", "theme_group", "family"))
        sections = tuple(_section(t) for t in _tables(root, "section"))
        groups = tuple(
            ThemeGroup(*_head(t, GROUP_KEYS), _list(t, "themes"))
            for t in _tables(root, "theme_group")
        )
        families = tuple(
            PlaybookFamily(*_head(t, FAMILY_KEYS), _list(t, "presets"))
            for t in _tables(root, "family")
        )
        _once(where, "section ids", (s.id for s in sections))
        _once(where, "theme group ids", (g.id for g in groups))
        _once(where, "themes", (t for g in groups for t in g.themes))
        _once(where, "family ids", (f.id for f in families))
        _once(where, "presets", (p for f in families for p in f.presets))
        return cls(sections, groups, families)

    @property
    def presets(self) -> tuple[str, ...]:
        """Every preset id the families list, in Guide order."""
        return tuple(p for f in self.families for p in f.presets)


def load_guide_sections(configs: Documents) -> GuideSections:
    """``config/site/guide/sections.toml``; missing: no sections, groups or families."""
    return GuideSections.from_document(configs.load("site", FOLDER, NAME))


def _tables(root: Table, key: str) -> list[Table]:
    raw = root.raw(key) or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{root.where} {key}: expected a list of tables ([[{key}]])")
    return [Table(e, f"{root.where} [[{key}]][{i}]") for i, e in enumerate(raw)]


def _line(t: Table, key: str) -> str:
    value = " ".join(t.text(key, "").split())
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def _head(t: Table, keys: tuple[str, ...]) -> tuple[str, str]:
    t.only(keys)
    return _line(t, "id"), _line(t, "title")


def _section(t: Table) -> GuideSectionEntry:
    t.only(SECTION_KEYS)
    section = t.choice("id", "", SECTIONS) if t.raw("id") is not None else ""
    if not section:
        raise ConfigurationError(f"{t.where} id: expected one of {', '.join(SECTIONS)}")
    return GuideSectionEntry(section, _line(t, "title"), _line(t, "purpose"))


def _list(t: Table, key: str) -> tuple[str, ...]:
    values = tuple(" ".join(s.split()) for s in t.strings(key, ()))
    if not values or not all(values):
        raise ConfigurationError(f"{t.where} {key}: expected one or more non-empty strings")
    return values


def _once(where: str, what: str, values: Iterable[str]) -> None:
    repeated = sorted(k for k, n in Counter(values).items() if n > 1)
    if repeated:
        raise ConfigurationError(f"{where}: {what} listed more than once: {repeated}")
