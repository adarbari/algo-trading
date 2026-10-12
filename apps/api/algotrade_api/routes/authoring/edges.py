"""``/edges/{id}``: copy an edge, save and delete the user's own, and move their status about one
(follow a site edge, move the status of their own, show the out-of-sample result): ADR 0053
amendments 2026-10-09 and 2026-10-10, ADR 0029 writes into ``config/users/<id>/edges/``.
Reading an edge is GraphQL (``Query.edge``); a run is ``POST /edges/{id}/evaluate``;
publishing site-wide is an admin read (``Query.publishedEdgeDocument``), never a write to the
site's config.
The write is for the caller; an admin names another user in the ``X-Act-For`` header (ADR 0040)."""

from fastapi import APIRouter

from algotrade.config.edges.loading import USER_STATUSES
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import edges
from algotrade.services.authoring.edges import StatusChange
from algotrade.services.read.context import open_stores
from algotrade.services.read.evaluation import versions
from algotrade_api import feedback
from algotrade_api.deps import Context, Feedback, Store, User, Writer
from algotrade_api.schemas.authoring.edges import (
    CopyEdgeBody,
    EdgeDocument,
    EdgeState,
    SaveEdgeBody,
    StateBody,
)

router = APIRouter(prefix="/edges", tags=["edges"])


@router.post("/{edge_id}/copy", status_code=201)
def copy(
    writer: Writer, user: User, ctx: Context, edge_id: str, body: CopyEdgeBody
) -> EdgeDocument:
    """A new edge of the user's that extends ``edge_id``; 404 when they see no such edge, 409
    when the new id is taken or was deleted."""
    document = edges.copy_edge(
        writer, user, edge_id, body.new_id, today=ctx.session.date, as_version=body.as_version
    )
    return EdgeDocument(edge_id=body.new_id, document=document)


@router.put("/{edge_id}")
def save(
    writer: Writer, user: User, sink: Feedback, edge_id: str, body: SaveEdgeBody
) -> EdgeDocument:
    """Replace (or create) the user's own edge; validated as the harness reads it, nothing is
    written on an error (400). A site edge's id is 409: copy it. A revision is recorded as an
    ``edge_revised`` feedback event after the write (ADR 0066), never failing the save."""
    previous, stored = edges.save_edge_revision(writer, user, edge_id, body.document)
    feedback.record_edge_revised(sink, body.draft_session_id, user, edge_id, previous, stored)
    return EdgeDocument(edge_id=edge_id, document=stored)


@router.delete("/{edge_id}", status_code=204)
def delete(writer: Writer, user: User, edge_id: str) -> None:
    """Archive the user's own edge (its state about a site edge: reset); 404 when they have
    none, 409 while another of their edges extends it."""
    edges.delete_edge(writer, user, edge_id)


@router.put("/{edge_id}/state")
def state(
    writer: Writer, user: User, ctx: Context, store: Store, edge_id: str, body: StateBody
) -> EdgeState:
    """Bookmark a site edge (``follow``) or move the status of the user's own (``status``), and/or
    show an own edge's out-of-sample result. The server decides the permanent labels (a warning,
    never a block); 400 for a ``status`` of a site edge, a ``follow`` of an own edge or both."""
    if body.follow is not None and body.status is not None:
        raise ConfigurationError("send follow (a site edge) or status (your own edge), not both")
    if body.status is not None and body.status not in USER_STATUSES:
        raise ConfigurationError(f"status {body.status!r}: expected one of {list(USER_STATUSES)}")
    change = StatusChange(body.status, body.follow, body.reason, body.reveal_oos)
    # The verdict is the one the acted-for user sees (X-Act-For), not the caller's.
    theirs = open_stores(store.reader, store.configs, UserContext(user), store.cache)
    judged = body.follow is True or body.status == "live"
    verdict = versions.verdict_level(theirs, edge_id) if judged else None
    edge = edges.set_status(writer, user, edge_id, change, today=ctx.session.date, verdict=verdict)
    return EdgeState(
        edge_id=edge_id,
        status=edge.status,
        followed=edge.followed,
        followed_since=edge.follow.since,
        status_since=edge.audit.status_since,
        reason=edge.audit.status_reason,
        replaces=edge.audit.replaces,
        labels=[*dict.fromkeys([*edge.follow.labels, *edge.audit.labels])],
        oos_revealed=edge.audit.oos_revealed,
    )
