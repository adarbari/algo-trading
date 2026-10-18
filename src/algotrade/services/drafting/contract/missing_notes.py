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
    r"(null|no value|missing|no \w+ rank)[^.]*"
    r"\b(not excluded|are kept(?! out)|are included|(?<!never )pass(es)?\b|still pass"
    r"|still appear(?!.*reject))",
    re.IGNORECASE,
)  # one pattern: the server drops such a note, the golden replay test asserts none is served
NOTE_CHARS = 300
NOTES = {  # what the engine does with a member whose field has no value (rules.md, Modes)
    "hard": "Names with no {} are also left out (missing data never passes).",
    "soft": "Names with no {} stay in but are marked down (missing data never passes).",
    "score": "Names with no {} score lower (missing data never passes).",
}


def without_false_claims(notes: Sequence[str]) -> tuple[str, ...]:
    """``notes`` less those that claim names with no value pass, are kept or are not excluded."""
    return tuple(n for n in notes if not CLAIMS_MISSING_PASSES.search(n))


def exclusion_notes(
    document: Mapping[str, Any], labels: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    """One note per field of a criterion that sits directly in a ``none`` group of ``document``,
    worded for the member's mode (``hard`` leaves the name out, ``soft`` keeps it marked down,
    ``score`` ranks it lower). A member that is itself a group is skipped on purpose: a ``none``
    over an ``all`` passes on one known negated member, so no single field decides it. No
    exclusion, no note. ``labels`` (field -> words) names a field; else its catalogue words, else
    the last segment of its name."""
    criteria = document.get("criteria") or {}
    seen: set[tuple[str, str]] = set()
    notes: list[str] = []
    for body in (document.get("groups") or {}).values():
        for cid in body.get("none", ()):
            member = criteria.get(cid) or {}
            field, mode = member.get("field"), member.get("mode") or "hard"
            if not isinstance(field, str) or (field, mode) in seen or mode not in NOTES:
                continue
            seen.add((field, mode))
            label = (labels or {}).get(field) or _label(field)
            notes.append(NOTES[mode].format(label)[:NOTE_CHARS])
    return tuple(notes)


def field_labels(infos: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, str]:
    """Field -> its words for the criteria of ``document``: the first clause of the catalogue
    description (``pct_vs_sma_50``: "close vs its 50-day SMA"), lower-cased unless it starts with
    an acronym; a field with no description is left to the name's last segment."""
    labels: dict[str, str] = {}
    for member in (document.get("criteria") or {}).values():
        name = member.get("field")
        text = getattr(infos.get(name), "description", "") if isinstance(name, str) else ""
        clause = re.split(r"[.;:,(]", text.strip(), maxsplit=1)[0].strip()
        if clause:
            labels[name] = clause if clause[:2].isupper() else clause[0].lower() + clause[1:]
    return labels


def _label(field: str) -> str:
    return field.rsplit(".", 1)[-1].replace("_", " ")
