"""``GET /health``: is the API up, which store it reads and how fresh it is."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

from algotrade.services.read.session import store_info
from algotrade_api import __version__
from algotrade_api.deps import Store
from algotrade_api.schemas.health import Health

router = APIRouter(tags=["health"])


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - always installed in the workspace
        return "unknown"


@router.get("/health")
def health(store: Store) -> Health:
    info = store_info(store.reader)
    return Health(
        storage=store.kind,
        latest_session=info.latest_session,
        tables=list(info.tables),
        versions={
            "algotrade": _version("algotrade"),
            "schema": info.schema_version,
            "api": __version__,
        },
    )
