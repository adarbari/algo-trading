"""The ML proposer v1 (ED6 winners study, definition 3): which features, standardised, best
separate the winners from the controls under the existing probit (``quant/probit.py``).

One probit per feature on its own non-NaN rows (an UNKNOWN is dropped, never imputed) of the
counted (feature, session) cells: ``winner ~ 1 + z``, ``z`` the feature standardised over those
rows. Features are ranked by the likelihood-ratio gain over the intercept-only fit. It proposes
and never judges: a row is ``proposed_by = "model"`` with no verdict; the gate of ``tells``
decides what the study finds. A feature with no variance, or only one class among its rows, is not
ranked. A fit that did not converge (separable classes) is ranked and says so.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from algotrade.quant import probit
from algotrade.services.evaluation.discovery.results import Proposal

MIN_PER_CLASS = 2  # a probit needs both classes; below this the coefficient is noise


def propose(
    values: npt.ArrayLike, winners: npt.ArrayLike, fields: Sequence[str]
) -> tuple[Proposal, ...]:
    """The ranked proposals over ``values`` (rows x ``fields``; NaN: not counted or UNKNOWN) and
    the 0 / 1 ``winners`` of the rows, best first, ties by feature name."""
    x = np.asarray(values, dtype=np.float64)
    y = np.asarray(winners, dtype=np.float64)
    found: list[tuple[float, str, float, int, bool]] = []
    for j, field in enumerate(fields):
        ok = np.isfinite(x[:, j])
        col, label = x[ok, j], y[ok]
        if min(float(label.sum()), float((1 - label).sum())) < MIN_PER_CLASS:
            continue
        sd = float(col.std())
        if sd <= 0.0:
            continue
        z = (col - col.mean()) / sd
        fit = probit.fit(np.column_stack([np.ones_like(z), z]), label)
        base = probit.fit(np.ones((z.size, 1)), label)
        gain = max(0.0, 2.0 * (fit.loglik - base.loglik))
        found.append((gain, field, float(fit.coef[1]), int(z.size), fit.converged))
    found.sort(key=lambda r: (-r[0], r[1]))
    return tuple(
        Proposal(feature=f, rank=k + 1, coefficient=c, gain=g, rows=n, converged=ok)
        for k, (g, f, c, n, ok) in enumerate(found)
    )
