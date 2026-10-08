"""``GET /health``: is the API up, which store it reads, how fresh it is, and whether the code it
started with is still the code of its checkout and of the web it serves (``ops/build.py``)."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request

from algotrade.services.read.session import store_info
from algotrade_api import __version__
from algotrade_api.deps import Store, is_admin_request
from algotrade_api.ops.build import build_status
from algotrade_api.schemas.health import Build, Health

router = APIRouter(tags=["health"])


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - always installed in the workspace
        return "unknown"


@router.get("/health")
def health(store: Store, request: Request) -> Health:
    info = store_info(store.reader)
    build = build_status(request.app.state.build, request.app.state.web_dist)
    return Health(
        storage=store.kind,
        latest_session=info.latest_session,
        tables=list(info.tables) if is_admin_request(request) else [],
        versions={
            "algotrade": _version("algotrade"),
            "schema": info.schema_version,
            "api": __version__,
        },
        build=Build.model_validate(build),
    )
