"""The leg key (ADR 0063): the identity of everything a screener's statistic at one session (a
leg) is a function of besides the session itself, so a leg computed by one run is the leg any run
with the same key would compute, and the random draws of a session can be seeded by it.

A key is a sha256 of a canonical JSON of the trial, the universe, the implied-vol field, the event
class and offset, the draws per session, the site's cost grid (leg v2 counts hits at each level,
ADR 0064), the definitions of every expression feature the user's catalogue resolves, and the
three scheme versions. A change to a screener's or the harness's
Python that changes a leg bumps ``LEG_VERSION`` (ADR 0063 amendment 9)."""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from algotrade.config.strategy.schema import Selection
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.evaluation.cross_section.random_picks import SEED_VERSION

LEG_VERSION = 5  # bump when a change to code (not config) changes what a leg holds
# 2 (ADR 0064 decision 4): every pick with its rank, score, reason, gross value, dip, ADV at D;
# hits at each cost level
# 3 (ADR 0053 amendment 2026-10-18): a screener out of sample also holds its sector-stratified
# random draws (``random_picks.SectorDraws``)
# 4 (ADR 0053 amendment 2026-10-18, buy/hold bands): a leg of an edge with ``hold_rank`` also holds
# the band names ranked ``top_k + 1 .. hold_rank``; every leg is recomputed once (one full re-run)
# 5 (ADR 0088, E6a): every pick's trade-contract fields (exit, exit kind, capital, return on
# capital gross and net, max adverse, price source, outcome licence); every leg is recomputed once
# (one full re-run)
HARNESS_VERSION = 2  # 2: the run hash is an allowlist of ``RUN_INPUTS``, not the whole Edge


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def universe_hash(universe: Selection) -> str:
    """The canonical form of a selection: its name, rule tree, cap and order."""
    return _digest(asdict(universe))


def expression_hash(features: FeatureSet) -> str:
    """Every expression feature's definition the catalogue resolves (site and the user's),
    by name: a changed formula, parameter or range changes it."""
    return _digest(
        {
            name: [e.definition.canonical(), e.definition.valid_range]  # no prose
            for name, e in sorted(features.expressions.items())
        }
    )


def leg_key(
    trial_hash: str,
    universe: str,
    iv_field: str,
    event_class: str | None,
    offset: int,
    draws: int,
    expr_defs_hash: str,
    top_k: int | None,
    base: str,
    picks: str,
    cost_levels: tuple[float, ...],
    short_adv_floor: float | None = None,
    event_subtype: str | None = None,
    hold_rank: int | None = None,
) -> str:
    """The key of a leg (``top_k``, ``base`` and ``picks`` of the scope's edge cut its picks and
    names and are not in the trial hash for ``main``): ``universe`` is ``universe_hash``,
    ``expr_defs_hash`` is ``expression_hash``, ``cost_levels`` the site's cost grid in bp;
    ``short_adv_floor`` the dollar volume a name must have to be in a short leg; ``hold_rank`` the
    buy/hold band's depth (the leg holds the names down to it). It, the floor and ``event_subtype``
    join the digest only when set, so the keys of every long edge, of every schedule without a
    subtype and of every edge without a band are unchanged but for ``LEG_VERSION``."""
    extra = {} if short_adv_floor is None else {"short_adv_floor": float(short_adv_floor)}
    subtype = {"event_subtype": event_subtype} if event_subtype else {}
    band = {} if hold_rank is None else {"hold_rank": hold_rank}
    return _digest(
        {
            **extra,
            **subtype,
            **band,
            "trial": trial_hash,
            "universe": universe,
            "iv_field": iv_field,
            "event_class": event_class,
            "offset": offset,
            "draws": draws,
            "cost_levels": [float(c) for c in cost_levels],
            "top_k": top_k,
            "base": base,
            "picks": picks,
            "expressions": expr_defs_hash,
            "versions": [HARNESS_VERSION, LEG_VERSION, SEED_VERSION],
        }
    )
