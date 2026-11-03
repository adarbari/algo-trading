"""The candidate edge draft of a winners study run that passed its gate (ADR 0053 amendment
2026-10-09, ED6). ``write_draft`` reads the run's record only and writes ``<out_dir>/<id>.toml``
(``var/edge_drafts`` by default): an edge document with ``status = "candidate"``, the study's
``frozen_from``, the nine quality-bar answers as TODO for a human to write, a 63- or 252-session
outcome (never the study's own 504-session one: a hold that long is not an implementation), and
the top-decile rule preset the tells suggest, as comments to copy once reviewed. It refuses a run
that is not a COMPLETE winners study run or did not pass the gate, writes nothing in that case,
never writes under ``config/site`` (the owner moves a reviewed draft there by hand), and
publishes by temp file then rename, so a draft is whole or absent.

``edge_proposal`` (W5) makes the same run judgeable: one rule screen per cluster's strongest
tell, ranked by it with no cut to choose, and a ``researching`` edge listing them, as documents
only; ``services/authoring/proposals.py`` writes them as a user's configs, so the harness
(``evaluate-edges``) judges what the study proposed. Pure: this package never writes configs."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.config.edges.document import QUALITY_BAR
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.evaluation.discovery.persist import JOB, TABLE_VERSION
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.result_writer import ResultWriter

DEFAULT_DIR = Path("var/edge_drafts")
DRAFT_HORIZON = 252  # sessions: 63 is the other allowed one; never the study's 504
TODO = "TODO"
MAX_RULES = 5  # the preset sketch lists the strongest tell of each of this many clusters
PROPOSAL_HORIZONS = (63, 252)  # sessions; never the study's 504 (not an implementation)
PROPOSAL_UNIVERSE = "liquid_common_stocks"  # the selection the site's momentum edge is judged on
PROPOSAL_TOP_K = 50  # the top of the tell's ranking each month end, as the site's momentum edge
# The decoys a proposed edge must beat (quality bar 9): size, and the volatility and liquidity the
# study's controls were matched on but a one-field ranking is not, so a tell that only stands in
# for them loses to its decoy.
PROPOSAL_BASELINES = ("size_small", "total_vol_high", "low_volatility", "amihud_illiquid")
STOCKS = ["COMMON_STOCK", "ADR"]


def draft_id(run_id: str) -> str:
    """The draft's edge id and file stem: the run id, lowercased (a valid id)."""
    return validate_id("edge draft", run_id.lower())


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _strongest(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """The strongest qualifying tell of each cluster, by |mean g|, at most ``MAX_RULES``."""
    best: dict[int, dict[str, Any]] = {}
    for t in stats["tells"]:
        k = t["cluster"]
        if k is not None and (k not in best or abs(t["mean_g"]) > abs(best[k]["mean_g"])):
            best[k] = t
    return sorted(best.values(), key=lambda t: (-abs(t["mean_g"]), t["feature"]))[:MAX_RULES]


def render_draft(run_id: str, stats: dict[str, Any]) -> str:
    """The draft's text."""
    edge_id = draft_id(run_id)
    tells = _strongest(stats)
    note = (
        f"Found by the winners study run {run_id}: {len(stats['clusters'])} clusters of tells "
        f"over {stats['blocks']} overlapping blocks. A proposal only."
    )
    lines = [
        f"# DRAFT from the winners study run {run_id}: a proposal, not evidence. {stats['blocks']}",
        f"# blocks of {stats['horizon_sessions']} sessions overlap at their edges, so they are not"
        " independent sessions.",
        "# Write every TODO, review it, then move it to config/site/edges/ by hand.",
        f"id = {_quote(edge_id)}",
        f"name = {_quote(TODO)}",
        f"thesis = {_quote(TODO)}",
        f"mechanism = {_quote(TODO)}",
        f"persistence = {_quote(TODO)}",
        'schedule = "every_session"',
        'top_k = "all"',
        'base = "universe"',
        "screeners = []",
        "baselines = []",
        'status = "candidate"',
        f"frozen_from = {stats['frozen_from']}",
        f"notes = {_quote(note)}",
        "",
        "[outcome]",
        'kind = "excess_return"',
        f"horizon_sessions = [{DRAFT_HORIZON}]  # 63 is the other allowed; never the study's 504",
        f"benchmark = {_quote(stats['benchmark'])}",
        "start_offset_sessions = 1",
        "",
        "[quality_bar]",
        *(f"{key} = {_quote(TODO)}" for key in QUALITY_BAR),
        "",
        "# Top-decile rule preset sketch: save as a screener preset (config/site/presets/",
        "# screeners/<id>/v1.toml) once the cut of each rule is chosen (the top decile of the",
        "# field over the eligible names).",
        f"# id = {_quote(edge_id)}",
        '# kind = "screener"',
        '# impl = "rules"',
        "# version = 1",
    ]
    for n, t in enumerate(tells, 1):
        op = "gte" if t["sign"] > 0 else "lte"
        lines += [
            f"# [criteria.tell_{n}]  # mean g {t['mean_g']:+.2f} over the winners",
            f"# field = {_quote(t['feature'])}",
            f'# op = "{op}"',
            f"# value = {TODO}  # the top-decile cut",
        ]
    return "\n".join(lines) + "\n"


def _refuse_config_site(out_dir: Path, config_root: Path | None) -> None:
    if config_root is None:
        return
    site = (config_root / "site").resolve()
    target = out_dir.resolve()
    if target == site or site in target.parents:
        raise ConfigurationError(
            f"{out_dir}: drafts never go under {config_root}/site; write to {DEFAULT_DIR}"
        )


@dataclass(frozen=True)
class EdgeProposal:
    """A judgeable proposal of a passed winners study run (W5): ``screens``, one rule screen per
    cluster (its strongest tell, ranked by it in the tell's sign; name -> document), and the
    ``edge`` document that lists them, both as a user's configs would store them. ``tells_tested``
    is how many features the study searched: the harness counts only these screens as trials, so
    the edge's notes carry it."""

    edge_id: str
    edge: dict[str, Any]
    screens: dict[str, dict[str, Any]]
    run_id: str
    tells_tested: int


def screen_document(
    field: str, sign: int, mean_g: float, eligible: dict[str, Any]
) -> dict[str, Any]:
    """The rule screen of one tell: the study's eligibility (stocks above its price and dollar
    volume floors), the tell stored (a missing value never passes), ranked by it, the highest
    first for a tell the winners had more of, the lowest first otherwise; the edge's ``top_k``
    takes the top. No cut value: the ranking is the rule."""
    return {
        "kind": "screener",
        "impl": "rules",
        "description": (
            f"Stocks ranked by {field}, {'highest' if sign > 0 else 'lowest'} first: a tell of "
            f"the winners study (mean g {mean_g:+.2f}); a proposal, not evidence."
        ),
        "criteria": {
            "security_type": {"field": "instrument.security_type", "op": "in", "value": STOCKS},
            "price": {
                "field": "rollup.price_stats@v2.close", "op": "gt",
                "value": eligible["min_price"],
            },
            "adv": {
                "field": "rollup.price_stats@v2.adv_usd_20d", "op": "gte",
                "value": eligible["min_adv_usd_20d"],
            },
            "tell": {"field": field, "op": "not_null"},
        },
        "rank": {"tie_break": field, "tie_break_order": "desc" if sign > 0 else "asc"},
    }  # fmt: skip


def edge_proposal(run_id: str, stats: dict[str, Any]) -> EdgeProposal:
    """The proposal of a passed run's ``stats`` (``passed_stats``). Its edge is ``researching``
    (the owner moves it to candidate; ML proposes, never judges), its ``frozen_from`` the
    study's, so the harness's test slice is out of the study's sample and its in-sample slice IS
    the discovery sample; the notes say so, with the run and the number of features searched."""
    tested = stats.get("features_tested")
    eligible = stats.get("eligible")
    if tested is None or eligible is None:
        raise ConfigurationError(
            f"{run_id}: the run records no features_tested / eligible (written before W5); re-run "
            "`algotrade-backtest study-winners` and propose from the new run"
        )
    edge_id = draft_id(run_id)
    tells = _strongest(stats)
    screens = {
        f"{edge_id}_t{n}": screen_document(t["feature"], t["sign"], t["mean_g"], eligible)
        for n, t in enumerate(tells, 1)
    }
    unknown = (
        f"Not established: proposed by the winners study run {run_id}, which found what the big "
        "winners had in common before they won; the harness judges whether it pays."
    )
    notes = (
        f"Proposed by the winners study run {run_id}: {len(tells)} tells kept of "
        f"{tested} features with data searched over {stats['blocks']} overlapping blocks of "
        f"{stats['horizon_sessions']} sessions. The in-sample slice (before "
        f"{stats['frozen_from']}) IS the discovery sample: biased, never evidence; only the "
        "test slice counts, and the "
        f"deflated Sharpe ratio counts these {len(tells)} screens, not the {tested} features "
        "searched. The study's eligibility was the universe as it was (delisted names included); "
        "the harness's is its own, so the in-sample comparison is not like for like."
    )
    edge = {
        "name": f"Winners study tells ({run_id})",
        "thesis": (
            "Stocks that look today like the big winners did before they won "
            f"({', '.join(t['feature'] for t in tells)}) outperform the market."
        ),
        "mechanism": unknown,
        "persistence": unknown,
        "schedule": "month_end",
        "universe": PROPOSAL_UNIVERSE,
        "top_k": PROPOSAL_TOP_K,
        "screeners": list(screens),
        "baselines": list(PROPOSAL_BASELINES),
        "frozen_from": date.fromisoformat(stats["frozen_from"]),
        "notes": notes,
        "sources": [{"title": f"Winners study run {run_id} (results/winners_study)"}],
        "outcome": {
            "kind": "excess_return",
            "horizon_sessions": list(PROPOSAL_HORIZONS),
            "benchmark": stats["benchmark"],
            "start_offset_sessions": 1,
        },
        "quality_bar": dict.fromkeys(QUALITY_BAR, unknown),
    }
    return EdgeProposal(edge_id, edge, screens, run_id, int(tested))


def passed_stats(writer: ResultWriter, run_id: str) -> dict[str, Any]:
    """The stats of ``run_id``, a COMPLETE winners study run of the current version that passed
    its gate; else ``ConfigurationError``. The run was unknown, is another job's or not COMPLETE,
    was written by an older study version (``TABLE_VERSION``: version 1 matched controls on two
    variables and had no winners-vs-losers gate, so its tells can be variance), or did not pass."""
    record = writer.load_run(run_id)
    if record is None or record.job != JOB:
        raise ConfigurationError(f"{run_id}: not a winners study run")
    if record.status is not RunStatus.COMPLETE:
        raise ConfigurationError(f"{run_id}: the run is {record.status}, not COMPLETE")
    version = record.stats.get("table_version", 1)
    if version < TABLE_VERSION:
        raise ConfigurationError(
            f"{run_id}: a version {version} winners study run (current {TABLE_VERSION}); re-run "
            "`algotrade-backtest study-winners` and draft from the new run"
        )
    if not record.stats.get("passed"):
        raise ConfigurationError(
            f"{run_id}: the run did not pass the gate "
            f"({record.stats.get('observed_clusters')} clusters, null threshold "
            f"{record.stats.get('null_threshold')}); no draft is written"
        )
    return dict(record.stats)


def write_draft(
    writer: ResultWriter,
    run_id: str,
    out_dir: Path = DEFAULT_DIR,
    config_root: Path | None = None,
) -> Path:
    """Write the draft of ``run_id`` and return its path. ``ConfigurationError`` (nothing
    written) when the run is refused (``passed_stats``) or ``out_dir`` is under
    ``config_root/site``."""
    stats = passed_stats(writer, run_id)
    _refuse_config_site(out_dir, config_root)
    text = render_draft(run_id, stats)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{draft_id(run_id)}.toml"
    temp = path.with_suffix(".toml.tmp")
    temp.write_text(text)
    temp.replace(path)
    return path
