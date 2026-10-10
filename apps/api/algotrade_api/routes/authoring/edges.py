"""``/edges/{id}``: copy an edge, save and delete the user's own, and move their state about one
(follow, reject, retire, a new version's trial, show the out-of-sample result): ADR 0053
amendment 2026-10-09, ADR 0029 writes into ``config/users/<id>/edges/``. Reading an edge is
GraphQL (``Query.edge``); a run is ``POST /edges/{id}/evaluate``; publishing site-wide is an
admin read (``Query.publishedEdgeDocument``), never a write to the site's config.
The write is for the caller; an admin names another user in the ``X-Act-For`` header (ADR 0040)."""

from fastapi import APIRouter

from algotrade.config.edges.document import Edge
from algotrade.config.edges.loading import KIND, SITE
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import edges
from algotrade.services.authoring.edges import StatusChange
from algotrade.services.read.context import open_stores
from algotrade.services.read.evaluation import versions
from algotrade_api.deps import Context, Store, User, Writer
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
def save(writer: Writer, user: User, edge_id: str, body: SaveEdgeBody) -> EdgeDocument:
    """Replace (or create) the user's own edge; validated as the harness reads it, nothing is
    written on an error (400). A site edge's id is 409: copy it."""
    return EdgeDocument(
        edge_id=edge_id, document=edges.save_edge(writer, user, edge_id, body.document)
    )


@router.delete("/{edge_id}", status_code=204)
def delete(writer: Writer, user: User, edge_id: str) -> None:
    """Archive the user's own edge (its state about a site edge: reset); 404 when they have
    none, 409 while another of their edges extends it."""
    edges.delete_edge(writer, user, edge_id)


@router.put("/{edge_id}/state")
def set_state(
    writer: Writer, user: User, ctx: Context, store: Store, edge_id: str, body: StateBody
) -> EdgeState:
    """Move the user's state about an edge (follow, reject, retire, replace) and/or show its
    out-of-sample result. The server decides the permanent labels (a warning, never a block)."""
    own = edge_id not in store.configs.names(SITE, KIND)
    change = _change(body, own)
    # The verdict is the one the acted-for user sees (X-Act-For), not the caller's.
    theirs = open_stores(store.reader, store.configs, UserContext(user), store.cache)
    verdict = versions.verdict_level(theirs, edge_id) if body.state == "following" else None
    edge = edges.set_status(writer, user, edge_id, change, today=ctx.session.date, verdict=verdict)
    return EdgeState(
        edge_id=edge_id,
        state=_state(edge, own),
        since=edge.audit.status_since if own else edge.follow.since,
        reason=edge.audit.status_reason,
        replaces=edge.audit.replaces,
        labels=[*dict.fromkeys([*edge.follow.labels, *edge.audit.labels])],
        oos_revealed=edge.audit.oos_revealed,
    )


# The old state words the browser still sends and reads (until the surfaces speak status, ADR 0053
# amendment 2026-10-10): an own edge's status, or a site edge's bookmark.
_STATUS_OF = {"researching": "researching", "trial": "candidate", "following": "live",
              "rejected": "rejected", "retired": "retired"}  # fmt: skip


def _change(body: StateBody, own: bool) -> StatusChange:
    state = body.state
    if state is not None and state not in _STATUS_OF:
        raise ConfigurationError(f"state {state!r}: expected one of {list(_STATUS_OF)}")
    if own:
        status = None if state is None else _STATUS_OF[state]
        return StatusChange(status, None, body.reason, body.reveal_oos)
    follow = None if state is None else state in ("following", "trial")
    return StatusChange(None, follow, body.reason, body.reveal_oos)


def _state(edge: Edge, own: bool) -> str:
    if not own:
        return "following" if edge.followed else "researching"
    return {v: k for k, v in _STATUS_OF.items()}.get(edge.status, "researching")
