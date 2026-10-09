"""Load the edge documents a user sees (ADR 0053 decision 1, ADR 0015 layering): the site's
``config/site/edges/<id>.toml``, then the user's ``config/users/<user>/edges/<id>.toml`` over
them (a user document with a site id is merged over it, tables deeply, lists replaced, but never
its ``status`` or ``rejection_reason``, which are the site's to decide; a new id is the user's
draft and a ``candidate``). Each layered document is typed by ``document.parse_edge``, then checked
against the store: every screener and baseline must name a screener preset that exists (a site
preset, or the user's own screen), a universe given by name a selection preset that exists, and,
given the caller's field catalogue, an inline universe only catalogue fields.

The ``site`` user reads the site documents only.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from algotrade.config.edges.document import Edge, parse_edge
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
SITE_DECIDES = (
    "status",
    "rejection_reason",
    "evidence",
    "frozen_from",
)  # a user layer never sets these
DRAFT_STATUS = "candidate"


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...

    def names(self, scope: str, kind: str) -> list[str]: ...


def own_edge_ids(configs: Documents, user: str = SITE_USER) -> frozenset[str]:
    """The ids of the edge documents ``user`` has of their own (a draft or a layer over a site
    edge): none for the ``site`` user, whose documents are the site's."""
    return frozenset() if user == SITE_USER else frozenset(configs.names(user, KIND))


def load_edges(
    configs: Documents, user: str = SITE_USER, catalog: FieldCatalog | None = None
) -> tuple[Edge, ...]:
    """Every edge ``user`` sees, by id; none without files. With ``catalog`` (the user's
    ``services.configs.field_catalog``) every inline universe's fields are checked too."""
    scopes = (SITE,) if user == SITE_USER else (SITE, user)
    layered: dict[str, tuple[dict[str, Any], str]] = {}
    for scope in scopes:
        for name in configs.names(scope, KIND):
            doc = configs.load(scope, KIND, name) or {}
            where = f"{_folder(scope)}/{name}.toml"
            if scope != SITE:
                doc = _user_layer(doc, where, site=name in layered)
            base = layered.get(name, ({}, ""))[0]
            layered[name] = (deep_merge(base, doc), where)
    screeners = _screeners(configs, scopes)
    selections = {n for scope in scopes for n in configs.names(scope, SELECTIONS)}
    edges = []
    for name, (doc, where) in sorted(layered.items()):
        edge = parse_edge(doc, name, where)
        _check_presets(edge, where, screeners, selections)
        if catalog is not None and not isinstance(edge.universe, str):
            catalog.check(edge.universe.where, f"{where} universe")
        edges.append(edge)
    return tuple(edges)


def _user_layer(doc: Mapping[str, Any], where: str, site: bool) -> Mapping[str, Any]:
    """A user's document: over a site edge it may not set what the site decides; a draft of its
    own is a candidate (the status it gets when none is given)."""
    if site:
        decided = [k for k in SITE_DECIDES if k in doc]
        if decided:
            raise ConfigurationError(f"{where}: {decided} are the site's to set, not a user's")
        return doc
    if doc.get("status", DRAFT_STATUS) != DRAFT_STATUS:
        raise ConfigurationError(f"{where} status: a user's draft edge is a {DRAFT_STATUS!r}")
    return {**doc, "status": DRAFT_STATUS}


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
