"""``/features``: the catalogue and one feature's distribution on a session."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from algotrade.services.explore import features
from algotrade_api.deps import Store
from algotrade_api.schemas.features import Distribution, Feature

router = APIRouter(prefix="/features", tags=["features"])


@router.get("")
def catalogue(store: Store) -> list[Feature]:
    """The caller's catalogue: the site's fields plus their own expression features
    (``scope = "user"``; the user is ``ALGOTRADE_USER``)."""
    return [Feature.model_validate(f) for f in features.feature_catalogue(store)]


@router.get("/{name}/distribution")
def distribution(
    store: Store, name: str, on: Annotated[date | None, Query(alias="date")] = None
) -> Distribution:
    return Distribution.model_validate(features.feature_distribution(store, name, on))
