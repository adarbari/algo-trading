"""Load the edge documents a user sees (ADR 0053 decision 1, ADR 0015 layering): the site's
``config/site/edges/<id>.toml``, then the user's own ``config/users/<user>/edges/<id>.toml``.
A user document never shadows a site edge (ADR 0053 amendment 2026-10-09):

- with ``extends = "<edge id>"`` it is a COPY: a new edge under its own id, the extended
  document (a site edge, or the user's own: v2 extends v1) deep-merged under it (tables
  deeply, lists replaced). What the site decides (``status``, ``rejection_reason``,
  ``evidence``, ``implementation``) is never inherited nor set: a copy is a ``candidate``;
- without it, an id that is no site edge's is a new edge of the user's, a ``candidate`` too;
- the file of a site edge's own id holds nothing but ``[follow]``: the user's state about a
  site edge they have not copied (changing its settings needs a copy).

Each layered document is typed by ``document.parse_edge``, then checked against the store: every
screener and baseline must name a screener preset that exists (a site preset, or the user's own
screen), a universe given by name a selection preset that exists, and, given the caller's field
catalogue, an inline universe only catalogue fields. ``Edge.site_frozen_from`` is the
``frozen_from`` of the root of the copy chain, so a copy whose split differs is exploratory.

The ``site`` user reads the site documents only.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Protocol

from algotrade.config.edges.document import Edge, parse_edge
from algotrade.config.edges.follow import KEY as FOLLOW
from algotrade.config.edges.follow import parse_follow
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
DRAFT_STATUS = "candidate"
MAX_CHAIN = 8  # a copy of a copy of ...: deeper is a mistake (and a cycle is refused earlier)


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


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
    parsed: dict[str, Edge] = {}
    for name, (doc, where, _root) in sorted(layered.items()):
        try:
            edge = parse_edge(doc, name, where)
            _check_presets(edge, where, screeners, selections)
            if catalog is not None and not isinstance(edge.universe, str):
                catalog.check(edge.universe.where, f"{where} universe")
        except ConfigurationError as exc:
            if not where.startswith(f"config/users/{user}/"):
                raise
            problems[name] = str(exc)
            continue
        parsed[name] = edge
    edges = []
    for name, edge in parsed.items():
        root = layered[name][2]
        parent = parsed.get(root) if root is not None else None
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
        n: (dict(d), f"{_folder(SITE)}/{n}.toml", None) for n, d in site.items()
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
        return {**site[name], FOLLOW: doc.get(FOLLOW, {})}, f"{_folder(SITE)}/{name}.toml", None
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
            chain.append((target, own[target]))
            extends = own[target].get("extends")
        else:
            known = sorted({*site, *own} - {name})
            raise ConfigurationError(f"{where} extends: no edge {target!r} (known: {known})")
    merged = _strip(base)
    for layer_name, layer in reversed(chain):
        merged = _copy_over(merged, layer, f"{_folder(user)}/{layer_name}.toml")
    # A copy is its own edge (the extended document's id is not its); a new one names itself.
    merged = {**merged, "id": name} if len(chain) > 1 or base else {"id": name, **merged}
    merged["status"] = DRAFT_STATUS
    if doc.get("extends") is not None:
        merged["extends"] = doc["extends"]
    if doc.get(FOLLOW) is not None:
        merged[FOLLOW] = doc[FOLLOW]
    return merged, where, root


def _strip(document: Mapping[str, Any]) -> dict[str, Any]:
    """The part of an extended document a copy inherits: not the site's decisions, not
    ``[follow]`` (the user's own state) and not its ``extends`` (the copy has its own)."""
    out = {k: v for k, v in document.items() if k not in (*SITE_DECIDES, "status", FOLLOW)}
    out.pop("extends", None)
    return out


def _copy_over(base: Mapping[str, Any], layer: Mapping[str, Any], where: str) -> dict[str, Any]:
    decided = [k for k in SITE_DECIDES if k in layer]
    if decided:
        raise ConfigurationError(f"{where}: {decided} are the site's to set, not a user's")
    if layer.get("status", DRAFT_STATUS) != DRAFT_STATUS:
        raise ConfigurationError(f"{where} status: a user's edge is a {DRAFT_STATUS!r}")
    return deep_merge(base, {k: v for k, v in layer.items() if k not in ("extends", FOLLOW)})


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
