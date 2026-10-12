"""Anti-leak, structured form: a held-out golden sentence must still need the model. The 5-word
leak test (``test_golden_leak``) cannot see a two-word phrasebook wording ("small caps") that
lets ``resolves_fully`` answer a held-out sentence alone, which would turn the held-out score
into a test of the phrasebook. So no sentence of a held-out case resolves fully; a case the
phrasebook has grown to cover moves to ``train`` and is replaced by an unseen one."""

from algotrade.config.site.settings import load_phrasebook
from algotrade.services.drafting.golden.golden import load_cases
from algotrade.services.drafting.phrasebook.resolve import resolves_fully
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"


def test_no_held_out_sentence_resolves_without_the_model() -> None:
    book = load_phrasebook(open_config_store(REPO_ROOT / "config")).phrases
    held = [c for c in load_cases(ROOT) if c.split == "held_out"]
    assert held, "the golden set needs held-out cases"
    for case in held:
        for sentence in case.sentences or (case.sentence,):
            assert resolves_fully(sentence, book) is None, (
                f"{case.id}: {sentence!r} resolves from the phrasebook; make it a train case "
                "and hold out a different sentence"
            )
