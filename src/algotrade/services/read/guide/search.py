"""``GuideSearch`` (ADR 0051; spec ``docs/ui/guide.md`` "Search"; ADR 0038: the server searches,
never the browser): one search over every Guide entry, the results grouped by kind
(``ENTRY_KINDS``), each ``{kind, id, title, snippet}``. Computed from the loaded sources on
each request; no index is stored.

What is searched, per kind (``guide_entries``, the one list of the Guide's entries):

- a field (every catalogue field of the caller): its name; its theme and intents (the field
  guide's); its prose (how to read it, the caveats, the catalogue description);
- a playbook: its id and name; its prose (summary, hit, not checked, before acting, asks);
- a situation: its slug and name; its signs and what to do;
- a regime indicator: its key and field, its plain and technical names; the card's prose;
- an episode: its key and name; its cause and notes;
- a glossary term: its id and term; its short line and body;
- a Start here page: its id and title; its summary and sections.

Ranking (``rank``), case-insensitive, the query's whitespace collapsed; the first tier that
matches counts:

0. exact: the query is an entry's name (an id, a catalogue name) or its title;
1. name or title: one of them contains the query;
2. intent or theme: one of a field's intents or its theme contains the query;
3. prose: every word of the query starts a word of the entry's prose.

Ties: the earlier match in the text matched, then the shorter title, then the title A-Z, then
the id. Each kind keeps its best ``limit`` hits; the groups come by their best hit, then in
``ENTRY_KINDS`` order. A snippet is the prose around the first query word for a prose match,
else the entry's lead (a term's short line, a field's first sentence, a page's summary), cut
at a word to ``SNIPPET`` characters."""

import re
from dataclasses import dataclass

from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.playbooks import load_guide_playbooks
from algotrade.config.site.guide.start import ENTRY_KINDS, load_guide_start
from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.config.site.settings import load_field_guide
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import site_playbooks
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos

SNIPPET = 160  # characters of a snippet, at most (an ellipsis marks a cut)
CONTEXT = 50  # characters of prose kept before the matched word
TIERS = ("exact", "name", "intent", "prose")


@dataclass(frozen=True)
class GuideEntryText:
    """One Guide entry as search reads it (module docstring): ``names`` (ids, catalogue
    names), ``titles`` (what the reader calls it), ``tags`` (a field's intents and theme),
    ``prose`` (its texts) and ``lead`` (the snippet when the prose did not match)."""

    kind: str
    id: str
    title: str
    names: tuple[str, ...]
    titles: tuple[str, ...]
    tags: tuple[str, ...]
    prose: tuple[str, ...]
    lead: str


@dataclass(frozen=True)
class GuideSearchHit:
    """One result: the entry (``kind``, ``id``: a field's catalogue name, a situation's slug,
    an indicator's or episode's key), its ``title`` and the ``snippet``."""

    kind: str
    id: str
    title: str
    snippet: str


@dataclass(frozen=True)
class GuideSearchGroup:
    kind: str
    hits: tuple[GuideSearchHit, ...]


@dataclass(frozen=True)
class GuideSearch:
    """The results for ``query`` (as given) by kind; no groups for a blank query or no
    match."""

    query: str
    groups: tuple[GuideSearchGroup, ...]


Key = tuple[int, int, int, str, int, str]


def load_guide_search(ctx: Stores, query: str, limit: int) -> GuideSearch:
    """``query`` over every Guide entry (module docstring); at most ``limit`` hits per kind."""
    q = " ".join(query.split()).lower()
    if not q or limit < 1:
        return GuideSearch(query, ())
    found = [(key, entry) for entry in guide_entries(ctx) if (key := rank(entry, q)) is not None]
    by_kind: dict[str, list[tuple[Key, GuideSearchHit]]] = {}
    for key, entry in sorted(found, key=lambda pair: pair[0]):
        hits = by_kind.setdefault(entry.kind, [])
        if len(hits) < limit:
            hits.append((key, _hit(entry, q, key[0])))
    order = sorted(by_kind, key=lambda kind: (by_kind[kind][0][0][0], ENTRY_KINDS.index(kind)))
    return GuideSearch(
        query, tuple(GuideSearchGroup(k, tuple(h for _, h in by_kind[k])) for k in order)
    )


def rank(entry: GuideEntryText, q: str) -> Key | None:
    """``entry``'s sort key for the lowered, collapsed query ``q``, its first item the tier
    that matched (an index of ``TIERS``); ``None``: no match."""
    tier, position = _match(entry, q)
    if tier is None:
        return None
    kind = ENTRY_KINDS.index(entry.kind)
    return tier, position, len(entry.title), entry.title.lower(), kind, entry.id


