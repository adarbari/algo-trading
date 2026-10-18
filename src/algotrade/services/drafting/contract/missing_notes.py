"""The notes about missing data of a draft (ADR 0015, 0041, 0071): missing data never passes a
selection, and that includes an exclusion, where a name with no value for the excluded field is
left out. The model sometimes writes the reverse in its notes (a recorded answer said names with no
IV rank "are not excluded"), so a model note that claims missing names pass is dropped here, and
the server adds the true note once per field of a ``none`` group. Pure: reads notes and the
document, calls nothing."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

CLAIMS_MISSING_PASSES = re.compile(
    r"(null|no value|missing|no \w+ rank)[^.]*\b(not excluded|are kept|still (pass|appear))",
    re.IGNORECASE,
)  # one pattern: the server drops such a note, the golden replay test asserts none is served
NOTE_CHARS = 300


def without_false_claims(notes: Sequence[str]) -> tuple[str, ...]:
    """``notes`` less those that claim names with no value pass, are kept or are not excluded."""
    return tuple(n for n in notes if not CLAIMS_MISSING_PASSES.search(n))


def exclusion_notes(document: Mapping[str, Any]) -> tuple[str, ...]:
    """One note per field of a criterion that sits in a ``none`` group of ``document``: names with
    no value for it are left out. No exclusion, no note."""
    criteria = document.get("criteria") or {}
    seen: list[str] = []
    for body in (document.get("groups") or {}).values():
        for cid in body.get("none", ()):
            field = (criteria.get(cid) or {}).get("field")
            if isinstance(field, str) and field not in seen:
                seen.append(field)
    return tuple(
        f"Names with no {_label(f)} are also left out (missing data never passes)."[:NOTE_CHARS]
        for f in seen
    )


def _label(field: str) -> str:
    return field.rsplit(".", 1)[-1].replace("_", " ")
