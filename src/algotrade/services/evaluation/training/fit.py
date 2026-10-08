"""Fit a learned scorer: a probit of the edge's hit on its standardised features (ADR 0053
amendment, ED7), the regime probit's model (``quant/probit.py``) on a ``TrainingFrame``.

Each feature is standardised on the training rows (mean, population standard deviation) so the
coefficients are comparable and the fit is well conditioned; the constant is the first
coefficient. ``score`` applies the fit to raw feature values and equals the expression feature
``render.py`` writes (``ncdf(b0 + sum w_i * (x_i - mean_i) / scale_i)``). Deterministic: no
randomness. The fit is refused, never guessed, on too few rows, fewer than ``MIN_SESSIONS``
independent decision sessions, one class, a constant feature or no convergence.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt

from algotrade.config.edges.document import MIN_INDEPENDENT_SESSIONS
from algotrade.core.model.errors import ConfigurationError
from algotrade.quant import probit
from algotrade.services.evaluation.training.frame import LABEL, TrainingFrame

MIN_ROWS = 100  # fewer labelled rows than this is not a fit
MIN_PER_CLASS = 10
MIN_SESSIONS = MIN_INDEPENDENT_SESSIONS  # independent decision sessions (docs/edges-plan.md)


@dataclass(frozen=True)
class ScorerFit:
    edge_id: str
    horizon: int
    features: tuple[str, ...]
    intercept: float
    weights: tuple[float, ...]  # on the standardised features
    means: tuple[float, ...]
    scales: tuple[float, ...]
    rows: int
    sessions: int
    positives: int
    fitted_through: date | None  # the date of the latest training window close
    loglik: float


def fit_scorer(training: TrainingFrame) -> ScorerFit:
    """The probit of ``training``'s label on its features. Raises ``ConfigurationError``."""
    frame = training.frame
    y = frame[LABEL].to_numpy(dtype=np.float64)
    positives = int(y.sum())
    if len(y) < MIN_ROWS or min(positives, len(y) - positives) < MIN_PER_CLASS:
        raise ConfigurationError(
            f"edge {training.edge_id}: {len(y)} training rows ({positives} hits) is too few to "
            f"fit (needs {MIN_ROWS} with {MIN_PER_CLASS} of each class)"
        )
    if training.sessions < MIN_SESSIONS:
        raise ConfigurationError(
            f"edge {training.edge_id}: {training.sessions} decision sessions before the frozen "
            f"period is below the {MIN_SESSIONS} independent sessions the quality bar asks; "
            "wait for more history rather than fit"
        )
    x = frame[list(training.features)].to_numpy(dtype=np.float64)
    means, scales = x.mean(axis=0), x.std(axis=0)
    if np.any(scales <= 0):
        raise ConfigurationError(f"edge {training.edge_id}: a feature is constant in training")
    design = np.column_stack([np.ones(len(y)), (x - means) / scales])
    try:
        result = probit.fit(design, y)
    except ValueError as exc:
        raise ConfigurationError(f"edge {training.edge_id}: {exc}") from exc
    if not result.converged:
        raise ConfigurationError(f"edge {training.edge_id}: the probit did not converge")
    return ScorerFit(
        edge_id=training.edge_id,
        horizon=training.horizon,
        features=training.features,
        intercept=float(result.coef[0]),
        weights=tuple(float(w) for w in result.coef[1:]),
        means=tuple(float(m) for m in means),
        scales=tuple(float(s) for s in scales),
        rows=len(y),
        sessions=training.sessions,
        positives=positives,
        fitted_through=training.fitted_through,
        loglik=result.loglik,
    )


def score(fit: ScorerFit, x: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """The fitted probability of a hit for raw feature rows ``x`` (n x len(features))."""
    raw = np.asarray(x, dtype=np.float64)
    z = (raw - np.array(fit.means)) / np.array(fit.scales)
    return probit.predict(np.column_stack([np.ones(len(z)), z]), [fit.intercept, *fit.weights])