def _match(entry: GuideEntryText, q: str) -> tuple[int | None, int]:
    named = (*entry.names, *entry.titles)
    if any(text.lower() == q for text in named):
        return 0, 0
    for tier, texts in ((1, named), (2, entry.tags)):
        found = [i for text in texts if (i := text.lower().find(q)) >= 0]
        if found:
            return tier, min(found)
    prose = " ".join(entry.prose)
    starts = [_word_at(prose, word) for word in q.split()]
    if all(i >= 0 for i in starts):
        return 3, starts[0]
    return None, 0


def _word_at(text: str, word: str) -> int:
    """Where a word of ``text`` starting with ``word`` is (case-insensitive); -1: none."""
    found = re.search(rf"(?<![\w]){re.escape(word)}", text, re.IGNORECASE)
    return found.start() if found is not None else -1


def _hit(entry: GuideEntryText, q: str, tier: int) -> GuideSearchHit:
    snippet = _around(entry.prose, q.split(maxsplit=1)[0]) if tier == 3 else None
    return GuideSearchHit(entry.kind, entry.id, entry.title, snippet or _cut(entry.lead, 0))


def _around(texts: tuple[str, ...], word: str) -> str | None:
    """The first text holding ``word``, from a word boundary ``CONTEXT`` characters before it."""
    for text in texts:
        at = _word_at(text, word)
        if at >= 0:
            return _cut(text, at - CONTEXT)
    return None


def _cut(text: str, start: int) -> str:
    """``text`` from ``start`` (moved to the next word; 0: the start), at most ``SNIPPET``
    characters ending at a word, with an ellipsis at each cut."""
    head = ""
    if start > 0:
        space = text.find(" ", start)
        start = space + 1 if space >= 0 else start
        head = "…"
    else:
        start = 0
    rest = text[start:]
    if len(rest) <= SNIPPET:
        return head + rest
    cut = rest.rfind(" ", 0, SNIPPET)
    return head + rest[: cut if cut > 0 else SNIPPET].rstrip(" ,;:") + "…"


def guide_entries(ctx: Stores) -> tuple[GuideEntryText, ...]:
    """Every Guide entry the caller can open, in ``ENTRY_KINDS`` order, each kind in its
    source's order (module docstring)."""
    guide = load_field_guide(ctx.configs)
    prose = load_guide_playbooks(ctx.configs)
    pages = tuple(
        GuideEntryText(
            "start", p.id, p.title, (p.id,), (p.title,), (),
            (p.summary, *(f"{s.title}. {s.body}" for s in p.sections)), p.summary,
        )
        for p in load_guide_start(ctx.configs).pages
    )  # fmt: skip
    indicators = tuple(
        GuideEntryText(
            "indicator", c.key, c.plain_name, (c.key, c.feature),
            (c.plain_name, c.technical_name), (),
            (c.one_liner, c.why_it_matters, c.what_on_means, c.lead_time, c.false_alarms),
            c.one_liner,
        )
        for c in load_cards(ctx.configs).cards
    )  # fmt: skip
    episodes = tuple(
        GuideEntryText("episode", e.key, e.name, (e.key,), (e.name,), (), (e.cause, e.notes),
                       e.cause)
        for e in load_episodes(ctx.configs).episodes
    )  # fmt: skip
    playbooks = []
    for p in site_playbooks(ctx):
        written = prose.get(p.id)
        texts = (
            (written.summary, written.hit, written.not_checked, *written.before_acting,
             *(a for _, a in written.asks))
            if written is not None
            else ()
        )  # fmt: skip
        lead = written.summary if written is not None else ""
        playbooks.append(
            GuideEntryText("playbook", p.id, p.name, (p.id,), (p.name,), (), texts, lead)
        )
    fields = tuple(_field(info) for info in feature_infos(ctx.features, guide=guide).values())
    situations = tuple(
        GuideEntryText("situation", s.slug, s.name, (s.slug,), (s.name,), (), (s.signs, s.do),
                       s.signs)
        for s in guide.situations
    )  # fmt: skip
    terms = tuple(
        GuideEntryText("term", t.id, t.term, (t.id,), (t.term,), (), (t.short, t.body), t.short)
        for t in load_guide_glossary(ctx.configs).terms
    )
    return (*pages, *indicators, *episodes, *playbooks, *fields, *situations, *terms)


def _field(info: FeatureInfo) -> GuideEntryText:
    entry = info.guide
    if entry is None:
        return GuideEntryText(
            "field", info.name, info.name, (info.name,), (), (), (info.description,),
            info.description,
        )  # fmt: skip
    intents = tuple(dict.fromkeys(u.intent for u in entry.uses))
    return GuideEntryText(
        "field", info.name, info.name, (info.name,), (), (*intents, entry.theme),
        (entry.reads, *entry.caveats, info.description), entry.summary,
    )  # fmt: skip


def entry_titles(ctx: Stores) -> dict[tuple[str, str], str]:
    """Every entry's title by ``(kind, id)`` (a reference's label)."""
    return {(e.kind, e.id): e.title for e in guide_entries(ctx)}
