"""``load_guide_search``: the ranking table (exact name, then name or title, then intent or
theme, then prose; case-insensitive; deterministic ties), the snippets, the grouping by kind
with a per-kind limit, and the shipped Guide (every kind reachable, the queries the spec
names)."""

import time

import pytest

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.search import (
    SNIPPET,
    TIERS,
    GuideEntryText,
    GuideSearchHit,
    entry_titles,
    guide_entries,
    load_guide_search,
    rank,
)
from tests.unit.services.read.guide.conftest import ADV, DOCUMENTS, stores

FIELD = GuideEntryText(
    "field", ADV, ADV, (ADV,), (), ("liquid", "liquidity"),
    ("Dollars traded a day, averaged over 20 sessions.",), "Dollars traded a day.",
)  # fmt: skip
TERM = GuideEntryText(
    "term", "near_miss", "Near miss", ("near_miss",), ("Near miss",), (),
    ("A value that missed by no more than its tolerance.", "It costs points."), "A value...",
)  # fmt: skip


@pytest.mark.parametrize(
    ("entry", "query", "tier"),
    [
        (FIELD, ADV, "exact"),  # the catalogue name
        (FIELD, ADV.upper(), "exact"),  # case-insensitive
        (TERM, "near miss", "exact"),  # the title
        (TERM, "near_miss", "exact"),  # the id
        (FIELD, "adv_usd", "name"),  # inside the name
        (TERM, "near", "name"),  # inside the title
        (FIELD, "liquid", "intent"),  # an intent (a tag)
        (FIELD, "liquidity", "intent"),  # the theme
        (FIELD, "dollars sessions", "prose"),  # every word, in any order
        (TERM, "tolerance", "prose"),
        (TERM, "points value", "prose"),  # words from two texts
        (FIELD, "ollars", None),  # a word must start a word of the prose
        (FIELD, "dollars weekly", None),  # every word must be there
        (TERM, "zzz", None),
    ],
)
def test_the_ranking_table(entry: GuideEntryText, query: str, tier: str | None) -> None:
    key = rank(entry, " ".join(query.split()).lower())
    assert (TIERS[key[0]] if key is not None else None) == tier


def test_ties_break_by_position_then_title_length_then_title_then_kind_then_id() -> None:
    def entry(kind: str, entry_id: str, title: str) -> GuideEntryText:
        return GuideEntryText(kind, entry_id, title, (entry_id,), (title,), (), (), "")

    found = [
        entry("term", "b", "Gap risk"),
        entry("term", "a", "Gap risk"),
        entry("field", "c", "Gap risk"),
        entry("term", "d", "Gap"),
        entry("term", "e", "The gap"),
    ]
    keys = sorted((rank(e, "gap"), e.id) for e in found)
    # d: the title is "gap" (exact); then the name tier: position 0 first (shorter title
    # first, then the field kind before term, then the id), then position 4.
    assert [entry_id for _, entry_id in keys] == ["d", "c", "a", "b", "e"]


def test_results_group_by_kind_best_group_first_with_a_limit_per_kind() -> None:
    ctx = stores(DOCUMENTS)
    found = load_guide_search(ctx, "  ALPHA ", limit=5)
    assert found.query == "  ALPHA "
    # "alpha": the playbook's id (exact) comes before the field whose prose has no "alpha".
    assert found.groups[0].kind == "playbook"
    assert found.groups[0].hits[0] == GuideSearchHit(
        "playbook", "alpha", "Alpha", "Finds dips; read feature.pullback_atr_20d first."
    )
    liquid = load_guide_search(ctx, "liquid", limit=1)
    (fields,) = [g for g in liquid.groups if g.kind == "field"]
    assert len(fields.hits) == 1  # two fields offer the intent; the limit keeps one
    assert load_guide_search(ctx, "   ", limit=5).groups == ()
    assert load_guide_search(ctx, "alpha", limit=0).groups == ()


def test_a_prose_snippet_is_cut_around_the_first_word() -> None:
    long = "word " * 40 + "takeover " + "tail " * 60
    entry = GuideEntryText("term", "t", "T", ("t",), ("T",), (), (long.strip(),), "lead")
    docs = {**DOCUMENTS, ("site", "guide", "glossary"): {"term": [
        {"id": "t", "term": "T", "short": "lead.", "body": long},
    ]}}  # fmt: skip
    assert rank(entry, "takeover") is not None
    (group,) = [
        g for g in load_guide_search(stores(docs), "takeover", 5).groups if g.kind == "term"
    ]
    snippet = group.hits[0].snippet
    assert snippet.startswith("…word") and snippet.endswith("…") and "takeover" in snippet
    assert len(snippet) <= SNIPPET + 2
    short = load_guide_search(stores(docs), "t", 5).groups
    assert [h.snippet for g in short if g.kind == "term" for h in g.hits] == ["lead."]


def test_the_shipped_guide(site: StoreContext) -> None:
    entries = guide_entries(site)
    kinds = [e.kind for e in entries]
    assert kinds == sorted(kinds, key=["start", "indicator", "episode", "playbook", "field",
                                       "situation", "term"].index)  # fmt: skip
    titles = entry_titles(site)
    assert titles[("term", "not_run")] == "NOT_RUN"
    assert titles[("field", ADV)] == ADV
    exact = load_guide_search(site, "NOT_RUN", 5)
    assert (exact.groups[0].kind, exact.groups[0].hits[0].id) == ("term", "not_run")
    named = load_guide_search(site, ADV, 5)
    assert (named.groups[0].kind, named.groups[0].hits[0].id) == ("field", ADV)
    trend = load_guide_search(site, "trend continuation", 5)
    assert trend.groups[0].hits[0].id == "trend_continuation"
    start = time.perf_counter()
    load_guide_search(site, "earnings", 5)
    assert time.perf_counter() - start < 2.0  # computed per request, no stored index
