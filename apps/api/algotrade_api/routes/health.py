"""``GET /health``: is the API up, which store it reads and how fresh it is."""

from fastapi import APIRouter

from algotrade.services.explore.store import store_info
from algotrade_api import __version__
from algotrade_api.deps import Store
from algotrade_api.schemas.health import Health

router = APIRouter(tags=["health"])


@router.get("/health")
def health(store: Store) -> Health:
    info = store_info(store)
    health = Health.model_validate(info)
    return health.model_copy(update={"versions": {**info.versions, "api": __version__}})
