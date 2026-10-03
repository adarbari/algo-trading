"""``algotrade-api``: serve the API with uvicorn on 127.0.0.1:8000 (``--reload`` for dev)."""

import argparse

import uvicorn

from algotrade.config.env import load_dotenv

APP = "algotrade_api.app:app"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="algotrade-api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    args = parser.parse_args(argv)
    load_dotenv()
    uvicorn.run(APP, host=args.host, port=args.port, reload=args.reload)
