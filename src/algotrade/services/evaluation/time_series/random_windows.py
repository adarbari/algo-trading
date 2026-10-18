"""Random window sets (ADR 0073): the random-pick analogue of a time-series edge. Each of
``DEFAULT_DRAWS`` draws takes, from the out-of-sample periods of an instrument (windows and
out-of-window stretches alike), as many as the edge has windows in them, uniformly without
replacement; its row has the draw's share of positive periods against the instrument's own
out-of-window share, so the read model places the edge's lift among the draws exactly as for
random picks (``percentile_of``). The generator is seeded by (key, ``SEED_VERSION``) only, so a
draw does not depend on the order observations arrive in, and the same inputs draw the same sets."""

import hashlib
from collections.abc import Sequence

import numpy as np

from algotrade.services.evaluation.cross_section.measures import SliceMeasure
from algotrade.services.evaluation.cross_section.random_picks import (
    DEFAULT_DRAWS,
    SEED_VERSION,
    draw_measure,
)
from algotrade.services.evaluation.time_series.measures import Obs


def generator(key: str) -> np.random.Generator:
    """The draws' generator, a function of ``key`` and the seed scheme only."""
    digest = hashlib.sha256(key.encode()).digest()
    entropy = [int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big")]
    return np.random.default_rng(np.random.SeedSequence([*entropy, SEED_VERSION]))


def random_windows(
    obs: Sequence[Obs], key: str, draws: int = DEFAULT_DRAWS
) -> tuple[SliceMeasure, ...]:
    """``draws`` measures, slice kind ``draw``, of random same-count window sets over ``obs``
    (sorted by first session so the order of arrival does not matter); empty when ``obs`` hold
    no window, no out-of-window period or fewer periods than windows."""
    ordered = sorted(obs, key=lambda o: o.period.first)
    k = sum(o.period.inside for o in ordered)
    outside = [o.value for o in ordered if not o.period.inside]
    if k < 1 or not outside or len(ordered) < k:
        return ()
    positive = np.array([o.value > 0 for o in ordered], dtype=np.float64)
    values = np.array([o.value for o in ordered], dtype=np.float64)
    order = generator(key).random((draws, len(ordered))).argsort(axis=1)[:, :k]
    hits = positive[order].sum(axis=1)
    means = values[order].mean(axis=1)
    base_hits = sum(v > 0 for v in outside)
    base_rate = base_hits / len(outside)
    out = []
    for draw in range(draws):
        rate = float(hits[draw]) / k
        out.append(
            draw_measure(
                draw, k, k, rate, int(hits[draw]), len(outside), base_hits, base_rate,
                float(means[draw]),
            )
        )  # fmt: skip
    return tuple(out)
