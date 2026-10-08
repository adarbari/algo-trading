"""The Guide's glossary (``config/site/guide/glossary.toml``, ADR 0051; spec ``docs/ui/guide.md``
section 3, "Glossary"): the app's own words and the rule grammar, one ``[[term]]`` each:
``id`` (its page's key), ``term`` (as the app writes it: ``NOT_RUN``, ``on_miss``,
``Near miss``), ``short`` (one sentence: the help button's hover and the drawer's first line),
``body`` (a short paragraph; catalogue names in it are linked) and ``see_also`` (other term
ids, in reading order).

The loader checks shape only: known keys, snake_case ids, non-empty text, no id or term twice
(terms compared without case), no ``see_also`` naming the term itself or another twice, no
secrets. That every
``see_also`` id is a term, every catalogue name in the prose exists, ``short`` is one sentence
and every term the spec lists is written are fitness tests over the shipped file."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.config.site.guide.start import entry_id
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide"  # the config store's kind: site/guide/glossary.toml
NAME = "glossary"
TERM_KEYS = ("id", "term", "short", "body", "see_also")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class GlossaryTerm:
    """One term (module docstring); ``see_also`` in file order."""

    id: str
    term: str
    short: str
    body: str
    see_also: tuple[str, ...] = ()

    @classmethod
    def from_table(cls, t: Table) -> "GlossaryTerm":
        t.only(TERM_KEYS)
        term_id = entry_id(t)
        see_also = t.lines("see_also", required=False)
        if term_id in see_also:
            raise ConfigurationError(f"{t.where} see_also: a term does not refer to itself")
        unique(t.where, "see_also ids", see_also)
        return cls(term_id, t.line("term"), t.line("short"), t.line("body"), see_also)


@dataclass(frozen=True)
class GuideGlossary:
    """Every term in file order (none without the file)."""

    terms: tuple[GlossaryTerm, ...] = ()

    def get(self, term_id: str) -> GlossaryTerm | None:
        return next((t for t in self.terms if t.id == term_id), None)

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "GuideGlossary":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("term",))
        terms = tuple(GlossaryTerm.from_table(t) for t in root.tables("term"))
        unique(where, "term ids", (t.id for t in terms))
        unique(where, "terms", (t.term.lower() for t in terms))
        return cls(terms)


def load_guide_glossary(configs: Documents) -> GuideGlossary:
    """``config/site/guide/glossary.toml``; missing: no terms."""
    return GuideGlossary.from_document(configs.load("site", FOLDER, NAME))
