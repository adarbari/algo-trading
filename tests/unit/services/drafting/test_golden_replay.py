"""Golden replay: every recorded model answer for every case in ``tests/fixtures/drafting/golden``
is parsed as the draft would parse it, against the site catalogue, and must score a pass.
No network, no model: the answers are recorded text."""

import json

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.services.configs import field_catalog
from algotrade.services.drafting.golden import (
    GoldenCase,
    load_cases,
    recorded_answers,
    score,
)
from algotrade.services.drafting.screens import criteria_of, draft_screen, parse_answer
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.factory import open_config_store
from algotrade_sources.framework.base import FixtureSource
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import api_store

ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"
CASES = load_cases(ROOT)
REPLAYS = [(c, slug, text) for c in CASES for slug, text in recorded_answers(ROOT, c.id).items()]
# a curated case is written unrecorded and skipped here until ``golden run --record``


LEGACY = [r for r in REPLAYS if not r[0].contract]  # a contract case needs the whole draft (below)


def test_every_case_has_a_recorded_answer_and_both_splits() -> None:
    assert {c.id for c, _, _ in REPLAYS} == {c.id for c in CASES if c.recorded}
    assert {c.split for c in CASES} == {"train", "held_out"}


@pytest.mark.parametrize(
    ("case", "slug", "text"),
    LEGACY,
    ids=[f"{c.id}-{slug}" for c, slug, _ in LEGACY],
)
def test_recorded_answer_meets_the_case(case: GoldenCase, slug: str, text: str) -> None:
    catalogue = set(field_catalog(open_config_store(REPO_ROOT / "config")).fields)
    kept, dropped = criteria_of(parse_answer(text), catalogue)
    result = score(case, kept, [d.field for d in dropped])
    assert result.passed, f"{slug}/{case.id}: {result}"


CONTRACT = [(c, slug, text) for c, slug, text in REPLAYS if c.contract]


@pytest.fixture(scope="module")
def ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, UserContext(store.user.user_id))


class Recorded:
    """A ``TextModel`` that gives a recorded answer."""

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, system: str, user: str, **_: object) -> Completion:
        return Completion(self.text, "recorded", "recorded")


def test_the_contract_cases_cover_every_bucket() -> None:
    parts = [p for c, _, _ in CONTRACT for p in c.parts]
    assert {"A", "B", "C", "ask"} <= {p["bucket"] for p in parts}
    assert any(c.split == "held_out" for c, _, _ in CONTRACT)


@pytest.mark.parametrize(
    ("case", "slug", "text"), CONTRACT, ids=[f"{c.id}-{slug}" for c, slug, _ in CONTRACT]
)
def test_a_contract_answer_through_the_whole_draft_meets_the_case(
    ctx: ReadContext, case: GoldenCase, slug: str, text: str
) -> None:
    """The recorded answer through ``draft_screen`` (formulas checked, deduplicated and dry-run,
    missing and unresolved resolved): pending formulas stay out of the document."""
    draft = draft_screen(ctx, Recorded(text), "golden", case.sentence)
    result = score(
        case,
        draft.document["criteria"],
        [d.field for d in draft.dropped],
        [(f.expr, f.criterion) for f in draft.formulas],
        [m.key or f"new:{m.new_key_slug}" for m in draft.missing],
        [u.term for u in draft.unresolved],
    )
    assert result.passed, f"{slug}/{case.id}: {result}"
    assert not any(f.name in json.dumps(draft.document) for f in draft.formulas)


def test_the_suggestions_of_a_contract_answer_are_offered_apart(ctx: ReadContext) -> None:
    """The cases that expect suggestions: the offered ones are beside the document, never in its
    criteria; the refused ones (hard, invented, duplicate) are not offered; notes say what was
    left out."""
    cases = [(c, s, t) for c, s, t in CONTRACT if c.suggested]
    assert {c.id for c, _, _ in cases} >= {
        "yield-trap-suggestions", "vague-word-no-threshold", "hard-suggestion-refused",
    }  # fmt: skip
    for case, _, text in cases:
        draft = draft_screen(ctx, Recorded(text), "golden", case.sentence)
        in_document = {c["field"] for c in draft.document["criteria"].values()}
        assert [s.criterion["field"] for s in draft.suggestions] == case.suggested["offered"]
        assert not in_document & {s.criterion["field"] for s in draft.suggestions}
        assert all(s.criterion["mode"] in ("soft", "score") for s in draft.suggestions)
        assert [d.field for d in draft.suggestions_dropped] == case.suggested["dropped"]
        for word in case.suggested["notes"]:
            assert any(word in n for n in draft.notes)
