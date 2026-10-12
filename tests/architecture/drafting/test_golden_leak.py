"""Anti-leak: a held-out golden sentence, or any 5-word run of it, appears neither in the
prompt's worked examples nor in the phrasebook (docs/drafting/describe-it-plan.md)."""

import json
import re

from algotrade.services.drafting.golden.golden import load_cases
from algotrade.services.drafting.prompt import examples_text
from tests.conftest import REPO_ROOT

GRAM = 5
ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def grams(text: str) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i : i + GRAM]) for i in range(len(w) - GRAM + 1)}


def test_no_held_out_sentence_is_in_the_examples_or_the_phrasebook() -> None:
    held = [c for c in load_cases(ROOT) if c.split == "held_out"]
    assert held, "the golden set needs held-out cases"
    for source, text in (
        ("examples_text()", examples_text()),
        ("config/site/phrasebook.toml", (REPO_ROOT / "config/site/phrasebook.toml").read_text()),
    ):
        flat = " ".join(words(text))
        for case in held:
            for sentence in case.sentences:  # every description of a curated multi-sentence case
                assert " ".join(words(sentence)) not in flat, f"{case.id} is in {source}"
                shared = grams(sentence) & grams(text)
                assert not shared, (
                    f"{case.id} shares {GRAM}-word runs with {source}: {sorted(shared)[:3]}"
                )


def test_a_curated_case_carries_its_paraphrased_sentences_and_source() -> None:
    for case in load_cases(ROOT):
        raw = json.loads((ROOT / "cases" / f"{case.id}.json").read_text())
        if "source_event" in raw:
            assert raw["sentences"] and raw["sentence"] == raw["sentences"][-1], case.id
            assert len(raw["criteria_in_force"]) == len(raw["sentences"]), case.id
