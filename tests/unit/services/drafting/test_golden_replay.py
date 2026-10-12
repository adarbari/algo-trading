"""Golden replay: every recorded model answer for every case in ``tests/fixtures/drafting/golden``
is parsed as the draft would parse it, against the site catalogue, and must score a pass.
No network, no model: the answers are recorded text."""

import pytest

from algotrade.services.configs import field_catalog
from algotrade.services.drafting.golden import (
    GoldenCase,
    load_cases,
    recorded_answers,
    score,
)
from algotrade.services.drafting.screens import criteria_of, parse_answer
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"
CASES = load_cases(ROOT)
REPLAYS = [(c, slug, text) for c in CASES for slug, text in recorded_answers(ROOT, c.id).items()]
# a curated case is written unrecorded and skipped here until ``golden run --record``


def test_every_case_has_a_recorded_answer_and_both_splits() -> None:
    assert {c.id for c, _, _ in REPLAYS} == {c.id for c in CASES if c.recorded}
    assert {c.split for c in CASES} == {"train", "held_out"}


@pytest.mark.parametrize(("case", "slug", "text"), REPLAYS, ids=lambda v: getattr(v, "id", v))
def test_recorded_answer_meets_the_case(case: GoldenCase, slug: str, text: str) -> None:
    catalogue = set(field_catalog(open_config_store(REPO_ROOT / "config")).fields)
    kept, dropped = criteria_of(parse_answer(text), catalogue)
    result = score(case, kept, [d.field for d in dropped])
    assert result.passed, f"{slug}/{case.id}: {result}"
