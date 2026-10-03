"""Implementations of each CLI sub-command. Each returns a process exit code."""

import argparse
import json
import sys

from algotrade.analytics.report import markdown_table
from algotrade.config.resolve import ResolvedConfig
from algotrade.config.user import UserContext
from algotrade.core.errors import ConfigurationError
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.configs import resolve_config
from algotrade.services.datasets import list_datasets, load_dataset
from algotrade.services.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.services.evaluation.suite import run_suite, with_benchmark_excess
from algotrade.services.jobs import JobStatus, LocalJobRunner
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.readers import StoreReader
from algotrade.strategies.trading.registry import create_strategy

SCORECARD_COLUMNS = (
    "strategy",
    "dataset",
    "total_return",
    "excess_return",
    "sharpe",
    "excess_sharpe",
    "max_drawdown",
    "num_trades",
    "exposure",
)


def reader_for(args: argparse.Namespace) -> StoreReader:
    return StoreReader(open_backend(args.data_url))


def cmd_datasets(args: argparse.Namespace) -> int:
    for info in list_datasets(reader_for(args)).values():
        print(f"{info.name:<26} {','.join(info.symbols):<18} {info.description}")
    return 0


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


def _resolved(args: argparse.Namespace, config_id: str) -> ResolvedConfig:
    return resolve_config(open_config_store(args.config_dir), config_id, UserContext(args.user))


def cmd_config(args: argparse.Namespace) -> int:
    resolved = _resolved(args, args.config_id)
    if args.action == "validate":
        print(
            f"{resolved.config.id}: OK (hash {resolved.hash[:12]}, layers {list(resolved.layers)})"
        )
        return 0
    print(
        json.dumps(
            {"hash": resolved.hash, "layers": list(resolved.layers), **resolved.canonical()},
            indent=2,
            default=str,
        )
    )
    return 0


def _config_backtest(args: argparse.Namespace) -> int:
    """Configured backtests go through the jobs runner, exactly as the UI will submit them."""
    if args.start is None or args.end is None:
        raise ConfigurationError("--config needs --start and --end")
    backend = open_backend(args.data_url)
    resources = {"reader": StoreReader(backend), "configs": open_config_store(args.config_dir)}
    runner = LocalJobRunner(backend.runs, LIBRARY_HANDLERS, resources)
    try:
        params = {
            "config": args.config,
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
        }
        job = runner.wait(runner.submit("backtest", params, UserContext(args.user), force=True))
    finally:
        runner.shutdown()
    if job.status is JobStatus.FAILED:
        print(f"error: {job.error}", file=sys.stderr)
        return 2
    print(json.dumps({"job_id": job.job_id, "user": job.user, **job.result}, indent=2, default=str))
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    if args.config:
        return _config_backtest(args)
    if not args.strategy:
        raise ConfigurationError("--dataset needs --strategy")
    data, terms = load_dataset(reader_for(args), args.dataset)
    strategy = create_strategy(args.strategy, **parse_params(args.param))
    result = run_backtest(data, strategy, instruments=terms)
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
    rows = run_suite(reader_for(args))
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
