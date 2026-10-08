"""The Guide's playbook prose (``config/site/guide/playbooks/<id>.toml``, ADR 0051; spec
``docs/ui/guide.md`` "The playbook page"): one file per site rule-screen preset, kept apart
from the preset because a preset version is immutable and its explanation is not. Keys:
``id`` (the file's name), ``version`` (the preset version the prose was written for: a new
preset version fails a fitness test until the prose is re-read and the number raised),
``summary`` (the page's hero), ``hit`` (what a hit looks like),
``not_checked`` (what it does not check), ``before_acting`` (the caveats, one string each),
``related`` (``{id, reason}``: other playbooks), ``sources`` and the ``[asks]`` table (each
criterion of the preset's latest version in a few plain words, for the criteria table). The
family is ``sections.toml``'s and is never repeated here.

The loader checks shape only: known keys, non-empty text, the id matching its file, no related
id twice or naming itself, no secrets. That every site preset has exactly one playbook, that
``asks`` names exactly the latest version's criteria, that every related id exists and that
every catalogue name in the prose exists are fitness tests over the shipped files."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide_playbooks"  # the config store's kind: site/guide/playbooks/<id>.toml
KEYS = (
    "id",
    "version",
    "summary",
    "hit",
    "not_checked",
    "before_acting",
    "related",
    "sources",
    "asks",
)
TEXTS = ("summary", "hit", "not_checked")
RELATED_KEYS = ("id", "reason")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


@dataclass(frozen=True)
class RelatedPlaybook:
    """Another playbook worth reading next, and why (a few words)."""

    id: str
    reason: str


@dataclass(frozen=True)
class PlaybookProse:
    """One playbook's prose (module docstring); ``asks`` in file order."""

    id: str
    version: int
    summary: str
    hit: str
    not_checked: str
    before_acting: tuple[str, ...]
    related: tuple[RelatedPlaybook, ...]
    sources: tuple[str, ...]
    asks: tuple[tuple[str, str], ...]

    def ask(self, criterion: str) -> str | None:
        """What ``criterion`` asks, in words (``None``: not written)."""
        return dict(self.asks).get(criterion)

    @classmethod
    def from_document(cls, name: str, doc: Mapping[str, Any] | None) -> "PlaybookProse":
        where = f"guide/playbooks/{name}.toml"
        reject_secrets(doc or {}, where)
        t = Table(doc, where)
        t.only(KEYS)
        if _line(t, "id") != name:
            raise ConfigurationError(f"{where} id: expected {name!r} (the file's name)")
        if t.raw("version") is None:
            raise ConfigurationError(f"{where} version: required (the preset version written for)")
        version = t.integer("version", 1, minimum=1)
        related = tuple(_related(t, name))
        ids = [r.id for r in related]
        if len(ids) != len(set(ids)):
            raise ConfigurationError(f"{where} related: an id listed more than once: {ids}")
        asks = t.table("asks", t.raw("asks") or {})
        return cls(
            id=name,
            version=version,
            summary=_line(t, "summary"),
            hit=_line(t, "hit"),
            not_checked=_line(t, "not_checked"),
            before_acting=_lines(t, "before_acting"),
            related=related,
            sources=_lines(t, "sources"),
            asks=tuple((key, _line(asks, key)) for key in asks.names()),
        )


@dataclass(frozen=True)
class GuidePlaybooks:
    """Every playbook file, by id (none without files)."""

    playbooks: tuple[PlaybookProse, ...] = ()

    def get(self, playbook_id: str) -> PlaybookProse | None:
        return next((p for p in self.playbooks if p.id == playbook_id), None)


def load_guide_playbooks(configs: Documents) -> GuidePlaybooks:
    """``config/site/guide/playbooks/*.toml`` in file-name order."""
    names = configs.names("site", FOLDER)
    return GuidePlaybooks(
        tuple(PlaybookProse.from_document(n, configs.load("site", FOLDER, n)) for n in names)
    )


def _line(t: Table, key: str) -> str:
    """``key`` with its whitespace collapsed; required and non-empty."""
    value = " ".join(t.text(key, "").split())
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def _lines(t: Table, key: str) -> tuple[str, ...]:
    values = tuple(" ".join(v.split()) for v in t.strings(key, ()))
    if not values or not all(values):
        raise ConfigurationError(f"{t.where} {key}: expected one or more non-empty strings")
    return values


def _related(t: Table, name: str) -> list[RelatedPlaybook]:
    raw = t.raw("related") or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{t.where} related: expected a list of {{id, reason}} tables")
    found = []
    for i, entry in enumerate(raw):
        row = Table(entry, f"{t.where} related[{i}]")
        row.only(RELATED_KEYS)
        related = RelatedPlaybook(_line(row, "id"), _line(row, "reason"))
        if related.id == name:
            raise ConfigurationError(f"{row.where} id: a playbook is not related to itself")
        found.append(related)
    return found
