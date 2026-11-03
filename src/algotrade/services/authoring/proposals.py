"""Write a study's proposed edge as a user's configs (ED6 W5, ADR 0053 amendment 2026-11-03): its
rule screens, each finalised into an immutable v1, then the ``researching`` edge that lists them
(``edges.save_proposed_edge``), so the harness (``evaluate-edges``) judges what the study
proposed. The documents come from ``services/evaluation/discovery/drafts.edge_proposal``; this
module only writes them, through the same calls a user's own writes use.

All or nothing: every id is checked free, every screen and the edge (with its screens as if
written) validated before anything is written, so a refused proposal leaves nothing and can be
retried; only a write that fails midway (I/O) leaves screens, which are then deleted (archived,
ADR 0029) so nothing half-proposed stays on the nightly. A finalised screen runs on
the nightly like any user screen (ADR 0033: no schedule switch); its matches never show in Ideas'
Unproven section (``services/read/ideas/setups.in_tab``: a screener behind a proposed edge
only)."""

from collections.abc import Mapping
from datetime import date
from typing import Any

from algotrade.config.edges.document import Edge
from algotrade.services.authoring import screens
from algotrade.services.authoring.edges import check_proposed_edge, save_proposed_edge
from algotrade.services.authoring.scope import ConflictError, author, screen_id
from algotrade.storage.configs.writer import ConfigWriter


def _refuse_taken_screens(writer: ConfigWriter, user: str, names: list[str]) -> None:
    for name in names:
        if writer.draft(user, name) is not None or writer.versions(user, name):
            raise ConflictError(f"{user}/{name}: a screen with this name exists; nothing written")
        screens.refuse_deleted_id(writer, user, name)


def save_proposal(
    writer: ConfigWriter,
    user: str,
    edge_id: str,
    edge: Mapping[str, Any],
    screen_documents: Mapping[str, Mapping[str, Any]],
    *,
    today: date,
) -> Edge:
    """Write ``screen_documents`` (name -> rule screen) and the edge ``edge_id`` that lists them
    as ``user``'s; returns the edge as the harness will read it. ``ConflictError`` or
    ``ConfigurationError`` with nothing left written."""
    who = author(user)
    names = [screen_id(n) for n in screen_documents]
    _refuse_taken_screens(writer, who.user_id, names)
    for name, document in screen_documents.items():
        screens.validate(writer, who, name, screens.draft_document(name, document) | {"version": 1})
    check_proposed_edge(writer, who.user_id, edge_id, edge, today=today, screens=screen_documents)
    written: list[str] = []
    try:
        for name, document in screen_documents.items():
            screens.save_draft(writer, who.user_id, name, document)
            written.append(name)
            screens.finalise(writer, who.user_id, name)
        return save_proposed_edge(writer, who.user_id, edge_id, edge, today=today)
    except Exception:
        for name in written:
            if writer.versions(who.user_id, name):
                screens.delete_screen(writer, who.user_id, name)
            else:
                screens.discard_draft(writer, who.user_id, name)
        raise
