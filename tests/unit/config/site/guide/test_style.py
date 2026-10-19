"""The writing style of the Guide's prose (``docs/ui/guide-quality.md`` section 3(b), the
checklist of 3(a); mechanics ``.claude/skills/add-guide-content``), over the shipped glossary,
Start here pages, mechanism pages and field guide: a ``short`` or ``summary`` is at most 25
words; every sentence of a body, a ``reads`` or a caveat at most 30; no marketing words,
hedging filler, exclamation marks or trading advice; a glossary term used in another entry is in its
``see_also`` (a Start page: its ``links``); every state or status term has a ``next``; a Start
page has at most 7 sections.

Sentences over 30 words that shipped before the check are a shrink-only baseline,
``architecture/guide_style_baseline.toml`` (counts per text): a new one fails (rewrite it,
never add it), and a count that falls fails until the baseline is lowered."""

import re
import tomllib
from collections import Counter
from collections.abc import Iterator
from typing import NamedTuple

from algotrade.config.site.guide.glossary import GlossaryTerm, load_guide_glossary
from algotrade.config.site.guide.mechanisms import load_guide_mechanisms
from algotrade.config.site.guide.start import load_guide_start
from algotrade.config.site.settings import load_field_guide
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
BASELINE = REPO_ROOT / "architecture" / "guide_style_baseline.toml"
COVERAGE = REPO_ROOT / "architecture" / "guide_coverage.toml"
SHORT_WORDS = 25  # the hover and the drawer's first line (checklist bullet 2)
SENTENCE_WORDS = 30  # checklist bullet 9
START_SECTIONS = 7  # checklist bullet 11
# A sentence ends at ., ! or ? followed by a space and a capital, digit, quote or bracket
# (not "e.g. a", "$5.50" or a catalogue name).
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
# Checklist bullet 8: marketing and filler words (whole words, any case), leverage as a verb
# (the noun and "a leveraged fund" are fine), exclamation marks, and advice to trade.
BANNED = re.compile(
    r"\b(simply|just|easy|easily|powerful|robust)\b"
    r"|\bleverag(es|ing)\b|\bleverage (the|a|an|your|our|this|these|it|its|their)\b"
    r"|!(?!=)"
    r"|\bshould (buy|sell|short|trade)\b|\b(buy|sell) (now|this name|these names)\b"
    r"|(^|[.?]\s+)(Buy|Sell)\b",
    re.IGNORECASE,
)


class Prose(NamedTuple):
    """One text: ``key`` (``<kind>:<id>:<part>``, the baseline's key), ``part`` and ``text``."""

    key: str
    part: str
    text: str


def _prose() -> Iterator[Prose]:
    for t in load_guide_glossary(SHIPPED).terms:
        yield Prose(f"term:{t.id}:short", "short", t.short)
        yield Prose(f"term:{t.id}:body", "body", t.body)
        if t.next:
            yield Prose(f"term:{t.id}:next", "next", t.next)
    for page in load_guide_start(SHIPPED).pages:
        yield Prose(f"start:{page.id}:summary", "summary", page.summary)
        for section in page.sections:
            yield Prose(f"start:{page.id}:{section.title}", "body", section.body)
    for m in load_guide_mechanisms(SHIPPED).mechanisms:
        yield Prose(f"mechanism:{m.id}:short", "short", m.short)
        for part in ("how_it_works", "why_it_survives", "research", "real_vs_decoy"):
            for paragraph in getattr(m, part):
                yield Prose(f"mechanism:{m.id}:{part}", "body", paragraph)
        yield Prose(f"mechanism:{m.id}:dont", "body", m.dont)
    guide = load_field_guide(SHIPPED)
    for field in guide.fields:
        yield Prose(f"field:{field.name}:reads", "reads", field.reads)
        for caveat in field.caveats:
            yield Prose(f"field:{field.name}:caveats", "caveat", caveat)
    for situation in guide.situations:
        yield Prose(f"situation:{situation.slug}:signs", "signs", situation.signs)
        yield Prose(f"situation:{situation.slug}:do", "do", situation.do)


PROSE = tuple(_prose())


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_BREAK.split(text.strip()) if s]


def long_sentences() -> Counter[str]:
    """Sentences over ``SENTENCE_WORDS`` per key, in every part but the one-line ones."""
    found: Counter[str] = Counter()
    for p in PROSE:
        if p.part not in ("short", "summary"):
            found[p.key] += sum(len(s.split()) > SENTENCE_WORDS for s in sentences(p.text))
    return +found


