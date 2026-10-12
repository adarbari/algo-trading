"""Golden cases of a part's re-draft (``tests/fixtures/drafting/golden/redraft``): the model's
recorded answer to the whole sentence, the part retyped, the model's recorded answer to the scoped
prompt, and what the merged draft must be: the rows, the parts (words, kind, origin, whether the
reading was kept: never its text), what was dropped and why, what must not have changed. Replayed
through the real ``draft_screen`` and ``redraft_part`` over the golden store; no model, no network.
Checked on every case: each criterion of the merged document belongs to exactly one part, and the
words of every part are the merged sentence's own slice."""

import json
from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.services.drafting.redraft.request import check_request
from algotrade.services.drafting.redraft.run import redraft_part
from algotrade.services.drafting.screens import draft_screen
from algotrade.services.read.context import ReadContext, open_context
from algotrade_sources.framework.base import FixtureSource
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import api_store

FOLDER = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden" / "redraft"
CASES = [json.loads(p.read_text()) for p in sorted(FOLDER.glob("*.json"))]


class Recorded:
    """A ``TextModel`` that gives recorded answers in turn."""

    def __init__(self, *answers: Any) -> None:
        self.answers = [json.dumps(a) for a in answers]

    def complete(self, system: str, user: str, **_: object) -> Completion:
        return Completion(self.answers.pop(0), "recorded", "recorded")


@pytest.fixture(scope="module")
def ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, UserContext(store.user.user_id))


def readings(document: dict[str, Any]) -> list[Any]:
    return [[c["field"], c["op"], c.get("value")] for c in document["criteria"].values()]


def test_there_are_four_cases_that_cover_what_a_re_draft_can_do() -> None:
    assert {c["id"] for c in CASES} == {
        "redraft-hand-added-stays", "redraft-number-changed", "redraft-other-part-wins",
        "redraft-vague-word-made-clear",
    }  # fmt: skip


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_the_recorded_re_draft_merges_into_the_draft_as_the_case_expects(
    ctx: ReadContext, case: dict[str, Any]
) -> None:
    prior = draft_screen(ctx, Recorded(case["prior"]), "golden", case["sentence"])
    assert [u.term for u in prior.unresolved] == case["expect"].get("unresolved_before", [])
    document = json.loads(json.dumps(prior.document))
    document["criteria"].update(case.get("hand_added", {}))  # the trader's own rows
    retype = case["retype"]
    body = asdict(prior) | {"document": document, **retype}
    request = check_request("golden", body)
    done = redraft_part(ctx, Recorded(case["answer"]), request)
    after, expect = done.draft, case["expect"]
    assert done.replaced_part_id == retype["part_id"] and after.sentence == expect["sentence"]
    assert sorted(readings(after.document), key=str) == sorted(expect["criteria"], key=str)
    assert [d.reason for d in after.dropped] == expect["dropped"]
    assert [u.term for u in after.unresolved] == expect.get("unresolved_after", [])
    parts = {p.id: p for p in after.parts or ()}
    for want in expect["parts"]:
        got = parts[want["id"]]
        assert got.kind == want["kind"], (case["id"], want)
        for key in ("words", "origin"):
            if key in want:
                assert getattr(got, key) == want[key], (case["id"], want)
        if "reading" in want:
            assert got.reading_source == want["reading"], (case["id"], want)
    before = {p.id: p for p in prior.parts or ()}
    for pid in expect["unchanged"]:
        keep = ("words", "kind", "criteria", "reading")
        assert [getattr(parts[pid], k) for k in keep] == [getattr(before[pid], k) for k in keep]
    # every criterion belongs to exactly one part; every part's words are the sentence's slice
    named = [cid for p in after.parts or () for cid in p.criteria]
    assert sorted(named) == sorted(after.document["criteria"]) and len(set(named)) == len(named)
    units = after.sentence.encode("utf-16-le")
    for p in after.parts or ():
        assert units[2 * p.start : 2 * p.end].decode("utf-16-le") == p.words


def test_the_other_part_keeps_its_soft_row_when_it_wins(ctx: ReadContext) -> None:
    case = next(c for c in CASES if c["id"] == "redraft-other-part-wins")
    prior = draft_screen(ctx, Recorded(case["prior"]), "golden", case["sentence"])
    body = asdict(prior) | case["retype"]
    done = redraft_part(ctx, Recorded(case["answer"]), check_request("golden", body))
    liquid = done.draft.document["criteria"][case["expect"]["soft_kept"]]
    assert liquid["mode"] == "soft" and liquid["field"].endswith("adv_usd_20d")
    assert liquid == prior.document["criteria"]["liquid"]  # p3's, untouched
