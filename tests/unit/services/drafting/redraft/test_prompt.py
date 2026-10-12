"""The scoped prompt of a part's re-draft (ADR 0041, amended 2026-10-12): the same cached prefix as
the whole draft's (so the provider's cache hits), a slice retrieved for the new words only, the
other parts' criteria as compact fixed rows, and under 4,000 tokens that are not the prefix, for
every golden sentence as the new words, with a trader's own features and the open keys padded."""

import hashlib

import pytest

from algotrade.services.drafting.golden.golden import GoldenCase
from algotrade.services.drafting.prompt import (
    PROMPT_VERSION,
    TASK,
    prefix_text,
    sliced_system_prompt,
)
from algotrade.services.drafting.redraft.prompt import (
    ASK,
    MAX_ROWS,
    ROW_CHARS,
    fixed_rows,
    scoped_prompts,
)
from algotrade.services.drafting.redraft.request import MAX_WORDS
from tests.unit.services.drafting.test_retrieval import (
    CASES,
    own_features,
    padded_keys,
    site,  # noqa: F401  (the fixture)
)

UNCACHED_TOKENS = 4_000


def long_rows() -> dict[str, dict[str, object]]:
    """More fixed criteria than are shown, each as long as a row may be."""
    return {
        f"criterion_{n:02d}": {
            "field": f"rollup.some_group@v1.a_rather_long_field_name_{n}", "op": "between",
            "value": [123456789.123, 987654321.987], "mode": "soft",
            "tolerance": {"relative": 0.123456},
        }
        for n in range(MAX_ROWS + 15)
    }  # fmt: skip


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_what_is_not_the_cached_prefix_is_under_4000_tokens(case: GoldenCase, site) -> None:  # noqa: F811
    infos, book, guide = site
    mine = own_features()
    words = case.sentence[:MAX_WORDS]
    system, user = scoped_prompts(
        [*infos, *mine], "my_screen", words, long_rows(), book, guide, padded_keys()
    )
    prefix = prefix_text(infos)
    assert system.startswith(prefix)
    uncached = (len(system) - len(prefix) + len(user)) // 4
    assert uncached < UNCACHED_TOKENS, f"{case.id}: {uncached} tokens"
    assert all(f"{m.name} | " in system for m in mine)  # the trader's own features, in full


def test_the_prefix_is_the_whole_drafts_prefix_byte_for_byte(site) -> None:  # noqa: F811
    infos, book, guide = site
    whole = sliced_system_prompt(infos, CASES[0].sentence, book, guide)
    scoped, _ = scoped_prompts(infos, "s", "price above 5", {}, book, guide, ())
    prefix = prefix_text(infos)
    assert whole.startswith(prefix) and scoped.startswith(prefix)


def test_the_slice_is_for_the_new_words_alone_and_far_smaller_than_the_whole_drafts(
    site,  # noqa: F811
) -> None:
    infos, book, guide = site
    case = max(CASES, key=lambda c: len(sliced_system_prompt(infos, c.sentence, book, guide)))
    prefix = prefix_text(infos)
    whole = sliced_system_prompt(infos, case.sentence, book, guide)
    scoped, _ = scoped_prompts(infos, "s", case.sentence[:MAX_WORDS], {}, book, guide, ())
    assert len(scoped) < len(whole)
    # the capped slice, its situations and the phrasebook leave 1,000 tokens for the user prompt
    assert (len(scoped) - len(prefix)) // 4 < UNCACHED_TOKENS - 1_000
    # a different part's words give a different slice over the same prefix
    other, _ = scoped_prompts(infos, "s", "earnings in the next 10 sessions", {}, book, guide, ())
    assert other.startswith(prefix) and other != scoped


def test_the_other_parts_criteria_are_compact_fixed_rows_the_part_is_not_among() -> None:
    rows = fixed_rows(
        {
            "price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5},
            "iv": {"field": "feature.iv_rank", "op": "gte", "value": 0.5, "mode": "soft",
                   "tolerance": {"relative": 0.2}},
            "active": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
            "has": {"field": "instrument.optionable", "op": "is_null"},
        }
    )  # fmt: skip
    assert rows == [
        "price | rollup.price_stats@v2.close gt 5",
        'iv | feature.iv_rank gte 0.5 soft {"relative":0.2}',
        'active | instrument.status eq "ACTIVE"',
        "has | instrument.optionable is_null",
    ]


def test_the_rows_are_capped_in_number_and_length_and_the_rest_is_counted() -> None:
    rows = fixed_rows(long_rows())
    assert len(rows) == MAX_ROWS + 1 and rows[-1] == "(+15 more, not shown)"
    assert all(len(r) <= ROW_CHARS for r in rows[:-1]) and rows[0].endswith("…")


def test_the_user_prompt_says_what_is_asked(site) -> None:  # noqa: F811
    infos, book, guide = site
    _, user = scoped_prompts(infos, "my_screen", "over $80", {}, book, guide, ())
    assert user.startswith("Screener id: my_screen\n") and user.endswith("Part words: over $80\n")
    assert "RE-DRAFT of ONE part" in user and "Fixed criteria of the other parts" in user
    assert "\nnone\n" in user  # no other criteria
    for rule in ('"p1"', "discarded", "no scaffolding"):
        assert rule.lower() in user.lower()


PINNED = {"9": ("43cf49adfc7573ca", "cb03fbc5eba3b5b0")}  # PROMPT_VERSION -> (TASK, ASK) hashes


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def test_one_prompt_version_serves_both_prompts_so_an_edit_of_either_needs_a_bump() -> None:
    """The usage log records ``PROMPT_VERSION`` for ``screener-draft`` and for
    ``screener-draft-part`` (orchestrator design call 2026-10-12). Editing ``TASK`` or the scoped
    ``ASK`` changes what the model is asked, so the version must move with it: this fails until
    ``PROMPT_VERSION`` is bumped to a number that has its hashes pinned here."""
    assert PROMPT_VERSION in PINNED, f"bump PROMPT_VERSION and pin {_hash(TASK)}, {_hash(ASK)}"
    assert (_hash(TASK), _hash(ASK)) == PINNED[PROMPT_VERSION], (
        f"TASK or ASK changed under PROMPT_VERSION {PROMPT_VERSION}: bump it and pin "
        f"{_hash(TASK)}, {_hash(ASK)}"
    )
