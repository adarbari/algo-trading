"""``algotrade-backtest`` CLI (``algotrade`` is kept as an alias through phase 1).

algotrade-backtest [--data-url URL] datasets list
algotrade-backtest backtest --strategy sma_crossover --dataset bull_trend [--param fast=10]
algotrade-backtest [--user U] backtest --config sma_trend --start 2020-01-01 --end 2022-12-31
algotrade-backtest [--user U] config validate|show sma_trend
algotrade-backtest [--user U] config validate-features   (the user's expression features)
algotrade-backtest evaluate [--update-baseline] [--report scorecard.md]
algotrade-backtest regime-scorecard [--report regime-scorecard.txt]   (the regime episodes)
algotrade-backtest fit-edge-scorer --edge ID [--from D] [--until D] [--out FILE]
algotrade-backtest evaluate-edges [--edge ID] [--from D] [--to D] [--as-of T] [--iv-field F]
                                    [--split-from D]
                                  [--report edges.md]
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from algotrade.config.env import load_dotenv
from algotrade.core.model.errors import AlgoTradeError
from algotrade_backtest.commands import (
    cmd_backtest,
    cmd_config,
    cmd_datasets,
    cmd_evaluate,
    cmd_evaluate_edges,
    cmd_fit_edge_scorer,
    cmd_regime_scorecard,
)

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

    cf = sub.add_parser(
        "config", help="validate or show a resolved config, or check the user's features"
    )
    cf.add_argument("action", choices=["validate", "show", "validate-features"])
    cf.add_argument("config_id", nargs="?", help="strategy / screener config id")

    ev = sub.add_parser("evaluate", help="run every strategy on every dataset vs the baseline")
    ev.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ev.add_argument("--update-baseline", action="store_true")
    ev.add_argument("--report", type=Path, help="write a Markdown scorecard here")

    rg = sub.add_parser(
        "regime-scorecard", help="the regime model against the reference crash episodes"
    )
    rg.add_argument("--report", type=Path, help="also write the text here")
    ee = sub.add_parser(
        "evaluate-edges", help="the edge harness: each edge's screeners against the stored outcomes"
    )
    ee.add_argument("--edge", help="one edge id (default: every open edge with screeners)")
    ee.add_argument("--from", dest="start", type=date.fromisoformat, help="first session")
    ee.add_argument("--to", dest="end", type=date.fromisoformat, help="last session")
    ee.add_argument(
        "--as-of", type=datetime.fromisoformat, help="outcomes known by this instant (default now)"
    )
    ee.add_argument(
        "--iv-field",
        help="the one implied-vol field of the run (default: our IV30, rollup.iv30@v1.iv30)",
    )
    ee.add_argument(
        "--split-from",
        type=date.fromisoformat,
        help="first session of the test slice (default: the user's evaluation.toml, else each "
        "edge's frozen_from); another split than frozen_from is exploratory",
    )
    ee.add_argument("--report", type=Path, help="also write the report here")
    fs = sub.add_parser(
        "fit-edge-scorer", help="fit an edge's learned scorer (probit) and write its TOML feature"
    )
    fs.add_argument("--edge", required=True, help="the edge id (its document has [scorer])")
    fs.add_argument("--from", dest="start", type=date.fromisoformat, help="first decision session")
    fs.add_argument("--until", type=date.fromisoformat, help="last decision session")
    fs.add_argument("--out", type=Path, help="the features file (default edge_scores.toml)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()  # same .env as algotrade-ingest, so both read the same ALGOTRADE_DATA_URL
    args = build_parser().parse_args(argv)
    handlers = {
        "datasets": cmd_datasets,
        "backtest": cmd_backtest,
        "evaluate": cmd_evaluate,
        "regime-scorecard": cmd_regime_scorecard,
        "evaluate-edges": cmd_evaluate_edges,
        "fit-edge-scorer": cmd_fit_edge_scorer,
        "config": cmd_config,
    }
    try:
        return handlers[args.command](args)
    except AlgoTradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
