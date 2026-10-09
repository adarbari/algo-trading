"""The candidate edge draft of a winners study run that passed its gate (ADR 0053 amendment
2026-10-09, ED6). ``write_draft`` reads the run's record only and writes ``<out_dir>/<id>.toml``
(``var/edge_drafts`` by default): an edge document with ``status = "candidate"``, the study's
``frozen_from``, the nine quality-bar answers as TODO for a human to write, a 63- or 252-session
outcome (never the study's own 504-session one: a hold that long is not an implementation), and
the top-decile rule preset the tells suggest, as comments to copy once reviewed. It refuses a run
that is not a COMPLETE winners study run or did not pass the gate, writes nothing in that case,
never writes under ``config/site`` (the owner moves a reviewed draft there by hand), and
publishes by temp file then rename, so a draft is whole or absent."""

from pathlib import Path
from typing import Any

from algotrade.config.edges.document import QUALITY_BAR
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.evaluation.discovery.persist import JOB
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.result_writer import ResultWriter

DEFAULT_DIR = Path("var/edge_drafts")
DRAFT_HORIZON = 252  # sessions: 63 is the other allowed one; never the study's 504
TODO = "TODO"
MAX_RULES = 5  # the preset sketch lists the strongest tell of each of this many clusters


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
        "# blocks of 504 sessions overlap at their edges, so they are not independent sessions.",
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


def write_draft(
    writer: ResultWriter,
    run_id: str,
    out_dir: Path = DEFAULT_DIR,
    config_root: Path | None = None,
) -> Path:
    """Write the draft of ``run_id`` and return its path. ``ConfigurationError`` (nothing
    written) when the run is unknown, is not a COMPLETE winners study run, did not pass the gate,
    or ``out_dir`` is under ``config_root/site``."""
    record = writer.load_run(run_id)
    if record is None or record.job != JOB:
        raise ConfigurationError(f"{run_id}: not a winners study run")
    if record.status is not RunStatus.COMPLETE:
        raise ConfigurationError(f"{run_id}: the run is {record.status}, not COMPLETE")
    if not record.stats.get("passed"):
        raise ConfigurationError(
            f"{run_id}: the run did not pass the gate "
            f"({record.stats.get('observed_clusters')} clusters, null threshold "
            f"{record.stats.get('null_threshold')}); no draft is written"
        )
    _refuse_config_site(out_dir, config_root)
    text = render_draft(run_id, record.stats)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{draft_id(run_id)}.toml"
    temp = path.with_suffix(".toml.tmp")
    temp.write_text(text)
    temp.replace(path)
    return path
