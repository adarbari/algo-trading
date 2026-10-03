"""Implementations of each CLI sub-command. Each returns a process exit code."""

import argparse
import json

from algotrade.analytics.report import markdown_table
from algotrade.core.errors import ConfigurationError
from algotrade.data.golden import build_golden
from algotrade.data.store import DatasetStore
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.services.evaluation.suite import run_suite, with_benchmark_excess
from algotrade.strategies.trading.registry import create_strategy

SCORECARD_COLUMNS = (
    "strategy", "dataset", "total_return", "excess_return", "sharpe", "excess_sharpe",
    "max_drawdown", "num_trades", "exposure",
)  # fmt: skip


def cmd_datasets(args: argparse.Namespace) -> int:
    store = DatasetStore(args.datasets_dir)
    if args.action == "build":
        for name in build_golden(store):
            print(f"built {name}")
        return 0
    if args.action == "list":
        for info in store.manifest().values():
            print(f"{info.name:<26} {','.join(info.symbols):<18} {info.description}")
        return 0
    problems = store.verify()
    for p in problems:
        print(p)
    print("datasets OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def parse_params(pairs: list[str]) -> dict[str, float | int | str]:
    params: dict[str, float | int | str] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise ConfigurationError(f"--param expects KEY=VALUE, got {pair!r}")
        value: float | int | str
        try:
            value = int(raw)
        except ValueError:
            try:
                value = float(raw)
            except ValueError:
                value = raw
        params[key] = value
    return params


def cmd_backtest(args: argparse.Namespace) -> int:
    data = DatasetStore(args.datasets_dir).load(args.dataset)
    strategy = create_strategy(args.strategy, **parse_params(args.param))
    result = run_backtest(data, strategy)
    print(
        json.dumps(
            {
                "strategy": result.strategy,
                "params": result.params,
                "dataset": args.dataset,
                "metrics": result.metrics.as_dict(),
            },
            indent=2,
        )
    )
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    rows = run_suite(DatasetStore(args.datasets_dir))
    table = markdown_table(with_benchmark_excess(rows), SCORECARD_COLUMNS)
    print(table)
    if args.report:
        args.report.write_text(f"# Strategy scorecard\n\n{table}\n")

    if args.update_baseline:
        save_baseline(rows, args.baseline)
        print(f"\nbaseline written to {args.baseline}")
        return 0
    if not args.baseline.exists():
        print(f"\nno baseline at {args.baseline}; run with --update-baseline", flush=True)
        return 1
    diffs = compare_to_baseline(rows, load_baseline(args.baseline))
    if diffs:
        print(f"\n{len(diffs)} result(s) differ from baseline:")
        for d in diffs:
            print(f"  {d.describe()}")
        print("If intended: `algotrade-backtest evaluate --update-baseline`, then commit it.")
        return 1
    print("\nall results match baseline")
    return 0
