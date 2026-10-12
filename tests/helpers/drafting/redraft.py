"""Shared builders of the re-draft tests: the draft the browser holds (the whole-sentence draft
of ``test_draft_parts``), its request body as the API passes it, and the model's answer to the
scoped prompt."""

from dataclasses import asdict
from typing import Any

from algotrade.services.drafting.screens import ScreenDraft, draft_screen
from algotrade.services.read.context import ReadContext
from tests.unit.services.drafting.parts.test_draft_parts import SENTENCE, tagged
from tests.unit.services.drafting.test_screens import OI, PRICE, Canned, proposal

__all__ = ["OI", "PRICE", "SENTENCE", "Canned", "answer_for", "body_of", "held_draft"]


def held_draft(ctx: ReadContext) -> ScreenDraft:
    """What the browser holds after the first description: five parts."""
    return draft_screen(ctx, Canned(tagged()), "my_screen", SENTENCE)


def body_of(draft: ScreenDraft, part_id: str, new_words: str, **over: Any) -> dict[str, Any]:
    """The request body of re-drafting ``part_id``: the draft as served, plus what to retype."""
    body = asdict(draft) | {"part_id": part_id, "new_words": new_words}
    return body | over


def answer_for(words: str, *criteria: dict[str, Any], reading: str | None = None, **extra: Any):
    """The scoped model's answer: one part ``p1`` holding the new words, its criteria tagged."""
    tagged_criteria = [{**c, "part": "p1"} for c in criteria]
    return proposal(
        *tagged_criteria,
        parts=[{"id": "p1", "words": words, "reading": reading}],
        **extra,
    )
