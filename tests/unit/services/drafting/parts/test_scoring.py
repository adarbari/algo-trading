"""Scoring explained parts structurally: words, origin and kind (never the reading's text), the
share the model placed itself, and the aggregate the live golden run reports."""

import json

from algotrade.config.site.llm import ProviderSettings
from algotrade.config.site.settings import load_llm
from algotrade.services.drafting.golden.golden import recorded_answers
from algotrade.services.drafting.parts.model import MAX_READING, MAX_WORDS, Part, PartsStats
from algotrade.services.drafting.parts.scoring import aggregate, score_parts, share_ok
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT


def part(words: str, kind: str = "applied", origin: str = "words", source: str = "model") -> Part:
    return Part("p1", words, 0, len(words), None, source, kind, origin)


EXPECTED = {
    "parts": [{"words": "over $5", "kind": "applied", "origin": "words", "reading": "model"}]
}


def test_a_part_with_the_expected_words_kind_and_reading_source_passes() -> None:
    assert score_parts(EXPECTED, [part("over $5")]).passed


def test_a_missing_wrong_or_extra_not_understood_part_fails() -> None:
    assert score_parts(EXPECTED, []).missing == ("over $5",)
    assert score_parts(EXPECTED, None).missing == ("over $5",)
    assert score_parts(EXPECTED, [part("over $5", "formula")]).wrong == ("over $5",)
    assert score_parts(EXPECTED, [part("over $5", source="server")]).wrong == ("over $5",)
    extra = score_parts(EXPECTED, [part("over $5"), part("zzz", "not_understood", "unplaced")])
    assert extra.extra == ("zzz",) and not extra.passed
    kept = {"parts": [{"words": "", "kind": "applied", "origin": "kept"}]}
    assert score_parts(kept, [part("", origin="kept")]).passed


def test_the_models_share_of_items_and_the_aggregate() -> None:
    stats = PartsStats(
        items=4, by_model=3, by_fallback=1, spans=3, located=3, readings=2, readings_kept=1
    )
    assert share_ok({"model_share": 0.75}, stats) and not share_ok({"model_share": 1.0}, stats)
    assert share_ok({}, None) and not share_ok({"model_share": 0.5}, None)
    total = aggregate(
        [stats, PartsStats(items=4, by_model=1, spans=1, located=0, not_understood=1), None]
    )
    assert total == {
        "with_parts": 2, "model_share": 0.5, "located_share": 0.75, "not_understood": 1,
        "readings_kept": 0.5,
    }  # fmt: skip
    assert aggregate([None])["model_share"] is None


def test_twelve_maximal_parts_on_the_largest_golden_answer_fit_the_answer_limit() -> None:
    """Output grows by a line per part: the largest recorded answer plus 12 parts at their caps
    (200 characters of words, 160 of reading), at chars / 3 tokens, with the ~2,000 tokens a
    thinking model spends first (``config/site/llm.toml``), stays under 75% of the shipped
    ``answer_limit``. (``chat.py``'s 2,000 is only a dataclass default: the registry passes the
    configured limit.)"""
    root = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"
    store = open_config_store(REPO_ROOT / "config")
    largest = max(
        (len(text) for path in (root / "cases").glob("*.json")
         for text in recorded_answers(root, path.stem).values()),
        default=0,
    )  # fmt: skip
    part = json.dumps({"id": "p12", "words": "w" * MAX_WORDS, "reading": "r" * MAX_READING})
    tags = 12 * len(', "part": "p12"') * 6  # a tag on a dozen items of each kind, generously
    worst = (largest + 12 * (len(part) + 2) + tags) // 3
    configured = [x.answer_limit for x in load_llm(store).providers]
    limit = min([ProviderSettings.answer_limit, *configured])  # the class default, 8000
    assert worst + 2000 <= 0.75 * limit, (worst, limit)
