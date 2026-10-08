"""Implementations of each CLI sub-command. Each returns a process exit code."""

import argparse
import json
import sys
from datetime import UTC, datetime

from algotrade.analytics.report import markdown_table
from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import load_edges
from algotrade.config.env import config_dir, data_url
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.config.site.settings import load_macro
from algotrade.config.strategy.regime import site_regime
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import UserContext
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.data import StoreReader
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.configs import default_user, resolve_config
from algotrade.services.datasets import list_datasets, load_dataset
from algotrade.services.evaluation.baseline import compare_to_baseline, load_baseline, save_baseline
from algotrade.services.evaluation.cross_section.report import render_edge_report
from algotrade.services.evaluation.overlay import compare_overlay, overlay_report
from algotrade.services.evaluation.regime_report import render
from algotrade.services.evaluation.regime_scorecard import load_history
from algotrade.services.evaluation.suite import run_suite, with_benchmark_excess
from algotrade.services.features import check_user_features
from algotrade.services.jobs import JobStatus, run_job
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import FORWARD_RETURNS
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
    return StoreReader(open_backend(data_url(args.data_url)))


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


def _user(args: argparse.Namespace) -> UserContext:
    return UserContext(args.user) if args.user else default_user("local")


def _resolved(args: argparse.Namespace, config_id: str) -> ResolvedConfig:
    return resolve_config(open_config_store(config_dir(args.config_dir)), config_id, _user(args))


def cmd_validate_features(args: argparse.Namespace) -> int:
    """Each of the user's expression features: type, inputs and a sample evaluation on the
    latest session its inputs have (``config/users/<user>/features/*.toml``)."""
    user = _user(args).user_id
    store = open_config_store(config_dir(args.config_dir))
    try:
        reader: StoreReader | None = reader_for(args)
    except AlgoTradeError as exc:
        print(f"warning: no data to evaluate on ({exc})", file=sys.stderr)
        reader = None
    checks = check_user_features(reader, store, user)
    print(f"{user}: {len(checks)} user feature(s), all valid")
    for c in checks:
        print(f"\nfeature.{c.name}  {c.kind} {c.dtype}  ({c.where})")
        print(f"  inputs: {', '.join(c.inputs)}")
        if c.session is None:
            print("  sample: nothing stored for its inputs")
            continue
        shown = ", ".join(f"{i}={v!r}" for i, v in c.sample)
        print(f"  {c.session}: {c.non_null}/{c.rows} instruments with a value; e.g. {shown}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if args.action == "validate-features":
        return cmd_validate_features(args)
    if not args.config_id:
        raise ConfigurationError(f"config {args.action} needs a config id")
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
    backend = open_backend(data_url(args.data_url))
    resources = {
        "reader": StoreReader(backend),
        "writer": ResultWriter(backend),
        "configs": open_config_store(config_dir(args.config_dir)),
    }
    params = {"config": args.config, "start": args.start.isoformat(), "end": args.end.isoformat()}
    job = run_job(backend.runs, LIBRARY_HANDLERS, resources, "backtest", params, _user(args))
    if job.status is JobStatus.FAILED:
        print(f"error: {job.error}", file=sys.stderr)
        return 2
    if job.result.get("survivorship_bias"):
        print(
            f"warning: --start {args.start} is before the first instrument reference snapshot "
            f"({job.result['reference_snapshot']}); the selection used a later list of "
            "instruments, so results carry survivorship bias",
            file=sys.stderr,
        )
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
    reader = reader_for(args)
    rows = run_suite(reader)
    table = markdown_table(with_benchmark_excess(rows), SCORECARD_COLUMNS)
    print(table)
    regime = site_regime(open_config_store(config_dir(args.config_dir)).load)
    overlay = overlay_report(compare_overlay(reader, regime))  # ADR 0049: never gates the run
    print(f"\n{overlay}")
    if args.report:
        args.report.write_text(f"# Strategy scorecard\n\n{table}\n\n{overlay}\n")

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


def cmd_regime_scorecard(args: argparse.Namespace) -> int:
    """The regime episode scorecard over the store (docs/market-regime-plan.md section 4):
    deterministic text, "no data" sections (exit 0) until the macro backfill has run."""
    configs = open_config_store(config_dir(args.config_dir))
    revised = [s.instrument_id for s in load_macro(configs).series if s.is_revised]
    history = load_history(reader_for(args), configs, _user(args))
    text = render(history, load_episodes(configs).episodes, revised)
    print(text, end="")
    if args.report:
        args.report.write_text(text)
    return 0


def cmd_evaluate_edges(args: argparse.Namespace) -> int:
    """The edge harness (ADR 0053) through the jobs runner: every open edge that has screeners
    or baselines (or the one ``--edge``) over ``--from``..``--to`` (default: the stored outcome
    sessions), outcomes known as of ``--as-of`` (default now), the test slice from
    ``--split-from`` (else
    the user's ``evaluation.toml``, else each edge's ``frozen_from``; another split is
    exploratory). Rows land in ``results/edge_eval``;
    a report with the survivorship line is printed (and written to ``--report``)."""
    backend = open_backend(data_url(args.data_url))
    reader = StoreReader(backend)
    configs = open_config_store(config_dir(args.config_dir))
    user = _user(args)
    edges = [e for e in load_edges(configs, user.user_id) if args.edge in (None, e.id)]
    if args.edge is None:
        edges = [e for e in edges if e.status not in CLOSED and (e.screeners or e.baselines)]
    if not edges:
        raise ConfigurationError(
            f"no edge to evaluate ({args.edge or 'no open edge has screeners'})"
        )
    stored = reader.dates(FORWARD_RETURNS)
    if not stored and not (args.start and args.end):
        raise ConfigurationError("no outcomes stored: run `algotrade-ingest run outcomes`")
    start, end = args.start or stored[0], args.end or stored[-1]
    as_of = args.as_of or datetime.now(UTC)
    resources = {"reader": reader, "writer": ResultWriter(backend), "configs": configs}
    reports, failed = [], False
    for edge in edges:
        params = {
            "edge": edge.id, "start": start.isoformat(), "end": end.isoformat(),
            "as_of": as_of.isoformat(), "iv_field": args.iv_field,
            "split_from": args.split_from.isoformat() if args.split_from else None,
        }  # fmt: skip
        job = run_job(backend.runs, LIBRARY_HANDLERS, resources, "edge-eval", params, user)
        if job.status is JobStatus.FAILED:
            print(f"error: {edge.id}: {job.error}", file=sys.stderr)
            failed = True
            continue
        reports.append(render_edge_report(job.result))
    text = "\n".join(reports)
    print(text, end="")
    if args.report:
        args.report.write_text(text)
    return 2 if failed else 0
