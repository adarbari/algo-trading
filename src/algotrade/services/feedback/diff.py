"""What a save changed against the draft the model returned (ADR 0066): the criteria of two
screen documents compared by criterion id, as a small JSON-ready dict. Edits are derived here
on the server, never logged keystroke by keystroke."""

from collections.abc import Mapping
from typing import Any

SHOWN = ("field", "op", "value", "mode", "tolerance")  # what identifies a criterion's meaning


def _brief(criterion: Any) -> dict[str, Any]:
    item = criterion if isinstance(criterion, Mapping) else {}
    return {k: item[k] for k in SHOWN if k in item}


def _criteria(document: Mapping[str, Any]) -> Mapping[str, Any]:
    criteria = document.get("criteria")
    return criteria if isinstance(criteria, Mapping) else {}


def criteria_diff(returned: Mapping[str, Any], saved: Mapping[str, Any]) -> dict[str, Any]:
    """``{"added": [...], "removed": [...], "changed": [...], "unchanged": n}`` of the criteria
    of ``saved`` against ``returned`` (each item: ``id`` and its ``field`` / ``op`` / ``value``;
    a changed one has ``from`` and ``to``), plus ``rank`` when the tie-break differs."""
    before, after = _criteria(returned), _criteria(saved)
    added = [{"id": cid, **_brief(after[cid])} for cid in after if cid not in before]
    removed = [{"id": cid, **_brief(before[cid])} for cid in before if cid not in after]
    changed = [
        {"id": cid, "field": _brief(after[cid]).get("field"),
         "from": _brief(before[cid]), "to": _brief(after[cid])}
        for cid in after
        if cid in before and _brief(before[cid]) != _brief(after[cid])
    ]  # fmt: skip
    diff: dict[str, Any] = {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(after) - len(added) - len(changed),
    }
    if returned.get("rank") != saved.get("rank"):
        diff["rank"] = {"from": returned.get("rank"), "to": saved.get("rank")}
    return diff
