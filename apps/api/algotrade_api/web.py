"""Serve the built web app on the API's own origin (ADR 0044): ``GET /{path}`` answers a file
under the build directory (``ALGOTRADE_WEB_DIST``), else the app's ``index.html`` (the SPA
fallback: the browser router owns deep links such as ``/login``).

``create_app`` mounts it last and only when the directory is set, so every API route
(``/health``, ``/graphql``, ``/docs``, the REST writes and polls) keeps precedence; a path an
API route serves under another method (``GET /screeners/preview``) answers 405, never the
page. ``HEAD`` is answered as ``GET`` without a body (uptime probes). It is
public: the bundle is the same for every visitor and holds no data (the API behind it checks
the caller on every request). A path never leaves the build directory: it is resolved and
must stay inside it, symlinks included. Vite's hashed ``assets/`` are cached for good and a
missing one is 404 (never ``index.html`` in place of a script); everything else is
revalidated, so a rebuild shows on the next load."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.routing import Match

from algotrade.core.model.errors import ConfigurationError

INDEX = "index.html"
ASSETS = "assets"  # Vite's build output: content-hashed names, immutable
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
REVALIDATE = {"Cache-Control": "no-cache"}


def build_file(root: Path, path: str) -> Path | None:
    """The file ``path`` names under the resolved directory ``root``; ``None`` when there is
    none or it would resolve outside ``root`` (``..``, an absolute path, a symlink out)."""
    try:
        candidate = (root / path).resolve()
        inside = candidate.is_relative_to(root) and candidate.is_file()
    except (OSError, ValueError):  # a null byte, a name too long
        return None
    return candidate if inside else None


def api_path(request: Request) -> bool:
    """Whether an API route serves this path under another method (the router reaches the web
    app only when no route matched path and method both)."""
    web = request.scope["route"].endpoint
    return any(
        route.matches(request.scope)[0] is Match.PARTIAL
        for route in request.app.router.routes
        if getattr(route, "endpoint", None) is not web
    )


def web_router(dist: Path) -> APIRouter:
    """The router serving the build in ``dist``; refuses a directory without ``index.html``
    (the web was not built: ``make web-build``)."""
    root = dist.resolve()
    index = root / INDEX
    if not index.is_file():
        raise ConfigurationError(
            f"ALGOTRADE_WEB_DIST={dist}: no {INDEX} there (build the web app: make web-build)"
        )
    router = APIRouter(tags=["web"])

    def web_app(path: str, request: Request) -> FileResponse:
        if api_path(request):
            raise HTTPException(405, "method not allowed")
        asset = path.split("/", 1)[0] == ASSETS
        found = build_file(root, path)
        if found is not None:
            return FileResponse(found, headers=IMMUTABLE if asset else REVALIDATE)
        if asset:
            raise HTTPException(404, f"no such build asset: {path}")
        return FileResponse(index, headers=REVALIDATE)

    summary = "The built web app: a file of the build, else index.html (ADR 0044)"
    for method in ("GET", "HEAD"):  # one route each: one OpenAPI operation id each
        router.add_api_route(
            "/{path:path}",
            web_app,
            methods=[method],
            response_class=FileResponse,
            summary=summary,
            operation_id=f"web_app_{method.lower()}",
        )
    return router
