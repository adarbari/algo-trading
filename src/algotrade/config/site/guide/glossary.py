"""The Guide's glossary (``config/site/guide/glossary/<theme>.toml``, ADR 0051; spec
``docs/ui/guide.md`` section 3, "Glossary"): the app's own words and the rule grammar, one
``[[term]]`` each: ``id`` (its page's key), ``term`` (as the app writes it: ``NOT_RUN``,
``on_miss``, ``Near miss``), ``short`` (one sentence: the help button's hover and the drawer's
first line), ``body`` (a short paragraph; catalogue names in it are linked) and ``see_also``
(other term ids, in reading order).

The loader reads every theme file in file-name order and checks shape only: known keys,
snake_case ids, non-empty text, no id or term twice across the files (terms compared without
case), no ``see_also`` naming the term itself or another twice, no
secrets. That every
``see_also`` id is a term, every catalogue name in the prose exists, ``short`` is one sentence
and every term the spec lists is written are fitness tests over the shipped file."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.config.site.guide.start import entry_id
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide_glossary"  # the config store's kind: site/guide/glossary/<theme>.toml
TERM_KEYS = ("id", "term", "short", "body", "see_also")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


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
    def from_documents(cls, docs: Mapping[str, Mapping[str, Any] | None]) -> "GuideGlossary":
        """``docs``: each theme file's document by its name, in file-name order."""
        terms: list[GlossaryTerm] = []
        for name, doc in docs.items():
            where = f"guide/glossary/{name}.toml"
            reject_secrets(doc or {}, where)
            root = Table(doc, where)
            root.only(("term",))
            terms.extend(GlossaryTerm.from_table(t) for t in root.tables("term"))
        where = "guide/glossary"
        unique(where, "term ids", (t.id for t in terms))
        unique(where, "terms", (t.term.lower() for t in terms))
        return cls(tuple(terms))


def load_guide_glossary(configs: Documents) -> GuideGlossary:
    """``config/site/guide/glossary/*.toml`` in file-name order; none: no terms."""
    names = configs.names("site", FOLDER)
    return GuideGlossary.from_documents({n: configs.load("site", FOLDER, n) for n in names})
