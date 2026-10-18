"""What a save changed against the draft the model returned (ADR 0066): the criteria of two
screen documents compared by criterion id (and their boolean groups by group id, ADR 0071), as a
small JSON-ready dict, and the top-level keys of
two edge documents. Edits are derived here on the server, never logged keystroke by keystroke."""

from collections.abc import Mapping
from typing import Any

SHOWN = ("field", "op", "value", "mode", "tolerance")  # what identifies a criterion's meaning


def _brief(criterion: Any) -> dict[str, Any]:
    item = criterion if isinstance(criterion, Mapping) else {}
    return {k: item[k] for k in SHOWN if k in item}


def _criteria(document: Mapping[str, Any]) -> Mapping[str, Any]:
    criteria = document.get("criteria")
    return criteria if isinstance(criteria, Mapping) else {}


def _groups(document: Mapping[str, Any]) -> Mapping[str, Any]:
    groups = document.get("groups")
    return groups if isinstance(groups, Mapping) else {}


def _group(body: Any) -> dict[str, Any]:
    """A group table as ``{"kind": "any", "members": [...]}`` (members in the file's order, and
    ``enabled`` when the table says so: switching a group off is a change)."""
    item = body if isinstance(body, Mapping) else {}
    for kind in ("all", "any", "none"):
        if kind in item:
            out: dict[str, Any] = {"kind": kind, "members": list(item[kind])}
            if "enabled" in item:
                out["enabled"] = item["enabled"]
            return out
    return {}


def groups_diff(returned: Mapping[str, Any], saved: Mapping[str, Any]) -> dict[str, Any]:
    """``{"added": [...], "removed": [...], "changed": [...]}`` of the boolean groups of ``saved``
    against ``returned`` (each item: ``id``, ``kind`` and ``members``; a changed one has ``from``
    and ``to``); empty when the groups are the same."""
    before, after = _groups(returned), _groups(saved)
    added = [{"id": gid, **_group(after[gid])} for gid in after if gid not in before]
    removed = [{"id": gid, **_group(before[gid])} for gid in before if gid not in after]
    changed = [
        {"id": gid, "from": _group(before[gid]), "to": _group(after[gid])}
        for gid in after
        if gid in before and _group(before[gid]) != _group(after[gid])
    ]
    return {k: v for k, v in (("added", added), ("removed", removed), ("changed", changed)) if v}


def criteria_diff(returned: Mapping[str, Any], saved: Mapping[str, Any]) -> dict[str, Any]:
    """``{"added": [...], "removed": [...], "changed": [...], "unchanged": n}`` of the criteria
    of ``saved`` against ``returned`` (each item: ``id`` and its ``field`` / ``op`` / ``value``;
    a changed one has ``from`` and ``to``), plus ``rank`` when the tie-break differs and ``groups``
    (``groups_diff``) when the boolean groups differ."""
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
    if groups := groups_diff(returned, saved):
        diff["groups"] = groups
    return diff


def criteria_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    """The criteria table of ``document`` with its tie-break / rank, as stored in an event: what
    was in force then (the whole of it, not a diff), so a golden case can be read from the rows."""
    snapshot = {"criteria": dict(_criteria(document)), "rank": document.get("rank")}
    if groups := _groups(document):  # absent when there are none, as in the spec
        snapshot["groups"] = {gid: dict(body) for gid, body in groups.items()}
    return snapshot


def document_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> dict[str, Any]:
    """``{"added": {key: value}, "removed": [key], "changed": {key: {"from", "to"}}}`` of the
    top-level keys of an edge document ``after`` against the stored ``before`` (``None``: a first
    save, every key is added). Empty lists / tables when nothing differs."""
    old: Mapping[str, Any] = before or {}
    return {
        "added": {k: after[k] for k in after if k not in old},
        "removed": [k for k in old if k not in after],
        "changed": {
            k: {"from": old[k], "to": after[k]} for k in after if k in old and old[k] != after[k]
        },
    }
