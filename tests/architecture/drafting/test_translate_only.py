"""Describe it only translates the sentence (ADR 0083 decision 4): nothing the drafting model is
sent asks it for a check the sentence did not ask for. The prompts (whole-sentence and one part)
never name ``suggestions``, the answer schema has no such key, and no field guide use-note (prompt
input) tells the model to suggest a criterion."""

import re
import tomllib

from algotrade.services.drafting.contract.answer_schema import ANSWER_SCHEMA
from algotrade.services.drafting.prompt import TASK
from algotrade.services.drafting.redraft.prompt import ASK
from tests.conftest import REPO_ROOT

FIELD_GUIDE = REPO_ROOT / "config" / "site" / "field_guide"
SUGGEST = re.compile(r"\bsuggest", re.IGNORECASE)


def test_the_prompts_and_the_answer_schema_ask_for_no_suggestions() -> None:
    for text in (TASK, ASK):
        assert not SUGGEST.search(text)
    assert "suggestions" not in ANSWER_SCHEMA["properties"]


def test_no_field_guide_use_note_tells_the_model_to_suggest_a_check() -> None:
    offending = [
        f"{path.relative_to(REPO_ROOT)}: {field['name']}: {use['note']}"
        for path in sorted(FIELD_GUIDE.rglob("*.toml"))
        for field in tomllib.loads(path.read_text()).get("field", [])
        for use in field.get("use", [])
        if SUGGEST.search(use.get("note", ""))
    ]
    assert offending == []
