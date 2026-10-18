"""The Guide's mechanism pages (``config/site/guide/mechanisms/<id>.toml``, ADR 0051; spec
``docs/ui/guide.md``, the Edges section): one file per ``MECHANISM_KINDS`` value
(``config/edges/document.py``), the reason an edge should work, kept apart from the edge
documents that name it. Keys: ``id`` (the file's name and the edge documents' ``mechanism_kind``),
``title``, ``question`` (the card's question), ``examples`` (one short line of edges), ``short``
(the card's hero), ``how_it_works``, ``why_it_survives``, ``research`` and ``real_vs_decoy``
(paragraphs, one string each), ``dont`` (the one thing not to read into it), ``see_also``
(glossary term ids), the optional ``[[stats]]`` tiles (``label``, ``value``, ``note``, ``source``:
an optional 1-based index into ``[[sources]]``) and ``[[sources]]`` (``title``, ``url`` https,
``note``).

The loader checks shape only: known keys, non-empty text, the id matching its file, https urls,
no url or see_also id twice, no secrets. That there is exactly one file per mechanism kind, every
see_also id is a glossary term and the writing style holds are fitness tests over the shipped
files. Files load in file-name order; the read model orders them by ``MECHANISM_KINDS``."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.config.site.guide.start import entry_id
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide_mechanisms"  # the config store's kind: site/guide/mechanisms/<id>.toml
KEYS = (
    "id", "title", "question", "examples", "short", "how_it_works", "why_it_survives",
    "research", "real_vs_decoy", "dont", "see_also", "stats", "sources",
)  # fmt: skip
STAT_KEYS = ("label", "value", "note", "source")
SOURCE_KEYS = ("title", "url", "note")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


@dataclass(frozen=True)
class MechanismStat:
    """One tile: ``label``, ``value`` (as shown), ``note``; ``source``: 1-based index into
    the mechanism's sources (``None``: our own bar, from ``config/site/verdict.toml``)."""

    label: str
    value: str
    note: str
    source: int | None = None


@dataclass(frozen=True)
class MechanismSource:
    """One source: ``title`` (the citation), ``url`` (https) and ``note`` (what it shows)."""

    title: str
    url: str
    note: str


@dataclass(frozen=True)
class MechanismProse:
    """One mechanism's page (module docstring); lists in file order."""

    id: str
    title: str
    question: str
    examples: str
    short: str
    how_it_works: tuple[str, ...]
    why_it_survives: tuple[str, ...]
    research: tuple[str, ...]
    real_vs_decoy: tuple[str, ...]
    dont: str
    see_also: tuple[str, ...]
    stats: tuple[MechanismStat, ...]
    sources: tuple[MechanismSource, ...]

    @classmethod
    def from_document(cls, name: str, doc: Mapping[str, Any] | None) -> "MechanismProse":
        where = f"guide/mechanisms/{name}.toml"
        reject_secrets(doc or {}, where)
        t = Table(doc, where)
        t.only(KEYS)
        if entry_id(t) != name:
            raise ConfigurationError(f"{where} id: expected {name!r} (the file's name)")
        sources = tuple(_source(s) for s in t.tables("sources"))
        unique(where, "source urls", (s.url for s in sources))
        see_also = t.lines("see_also", required=False)
        unique(where, "see_also ids", see_also)
        return cls(
            id=name,
            title=t.line("title"),
            question=t.line("question"),
            examples=t.line("examples"),
            short=t.line("short"),
            how_it_works=t.lines("how_it_works"),
            why_it_survives=t.lines("why_it_survives"),
            research=t.lines("research"),
            real_vs_decoy=t.lines("real_vs_decoy"),
            dont=t.line("dont"),
            see_also=see_also,
            stats=tuple(_stat(s, len(sources)) for s in t.tables("stats")),
            sources=sources,
        )


@dataclass(frozen=True)
class GuideMechanisms:
    """Every mechanism file, in file-name order (none without files)."""

    mechanisms: tuple[MechanismProse, ...] = ()

    def get(self, mechanism_id: str) -> MechanismProse | None:
        return next((m for m in self.mechanisms if m.id == mechanism_id), None)


def load_guide_mechanisms(configs: Documents) -> GuideMechanisms:
    """``config/site/guide/mechanisms/*.toml`` in file-name order."""
    names = configs.names("site", FOLDER)
    docs = (MechanismProse.from_document(n, configs.load("site", FOLDER, n)) for n in names)
    mechanisms = tuple(docs)
    unique("guide/mechanisms", "titles", (m.title.lower() for m in mechanisms))
    return GuideMechanisms(mechanisms)


def _stat(t: Table, sources: int) -> MechanismStat:
    t.only(STAT_KEYS)
    source = t.integer("source", 0, minimum=1) if t.raw("source") is not None else None
    if source is not None and source > sources:
        raise ConfigurationError(f"{t.where} source: {source} but there are {sources} sources")
    return MechanismStat(t.line("label"), t.line("value"), t.line("note"), source)


def _source(t: Table) -> MechanismSource:
    t.only(SOURCE_KEYS)
    url = t.line("url")
    if not url.startswith("https://") or " " in url:
        raise ConfigurationError(f"{t.where} url: expected an https url, got {url!r}")
    return MechanismSource(t.line("title"), url, t.line("note"))