def test_a_short_or_summary_is_at_most_25_words() -> None:
    for p in PROSE:
        if p.part in ("short", "summary"):
            words = len(p.text.split())
            assert words <= SHORT_WORDS, f"{p.key}: {words} words, at most {SHORT_WORDS}"


def test_sentences_are_at_most_30_words_or_in_the_shrink_only_baseline() -> None:
    baseline = Counter(tomllib.loads(BASELINE.read_text())["long_sentences"])
    found = long_sentences()
    grown = {k: n for k, n in found.items() if n > baseline[k]}
    assert not grown, (
        f"sentences over {SENTENCE_WORDS} words (split them; never add to {BASELINE.name}): {grown}"
    )
    shrunk = {k: found[k] for k, n in baseline.items() if found[k] < n}
    assert not shrunk, f"fewer long sentences now: lower these in {BASELINE.name}: {shrunk}"


def test_no_marketing_filler_exclamation_or_advice() -> None:
    hits = [f"{p.key}: {m.group().strip()!r}" for p in PROSE for m in BANNED.finditer(p.text)]
    assert not hits, f"banned words (checklist bullet 8; say what it is instead): {hits}"


def _term_pattern(term: GlossaryTerm) -> re.Pattern[str] | None:
    """How ``term`` is spotted in prose, ``None`` for a plain single word ("Run", "hard"),
    which reads as ordinary English: a code (``NOT_RUN``, ``on_miss``) as written, a phrase
    ("Near miss", "Win rate") in any case; a trailing "(...)" is not part of it."""
    words = re.sub(r"\s*\(.*\)$", "", term.term)
    code = "_" in words or words.isupper()
    if not code and len(words.split()) < 2:
        return None
    flags = 0 if code else re.IGNORECASE
    return re.compile(rf"(?<![\w.@]){re.escape(words)}(?![\w@])", flags)


def test_a_term_used_in_another_entry_is_linked_from_it() -> None:
    glossary = load_guide_glossary(SHIPPED)
    patterns = [(t.id, p) for t in glossary.terms if (p := _term_pattern(t)) is not None]
    orphans = [
        f"term:{t.id} -> {other}"
        for t in glossary.terms
        for other, pattern in patterns
        if other != t.id and other not in t.see_also and pattern.search(f"{t.short} {t.body}")
    ]
    for page in load_guide_start(SHIPPED).pages:
        linked = {link.id for link in page.links if link.kind == "term"}
        body = " ".join(s.body for s in page.sections)
        orphans += [
            f"start:{page.id} -> {other}"
            for other, pattern in patterns
            if other not in linked and pattern.search(body)
        ]
    assert not orphans, f"add the term to see_also (a Start page: its links): {orphans}"


def state_terms() -> set[str]:
    """Every term a status or state value maps to in ``architecture/guide_coverage.toml``."""
    coverage = tomllib.loads(COVERAGE.read_text())
    return {
        ref.removeprefix("term:")
        for enum in coverage.get("enum", [])
        for ref in enum.get("values", {}).values()
        if ref.startswith("term:")
    }


def test_every_state_term_says_what_happens_next() -> None:
    glossary = load_guide_glossary(SHIPPED)
    states = state_terms()
    assert states, f"{COVERAGE.name} maps no value to a term"
    missing = sorted(t.id for t in glossary.terms if t.id in states and not t.next)
    assert not missing, (
        f"glossary: give these state terms a `next` (what the app does next or what the "
        f"reader can do; checklist bullet 4): {missing}"
    )
    assert all(len(sentences(t.next)) == 1 for t in glossary.terms if t.next), (
        "glossary: `next` is one sentence"
    )


def test_a_start_page_has_at_most_7_sections() -> None:
    for page in load_guide_start(SHIPPED).pages:
        assert len(page.sections) <= START_SECTIONS, (
            f"start:{page.id}: {len(page.sections)} sections, at most {START_SECTIONS}; split it"
        )


def test_the_checks_catch_what_they_name() -> None:
    assert len(sentences("One two. Three, e.g. four. Five is $5.50 at feature.x. Six.")) == 4
    for bad in ("simply put", "a Robust check", "Great!", "you should buy", "It. Buy it."):
        assert BANNED.search(bad), bad
    fine_texts = (
        "a leveraged fund",
        "its leverage (2x)",
        "buyers and sellers",
        "the day to buy it",
    )
    for fine in (*fine_texts, "a != b"):
        assert not BANNED.search(fine), fine
    near = _term_pattern(GlossaryTerm("near_miss", "Near miss", "s", "b"))
    assert near is not None and near.search("a near miss") and not near.search("nearmiss")
    assert _term_pattern(GlossaryTerm("run", "Run", "s", "b")) is None
