"""The Guide's "Researched, not built" ideas (``config/site/guide/ideas/<family>.toml``, ADR 0051;
spec ``docs/ui/guide.md``): every idea of the edge-idea catalogue (``docs/edge-ideas/``, nine
family pages) that is not a site edge, one ``[[idea]]`` each, one file per family. The file's
name is the family's (``FAMILIES``) and its ``family`` key the letter. Keys of an idea: ``id``
(the catalogue heading's id), ``title`` (plain words), ``mechanism_kind`` (one of
``config/edges/document.py`` ``MECHANISM_KINDS``: why it should work, which groups it under a Guide
mechanism page; a site setting may not import that module, so a test checks membership) and
EITHER ``filed_as`` (the site edge it became, under another name: a variant or a screener of
it) OR the three of ``verdict`` (``IDEA_VERDICTS``: the catalogue's published grade, never the
harness's), ``feasibility`` (``IDEA_FEASIBILITY``: what the catalogue says building it needs)
and ``why_not_built`` (one plain sentence, qualitative).

The loader checks shape only: known keys, snake_case ids unique across the files, the file
named for its family, the verdict and feasibility sets, exactly one of ``filed_as`` or the
three, no secrets. That ``mechanism_kind`` is one of ``MECHANISM_KINDS``, that the headings of
the nine pages and the ids agree, that a ``filed_as`` names a site edge and an unfiled id is
not one, and that the sentence is one sentence are fitness tests over the shipped files
(``tests/unit/config/site/guide/test_ideas.py``)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets, unique
from algotrade.config.site.guide.start import entry_id
from algotrade.core.model.errors import ConfigurationError

FOLDER = "guide_ideas"  # the config store's kind: site/guide/ideas/<family>.toml
# the family letter -> its file's name (the catalogue page's name, underscored)
FAMILIES = {
    "A": "cross_sectional", "B": "events", "C": "options_volatility", "D": "calendar_flows",
    "E": "trend_macro", "F": "altdata_text_ml", "G": "statarb_technical",
    "H": "structural_niches", "I": "frontier",
}  # fmt: skip
IDEA_VERDICTS = ("strong", "promising", "weak", "decayed", "dead", "not_graded")  # not_graded: none
IDEA_FEASIBILITY = ("data_ready", "needs_data", "needs_code", "out_of_scope")
UNFILED_KEYS = ("verdict", "feasibility", "why_not_built")
KEYS = ("id", "title", "mechanism_kind", "filed_as", *UNFILED_KEYS)


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


@dataclass(frozen=True)
class Idea:
    """One catalogue idea (module docstring): filed (``filed_as``) or not (the three)."""

    id: str
    family: str
    title: str
    mechanism_kind: str
    filed_as: str | None = None
    verdict: str | None = None
    feasibility: str | None = None
    why_not_built: str | None = None

    @classmethod
    def from_table(cls, t: Table, family: str) -> "Idea":
        t.only(KEYS)
        idea_id = entry_id(t)
        kind = entry_id_text(t, "mechanism_kind")
        title = t.line("title")
        if t.raw("filed_as") is not None:
            extra = [k for k in UNFILED_KEYS if t.raw(k) is not None]
            if extra:
                raise ConfigurationError(
                    f"{t.where} filed_as: an idea filed as an edge has no {extra}"
                )
            return cls(idea_id, family, title, kind, filed_as=entry_id_text(t, "filed_as"))
        missing = [k for k in UNFILED_KEYS if t.raw(k) is None]
        if missing:
            raise ConfigurationError(
                f"{t.where}: expected filed_as, or {list(UNFILED_KEYS)}; no {missing}"
            )
        return cls(
            idea_id, family, title, kind,
            verdict=t.choice("verdict", "", IDEA_VERDICTS),
            feasibility=t.choice("feasibility", "", IDEA_FEASIBILITY),
            why_not_built=t.line("why_not_built"),
        )  # fmt: skip


def entry_id_text(t: Table, key: str) -> str:
    """``key``'s value as a snake_case id (an edge id, a variant id)."""
    return entry_id(Table({"id": t.raw(key)}, f"{t.where} {key}"))


@dataclass(frozen=True)
class GuideIdeas:
    """Every idea, in family then file order (none without files)."""

    ideas: tuple[Idea, ...] = ()

    def get(self, idea_id: str) -> Idea | None:
        return next((i for i in self.ideas if i.id == idea_id), None)

    @property
    def unfiled(self) -> tuple[Idea, ...]:
        """The ideas not filed as an edge: the "Researched, not built" list."""
        return tuple(i for i in self.ideas if i.filed_as is None)

    @classmethod
    def from_documents(cls, docs: Mapping[str, Mapping[str, Any] | None]) -> "GuideIdeas":
        """``docs``: each family file's document by its name."""
        ideas: list[Idea] = []
        for name in sorted(docs, key=_order):
            where = f"guide/ideas/{name}.toml"
            doc = docs[name] or {}
            reject_secrets(doc, where)
            root = Table(doc, where)
            root.only(("family", "idea"))
            family = root.line("family")
            if FAMILIES.get(family) != name:
                raise ConfigurationError(
                    f"{where} family: {family!r} is not the family of this file "
                    f"(expected the file of {FAMILIES.get(family)!r})"
                )
            ideas.extend(Idea.from_table(t, family) for t in root.tables("idea"))
        unique("guide/ideas", "idea ids", (i.id for i in ideas))
        return cls(tuple(ideas))


def _order(name: str) -> tuple[int, str]:
    names = list(FAMILIES.values())
    return (names.index(name) if name in names else len(names), name)


def load_guide_ideas(configs: Documents) -> GuideIdeas:
    """``config/site/guide/ideas/*.toml`` in family order; none: no ideas."""
    return GuideIdeas.from_documents(
        {n: configs.load("site", FOLDER, n) for n in configs.names("site", FOLDER)}
    )
