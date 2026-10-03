"""``/configs``: every config the user sees, and one resolved config (layers + hash)."""

from fastapi import APIRouter

from algotrade.services.explore import configs
from algotrade_api.deps import Store
from algotrade_api.schemas.configs import ConfigDetail, ConfigSummary

router = APIRouter(prefix="/configs", tags=["configs"])


@router.get("")
def config_list(store: Store) -> list[ConfigSummary]:
    return [ConfigSummary.model_validate(c) for c in configs.config_list(store)]


@router.get("/{config_id}")
def config_detail(store: Store, config_id: str) -> ConfigDetail:
    return ConfigDetail.model_validate(configs.config_detail(store, config_id))
