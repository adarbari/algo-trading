"""Load the edge documents a user sees (ADR 0053 decision 1, ADR 0015 layering): the site's
``config/site/edges/<id>/edge.toml``, then the user's own ``config/users/<user>/edges/<id>.toml``.
A user document never shadows a site edge (ADR 0053 amendment 2026-10-09):

- with ``extends = "<edge id>"`` it is a COPY: a new edge under its own id, the extended
  document (a site edge, or the user's own: v2 extends v1) deep-merged under it (tables
  deeply, lists replaced). What the site decides (``status``, ``rejection_reason``,
  ``evidence``, ``implementation``) is never inherited nor set. The edge's ``status`` is the
  user's own (ADR 0053 amendment 2026-10-10: ``USER_STATUSES``, a copy starts as ``researching``;
  ``evidenced`` and ``blocked`` stay the site's) and so is its ``[audit]``, the server's
  bookkeeping of it; a rejected or retired edge's reason is the audit's ``status_reason``;
- without it, an id that is no site edge's is a new edge of the user's, a ``researching`` too;
- the file of a site edge's own id holds nothing but ``[follow]``: the user's bookmark of a
  site edge they have not copied (changing its settings needs a copy).
A user's own document still holding the old ``[follow]`` state is read as its status and audit
(``follow.legacy_own``) until ``scripts/migrate_edge_follows.py`` has rewritten it.

Each layered document is typed by ``document.parse_edge``, then checked against the store: every
screener and baseline must name a screener preset that exists (a site preset, or the user's own
screen), a universe given by name a selection preset that exists, and, given the caller's field
catalogue, an inline universe only catalogue fields. A baseline ``"@standard"`` is expanded to
``verdict.toml [decoys] standard`` first (so a decoy that does not exist fails here, as any
baseline). ``Edge.site_frozen_from`` is the ``frozen_from`` of the root of the copy chain, so a
copy whose split differs is exploratory.

The ``site`` user reads the site documents only. ``Edge.owner`` is where the document lives:
``site`` for a site document (a user's follow-only file over it included), the user for a copy or
a new edge; ``load_all_edges`` is every site edge and every user's own, for the evaluation CLI.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Protocol

from algotrade.config.edges.document import Edge, expand_baselines, parse_edge
from algotrade.config.edges.follow import AUDIT, is_legacy, legacy_own, parse_audit, parse_follow
from algotrade.config.edges.follow import KEY as FOLLOW
from algotrade.config.edges.positions.spec import check_edge as check_positions
from algotrade.config.edges.positions.spec import check_rules
from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.config.site.settings import site_document
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.resolve import deep_merge
from algotrade.config.user import SITE_USER
from algotrade.core.model.errors import ConfigurationError

KIND = "edges"
SITE = "site"
# Where screener configs live (ADR 0029): rule screens in their own kind, Python screeners as
# strategy configs with kind = "screener".
RULE_SCREENS = "screeners"
CONFIGS = "strategies"
SELECTIONS = "selections"
SITE_DECIDES = ("rejection_reason", "evidence", "implementation")  # a user's edge never has these
DRAFT_STATUS = "researching"
USER_STATUSES = ("researching", "candidate", "live", "retired", "rejected")  # a user sets these
# The statuses an edge takes new paper picks in, for its OWNER's record (ADR 0053 amendment
# 2026-10-10: a user cannot set ``evidenced``, so their own edge records from ``live``).
RECORDING = ("evidenced", "live")
# A site setup records from ``candidate`` (ADR 0064 amendment 2026-10-24: the forward record is the
# product's evidence and a day not recorded cannot be recovered; "recording" is a notion of its
# own, never a verdict: ``evidenced`` still means the verdict cleared its bar).
SITE_RECORDING = ("candidate", *RECORDING)


def records_paper(status: str, site: bool) -> bool:
    """Whether an edge with ``status`` takes new paper picks for its record owner's record: a SITE
    edge (``site``) from ``candidate`` to ``live``, a user's own edge from ``live`` only (a user
    cannot set ``evidenced``; a draft or candidate of theirs is no one's evidence). A
    ``researching``, ``retired``, ``rejected`` or ``blocked`` edge takes none (its open trades
    still settle)."""
    return status in (SITE_RECORDING if site else RECORDING)


MAX_CHAIN = 8  # a copy of a copy of ...: deeper is a mistake (and a cycle is refused earlier)


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


class UserDocuments(Documents, Protocol):
    """``Documents`` that can also list the users with files (``ConfigStore``)."""

    def users(self) -> list[str]: ...


def load_edges(
    configs: Documents, user: str = SITE_USER, catalog: FieldCatalog | None = None
) -> tuple[Edge, ...]:
    """Every edge ``user`` sees, by id; none without files. With ``catalog`` (the user's
    ``services.configs.field_catalog``) every inline universe's fields are checked too.

    A fault in the USER's own files never costs them every edge (the site can change under a
    user's file: it publishes an edge of the same id, or drops one a copy extends): that edge is
    left out, or for a site id kept as the site's with only its ``[follow]`` read, and
    ``edge_problems`` says why. A fault in a site document still raises."""
    return _load(configs, user, catalog)[0]


def load_all_edges(configs: UserDocuments) -> tuple[Edge, ...]:
    """The site's edges, then each user's own (copies and new edges; a site edge once), by
    owner: what ``evaluate-edges`` runs, each under its owner. Users come from the store's
    ``users()``; a user whose file is faulty contributes what loads."""
    found = list(load_edges(configs))
    for user in configs.users():
        if user != SITE_USER:
            found.extend(e for e in load_edges(configs, user) if e.owner == user)
    return tuple(found)


def edge_problems(
    configs: Documents, user: str = SITE_USER, catalog: FieldCatalog | None = None
) -> dict[str, str]:
    """The reasons the user's own edge files do not (fully) load, by edge id: what ``load_edges``
    left out or ignored so a page can say so instead of the edge silently vanishing."""
    return _load(configs, user, catalog)[1]


def _load(
    configs: Documents, user: str, catalog: FieldCatalog | None
) -> tuple[tuple[Edge, ...], dict[str, str]]:
    scopes = (SITE,) if user == SITE_USER else (SITE, user)
    layered, problems = _layered(configs, user)
    screeners = _screeners(configs, scopes)
    selections = {n for scope in scopes for n in configs.names(scope, SELECTIONS)}
    verdict = VerdictSettings.from_document(site_document(configs.load, "verdict"))
    standard = verdict.decoys_standard
    templates = load_templates(configs)
    parsed: dict[str, Edge] = {}
    for name, (doc, where, _root) in sorted(layered.items()):
        try:
            edge = parse_edge(doc, name, where)
            edge = replace(
                edge, baselines=expand_baselines(edge.baselines, standard, edge.screeners)
            )
            _check_presets(edge, where, screeners, selections)
            if catalog is not None:
                check_rules(edge, where, catalog, templates)
            check_positions(edge, where, templates)
            if catalog is not None and not isinstance(edge.universe, str):
                catalog.check(edge.universe.where, f"{where} universe")
        except ConfigurationError as exc:
            if not where.startswith(f"config/users/{user}/"):
                raise
            problems[name] = str(exc)
            continue
        parsed[name] = edge
    edges = []
    for name, parsed_edge in parsed.items():
        root = layered[name][2]
        parent = parsed.get(root) if root is not None else None
        owner = SITE if layered[name][1].startswith(f"{_folder(SITE)}/") else user
        edge = replace(parsed_edge, owner=owner)
        edges.append(edge if parent is None else replace(edge, site_frozen_from=parent.frozen_from))
    return tuple(edges), problems


def layered_documents(configs: Documents, user: str = SITE_USER) -> dict[str, dict[str, Any]]:
    """Every edge ``user`` sees as one layered document (before it is typed), by id: a copy with
    its ``extends`` resolved, a site edge with the user's ``[follow]``. What an admin publishes
    (``services/read/evaluation/versions.py``)."""
    return {name: dict(doc) for name, (doc, _, _) in _layered(configs, user)[0].items()}


def _layered(
    configs: Documents, user: str
) -> tuple[dict[str, tuple[dict[str, Any], str, str | None]], dict[str, str]]:
    """((document, the file it is named by, the id of its chain's root) by edge id, the problems
    of the user's own files by edge id): a file that cannot be layered is a problem, not an
    error."""
    site = _documents(configs, SITE)
    own = {} if user == SITE_USER else _documents(configs, user)
    layered: dict[str, tuple[dict[str, Any], str, str | None]] = {
        n: (dict(d), _site_file(n), None) for n, d in site.items()
    }
    problems: dict[str, str] = {}
    for name, doc in own.items():
        try:
            layered[name] = _own_document(name, doc, site, own, user, problems)
        except ConfigurationError as exc:
            problems[name] = str(exc)
    return layered, problems


def _documents(configs: Documents, scope: str) -> dict[str, Mapping[str, Any]]:
    return {n: configs.load(scope, KIND, n) or {} for n in configs.names(scope, KIND)}


def _own_document(
    name: str,
    doc: Mapping[str, Any],
    site: Mapping[str, Mapping[str, Any]],
    own: Mapping[str, Mapping[str, Any]],
    user: str,
    problems: dict[str, str],
) -> tuple[dict[str, Any], str, str | None]:
    """(layered document, the file it is named by, the id of its chain's root) for the user's
    file ``name``: a copy over what it extends, a follow-only file over a site edge, or a new
    edge."""
    where = f"{_folder(user)}/{name}.toml"
    extends = doc.get("extends")
    if name in site:
        # The site has an edge of this id (it may have been published from this user's copy):
        # the file is the user's state about it, nothing else; the rest is ignored, with a reason.
        stray = sorted(set(doc) - {FOLLOW})
        if stray:
            problems[name] = (
                f"{where}: the site now has an edge {name!r}, so this file holds only [follow]; "
                f"ignored {stray} (change its settings in a copy under a new id)"
            )
        parse_follow(doc, where)
        return {**site[name], FOLLOW: doc.get(FOLLOW, {})}, _site_file(name), None
    doc = _modernised(doc, where)
    chain: list[tuple[str, Mapping[str, Any]]] = [(name, doc)]  # outermost first
    base: Mapping[str, Any] = {}
    root = name
    while extends is not None:
        target = str(extends)
        if target in {n for n, _ in chain} or len(chain) > MAX_CHAIN:
            raise ConfigurationError(
                f"{where} extends: {target!r} makes a cycle or a chain over {MAX_CHAIN} copies deep"
            )
        root = target
        if target in site:
            base, extends = site[target], None
        elif target in own:
            chain.append((target, _modernised(own[target], f"{_folder(user)}/{target}.toml")))
            extends = own[target].get("extends")
        else:
            known = sorted({*site, *own} - {name})
            raise ConfigurationError(f"{where} extends: no edge {target!r} (known: {known})")
    merged = _strip(base)
    for layer_name, layer in reversed(chain):
        merged = _copy_over(merged, layer, f"{_folder(user)}/{layer_name}.toml")
    # A copy is its own edge (the extended document's id is not its); a new one names itself.
    merged = {**merged, "id": name} if len(chain) > 1 or base else {"id": name, **merged}
    merged["status"] = doc.get("status", DRAFT_STATUS)
    if doc.get("extends") is not None:
        merged["extends"] = doc["extends"]
    if doc.get(AUDIT) is not None:
        merged[AUDIT] = doc[AUDIT]
        reason = parse_audit(doc, where).status_reason
        if merged["status"] in ("rejected", "retired") and reason:
            merged["rejection_reason"] = reason  # the reason the document type asks for
    if merged["status"] == "rejected" and "rejection_reason" not in merged:
        merged["rejection_reason"] = "rejected by the user"
    return merged, where, root


def _modernised(doc: Mapping[str, Any], where: str) -> Mapping[str, Any]:
    """``doc`` with an old ``[follow]`` state turned into its ``status`` and ``[audit]``."""
    if doc.get(FOLLOW) is None:
        return doc
    if not is_legacy(doc[FOLLOW]):
        raise ConfigurationError(
            f"{where} [follow]: an own edge has a status (a bookmark is of a site edge)"
        )
    status, audit = legacy_own(doc[FOLLOW], where)
    rest = {k: v for k, v in doc.items() if k != FOLLOW}
    # the old state is the truth: it wins over a stray ``status`` or ``[audit]``
    return {**rest, "status": status, AUDIT: audit}


def _strip(document: Mapping[str, Any]) -> dict[str, Any]:
    """The part of an extended document a copy inherits: not the site's decisions, not
    ``[follow]`` or ``[audit]`` (the user's own state) and not its ``extends`` (the copy has its
    own)."""
    out = {k: v for k, v in document.items() if k not in (*SITE_DECIDES, "status", FOLLOW, AUDIT)}
    out.pop("extends", None)
    return out


def _copy_over(base: Mapping[str, Any], layer: Mapping[str, Any], where: str) -> dict[str, Any]:
    decided = [k for k in SITE_DECIDES if k in layer]
    if decided:
        raise ConfigurationError(f"{where}: {decided} are the site's to set, not a user's")
    if layer.get("status", DRAFT_STATUS) not in USER_STATUSES:
        raise ConfigurationError(
            f"{where} status: a user's edge is one of {list(USER_STATUSES)} "
            "(evidenced and blocked are the site's)"
        )
    skipped = ("extends", "status", FOLLOW, AUDIT)
    return deep_merge(base, {k: v for k, v in layer.items() if k not in skipped})


def _site_file(name: str) -> str:
    return f"{_folder(SITE)}/{name}/edge.toml"


def _folder(scope: str) -> str:
    return f"config/site/{KIND}" if scope == SITE else f"config/users/{scope}/{KIND}"


def _screeners(configs: Documents, scopes: tuple[str, ...]) -> set[str]:
    """The screener presets in ``scopes``: rule screens, and strategy configs of kind screener."""
    found = {n for scope in scopes for n in configs.names(scope, RULE_SCREENS)}
    for scope in scopes:
        for name in configs.names(scope, CONFIGS):
            if (configs.load(scope, CONFIGS, name) or {}).get("kind") == "screener":
                found.add(name)
    return found


def _check_presets(edge: Edge, where: str, screeners: set[str], selections: set[str]) -> None:
    for key, ids in (("screeners", edge.screeners), ("baselines", edge.baselines)):
        unknown = [s for s in ids if s not in screeners]
        if unknown:
            raise ConfigurationError(
                f"{where} {key}: no screener preset named {unknown} (known: {sorted(screeners)})"
            )
    if isinstance(edge.universe, str) and edge.universe not in selections:
        raise ConfigurationError(
            f"{where} universe: no selection preset named {edge.universe!r} "
            f"(known: {sorted(selections)})"
        )
