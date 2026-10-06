"""The probit model: ``P(y = 1 | x) = Phi(x . b)`` fitted by maximum likelihood.

The regime track's bear-state probit (docs/market-regime-plan.md section 3E: Chen 2009, "Do
macroeconomic variables have regime-dependent effects on stock return dynamics?"; Nyberg 2013,
"Predicting bear and bull stock markets with dynamic binary time series models") is this model
with a constant, the term spread, inflation and the high-yield spread as ``x`` and a dated bear
state ahead as ``y``. A dynamic probit (Nyberg) is the same fit with the lagged state as one
more column of ``x``.

    fit      Newton-Raphson on the log-likelihood from ``b = 0``, with step halving so the
             likelihood never falls (the probit log-likelihood is concave, so this converges
             unless the classes are separable, where the coefficients run off: then
             ``converged`` is False after ``max_iter``)
    predict  ``Phi(X b)``

Deterministic: no randomness, the same input gives the same coefficients. The normal CDF is
``black_scholes.norm_cdf`` (accurate in both tails), its owner.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from algotrade.quant.black_scholes import norm_cdf, norm_pdf

type Array = npt.NDArray[np.float64]
TINY = 1e-300  # a probability floor so log(0) never happens in a separated tail
MIN_STEP = 1e-6  # step halving gives up below this fraction of the Newton step


@dataclass(frozen=True)
class ProbitFit:
    """``coef``: one per column of ``X``; ``converged``: the last step was below ``tol``;
    ``loglik``: the log-likelihood at ``coef``."""

    coef: Array
    converged: bool
    loglik: float


def _design(x: npt.ArrayLike, y: npt.ArrayLike) -> tuple[Array, Array]:
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    if xs.ndim != 2 or ys.ndim != 1 or xs.shape[0] != ys.shape[0]:
        raise ValueError("X must be n x k and y of length n")
    if xs.shape[0] < xs.shape[1] or xs.shape[1] == 0:
        raise ValueError(f"need at least as many rows as columns, got {xs.shape}")
    if not (np.all(np.isfinite(xs)) and np.all((ys == 0) | (ys == 1))):
        raise ValueError("X must be finite and y 0 or 1 (drop rows with a missing value)")
    return xs, ys


def _loglik(x: Array, sign: Array, coef: Array) -> float:
    return float(np.sum(np.log(np.maximum(norm_cdf(sign * (x @ coef)), TINY))))


def fit(x: npt.ArrayLike, y: npt.ArrayLike, *, max_iter: int = 50, tol: float = 1e-8) -> ProbitFit:
    """Maximum-likelihood probit coefficients of ``y`` (0 / 1, length n) on ``x`` (n x k; add a
    column of ones for a constant). Raises ``ValueError`` on a bad shape, a missing value, or
    columns that are linearly dependent (a singular information matrix)."""
    if max_iter < 1 or tol <= 0:
        raise ValueError("max_iter must be >= 1 and tol > 0")
    xs, ys = _design(x, y)
    sign = 2.0 * ys - 1.0
    coef = np.zeros(xs.shape[1])
    loglik = _loglik(xs, sign, coef)
    for _ in range(max_iter):
        z = xs @ coef
        qz = sign * z
        lam = sign * norm_pdf(qz) / np.maximum(norm_cdf(qz), TINY)  # the score per row
        information = (xs * (lam * (lam + z))[:, None]).T @ xs  # minus the Hessian
        try:
            step = np.linalg.solve(information, xs.T @ lam)
        except np.linalg.LinAlgError as exc:
            raise ValueError(f"the columns of X are linearly dependent: {exc}") from exc
        scale = 1.0
        while True:
            trial = coef + scale * step
            trial_ll = _loglik(xs, sign, trial)
            if trial_ll >= loglik or scale < MIN_STEP:
                break
            scale /= 2.0
        moved = float(np.max(np.abs(trial - coef)))
        if trial_ll >= loglik:
            coef, loglik = trial, trial_ll
        if moved < tol:
            return ProbitFit(coef, True, loglik)
    return ProbitFit(coef, False, loglik)


def predict(x: npt.ArrayLike, coef: npt.ArrayLike) -> Array:
    """``Phi(x . coef)`` per row of ``x`` (a single row gives a 0-d array); NaN where a value
    of the row is NaN."""
    return norm_cdf(np.asarray(x, dtype=np.float64) @ np.asarray(coef, dtype=np.float64))
