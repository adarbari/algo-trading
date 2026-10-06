"""``algotrade-api``: serve the API with uvicorn on 127.0.0.1:8000 (``--reload`` for dev).
With ``ALGOTRADE_AUTH=off`` (no token, ADR 0040) it refuses a non-loopback ``--host``."""

import argparse

import uvicorn

from algotrade.config.env import auth_mode, load_dotenv
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import require_loopback
from algotrade_api.auth.mode import AuthMode

APP = "algotrade_api.app:app"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="algotrade-api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    args = parser.parse_args(argv)
    load_dotenv()
    if auth_mode() == AuthMode.OFF:
        try:
            require_loopback(args.host)
        except ConfigurationError as exc:
            parser.error(str(exc))
    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload)
