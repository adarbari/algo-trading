"""``algotrade-backtest`` CLI (``algotrade`` is kept as an alias through phase 1).

algotrade-backtest [--data-url URL] datasets list
algotrade-backtest backtest --strategy sma_crossover --dataset bull_trend [--param fast=10]
algotrade-backtest [--user U] backtest --config sma_trend --start 2020-01-01 --end 2022-12-31
algotrade-backtest [--user U] config validate|show sma_trend
algotrade-backtest evaluate [--update-baseline] [--report scorecard.md]
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from algotrade.core.errors import AlgoTradeError
from algotrade_backtest.commands import cmd_backtest, cmd_config, cmd_datasets, cmd_evaluate

DEFAULT_BASELINE = Path("benchmarks/baseline.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="algotrade-backtest", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-url",
        help="storage to read (default: $ALGOTRADE_DATA_URL). Golden datasets live in the "
        "fixture store built by `make golden-store`.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ds = sub.add_parser("datasets", help="list the golden datasets in the store")
    ds.add_argument("action", choices=["list"])

    parser.add_argument("--config-dir", help="site/user configs (default: ./config)")
    parser.add_argument("--user", help="config owner (default: $ALGOTRADE_USER or local)")

    bt = sub.add_parser("backtest", help="a strategy on a golden dataset, or a config")
    target = bt.add_mutually_exclusive_group(required=True)
    target.add_argument("--dataset", help="golden dataset name (use with --strategy)")
    target.add_argument("--config", help="strategy config id (use with --start/--end)")
    bt.add_argument("--strategy")
    bt.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    bt.add_argument("--start", type=date.fromisoformat)
    bt.add_argument("--end", type=date.fromisoformat)

    cf = sub.add_parser("config", help="validate or show a resolved config")
    cf.add_argument("action", choices=["validate", "show"])
    cf.add_argument("config_id")

    ev = sub.add_parser("evaluate", help="run every strategy on every dataset vs the baseline")
    ev.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ev.add_argument("--update-baseline", action="store_true")
    ev.add_argument("--report", type=Path, help="write a Markdown scorecard here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "datasets": cmd_datasets,
        "backtest": cmd_backtest,
        "evaluate": cmd_evaluate,
        "config": cmd_config,
    }
    try:
        return handlers[args.command](args)
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
