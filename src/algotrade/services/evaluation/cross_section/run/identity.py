"""The identity of one edge evaluation (ADR 0053, ADR 0063): which ``Edge`` fields make a run
(``RUN_INPUTS``) and which are ``BOOKKEEPING``, the run hash, the run's effective split and
whether it is exploratory, and the trials earlier runs of the edge logged (the deflated Sharpe
ratio's count)."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime

from algotrade.config.edges.document import (
    LEGACY_SITE_CUTOFF,
    LEGACY_SITE_OWNERS,
    MAIN,
    Edge,
    job_name,
)
from algotrade.config.edges.identity import identity_dict
from algotrade.config.user import SITE_USER
from algotrade.services.evaluation.cross_section.baselines.variant import Variant
from algotrade.services.evaluation.cross_section.hit import IMPLIED_VOL_FIELD
from algotrade.services.evaluation.cross_section.legs.key import HARNESS_VERSION
from algotrade.services.evaluation.cross_section.measures import BASELINE, MEMBER
from algotrade.services.evaluation.cross_section.random_picks import DEFAULT_DRAWS, SEED_VERSION
from algotrade.storage.tables.result_writer import ResultWriter

# What an edge contributes to a run's identity (``run_hash``); every other field of ``Edge`` is
# ``BOOKKEEPING`` (the user's or the server's state, prose, the site's decisions): changing one
# never changes what a run measures, so it never makes a new run (nor reseeds the random draws).
# A fitness test classifies every field: a new one fails until it is named here.
RUN_INPUTS = (
    "id", "outcome", "schedule", "universe", "top_k", "screeners", "baselines", "frozen_from",
    "site_frozen_from", "base", "picks", "variants", "scorer_features", "ensemble", "gate",
    "variant_grid", "position_baselines",
)  # fmt: skip
BOOKKEEPING = (
    "name", "thesis", "mechanism", "persistence", "sources", "quality_bar", "notes", "status",
    "rejection_reason", "evidence", "promoted", "compared", "basis_horizon", "extends", "follow",
    "audit", "owner", "published", "family", "oos_class",
    "mechanism_kind", "asset_class", "plain_reason", "verdict_profile", "holdout_from",
)  # fmt: skip


def run_hash(
    edge: Edge,
    variants: Sequence[Variant],
    start: date,
    end: date,
    as_of: datetime,
    iv_field: str = IMPLIED_VOL_FIELD,
    split_from: date | None = None,
    random_draws: int = DEFAULT_DRAWS,
) -> str:
    """Identity of one evaluation: the edge's ``RUN_INPUTS``, each variant's config hash, the range,
    the outcomes' ``as_of``, the run's implied-vol field, its effective split, the random draws
    per session and their seed scheme (``SEED_VERSION``), and the harness version."""
    payload = {
        "edge": identity_dict({k: asdict(edge)[k] for k in RUN_INPUTS}),
        "iv_field": iv_field,
        "variants": [(v.id, v.hash) for v in variants],
        "range": [start, end],
        "as_of": as_of,
        "split_from": split_from,
        "random": [random_draws, SEED_VERSION],
        "version": HARNESS_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def effective_split(run: date | None, edge: Edge) -> tuple[date | None, bool]:
    """(split, exploratory): the run's split, else the edge's own ``frozen_from``. Exploratory
    when it is not the site edge's (a copy whose split moved), or the user moved the split of
    an edge whose out-of-sample result they had seen (a permanent label)."""
    split = run or edge.frozen_from
    moved = "split_moved_after_viewing" in edge.audit.labels
    return split, split != edge.site_frozen_from or moved


def prior_trials(
    writer: ResultWriter, edge_id: str, user_id: str
) -> set[tuple[str, str, str, int]]:
    """(edge variant, variant, config hash, horizon) of earlier runs; a trial logged before
    edge variants existed is the edge's own ("main"). The site's log includes the runs recorded
    under ``LEGACY_SITE_OWNERS``, so the deflated Sharpe ratio still counts them. A logged
    baseline is not a trial."""
    found: set[tuple[str, str, str, int]] = set()
    records = list(writer.runs_for(job_name(edge_id, user_id)))
    if user_id == SITE_USER:  # the legacy owners' records from before the cutoff only
        for legacy in LEGACY_SITE_OWNERS:
            records += [
                r
                for r in writer.runs_for(job_name(edge_id, legacy))
                if (r.finished_at or r.started_at) < LEGACY_SITE_CUTOFF
            ]
    for record in records:
        for t in record.stats.get("trials", []):
            if t.get("role") in (BASELINE, MEMBER):  # a comparison or a grid member, not a trial
                continue  # (no role: counted; an ensemble is one trial, whatever its grid)
            found.add(
                (t.get("edge_variant") or MAIN, t["variant"], t["config_hash"], int(t["horizon"]))
            )
    return found
