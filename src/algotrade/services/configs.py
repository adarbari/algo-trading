"""Use case: resolve configs from the ``ConfigStore`` and find the screeners that run nightly."""

from collections.abc import Mapping, Sequence
from typing import Any

from algotrade.config.env import user_id
from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.resolve import CONFIG_KINDS, ResolvedConfig, resolve
from algotrade.config.strategy.schema import RULE_IMPLS, Selection
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import FEATURE_FIELD_PREFIX, is_feature_field
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.registry import catalogue_columns
from algotrade.services.features import catalogue
from algotrade.storage.configs.files import SCREENERS
from algotrade.storage.configs.store import ConfigStore, OverlayConfigStore


def default_user(fallback: str) -> UserContext:
    """``$ALGOTRADE_USER`` if set, else ``fallback`` (CLIs: ``local``; site screens: ``site``)."""
    return UserContext(user_id(fallback))


def field_catalog(store: ConfigStore | None = None, user: str | None = None) -> FieldCatalog:
    """Every field a selection may reference: L1 instrument columns, registered rollups, the
    site's expression features (``store``'s, default: the site config directory) and, with a
    ``user``, that user's own (``services.features.catalogue``)."""
    return catalog_of(catalogue(store, user))


def catalog_of(fs: FeatureSet) -> FieldCatalog:
    """``fs``'s per-instrument fields (market-entity features are not selectable per
    instrument: ADR 0047)."""
    expressions = {
        n: e.feature.dtype for n, e in fs.expressions.items() if e.feature.entity == "instrument"
    }
    return FieldCatalog.build(catalogue_columns(), expressions, fs.moved_field)


def resolve_config(
    store: ConfigStore,
    config_id: str,
    user: UserContext,
    overrides: Mapping[str, Any] | None = None,
) -> ResolvedConfig:
    """``config_id`` for ``user``; its selection (and a rule screen's criteria) may name the
    user's own features, which then join the config hash (``ResolvedConfig.features``)."""
    fs = catalogue(store, user.user_id)
    resolved = resolve(config_id, user, store.load, overrides, catalog_of(fs))
    spec_fields = resolved.screen_spec.fields() if resolved.config.rules else ()
    return resolved.with_features(user_features_read(fs, resolved.selection, spec_fields))


def resolve_rule_draft(
    store: ConfigStore,
    name: str,
    user: UserContext,
    document: Mapping[str, Any],
) -> ResolvedConfig:
    """``document`` (a draft, not stored) resolved as ``user``'s rule screen ``name``, exactly
    as it would run: layers, selection, the ``ScreenSpec`` and the catalogue (incl. the user's
    features). A ``ConfigurationError`` naming the path unless it is a valid rule screen.
    Authoring validates drafts with it; the Builder's preview evaluates them with it."""
    overlay = OverlayConfigStore(store, {(user.user_id, SCREENERS, name): document})
    resolved = resolve_config(overlay, name, user)
    if resolved.config.kind != "screener" or resolved.config.impl not in RULE_IMPLS:
        raise ConfigurationError(
            f"{user.user_id}/{name}: not a rule screen (impl = 'rules' or 'model')"
        )
    return resolved


def user_features_read(
    fs: FeatureSet, selection: Selection | None, extra: Sequence[str] = ()
) -> tuple[FeatureDefinition, ...]:
    """The user features ``selection`` (and the ``extra`` fields) name, and the user features
    those read, in dependency order."""
    fields = [r.field for r in selection.where.rules()] if selection else []
    if selection is not None and selection.order_by:
        fields.append(selection.order_by)
    fields.extend(extra)
    todo = [f.removeprefix(FEATURE_FIELD_PREFIX) for f in fields if is_feature_field(f)]
    seen: set[str] = set()
    while todo:
        name = todo.pop()
        e = fs.expressions.get(name)
        if e is None or e.scope != "user" or name in seen:
            continue
        seen.add(name)
        todo += e.uses
    return tuple(e.definition for n, e in fs.expressions.items() if n in seen)


def nightly_screeners(store: ConfigStore) -> list[ResolvedConfig]:
    """The screeners the nightly runs (ADR 0033): every site screener preset (as the ``site``
    user) and every finalised screener of each user. There is no schedule switch: finalising
    a screener is what puts it on the nightly. A draft never finalised is not run."""
    runs: list[ResolvedConfig] = []
    for owner in [SITE_USER, *store.users()]:
        scope = "site" if owner == SITE_USER else owner
        for config_id in config_ids(store, scope):
            resolved = resolve_config(store, config_id, UserContext(owner))
            if resolved.config.kind == "screener":
                runs.append(resolved)
    return runs


def config_ids(store: ConfigStore, scope: str) -> list[str]:
    """Every strategy / screener config id in ``scope`` (``CONFIG_KINDS``; a user's rule
    screens count once finalised), sorted and unique."""
    return sorted({n for kind in CONFIG_KINDS for n in store.names(scope, kind)})
