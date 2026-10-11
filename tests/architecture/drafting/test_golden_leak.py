"""Anti-leak: a held-out golden sentence, or any 5-word run of it, appears neither in the
prompt's worked examples nor in the phrasebook (docs/drafting/describe-it-plan.md)."""

import re

from algotrade.services.drafting.golden import load_cases
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
            assert " ".join(words(case.sentence)) not in flat, f"{case.id} is in {source}"
            shared = grams(case.sentence) & grams(text)
            assert not shared, (
                f"{case.id} shares {GRAM}-word runs with {source}: {sorted(shared)[:3]}"
            )
