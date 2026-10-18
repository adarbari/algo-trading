"""The ``portfolio_return`` outcome of an edge document (ADR 0053 amendment, ADR 0074): the value of
one session is the return of a weighted book of the picks minus the return of a blended benchmark
over the same window, so an allocation edge (ETF rotation, tactical asset allocation) is judged
against what a passive mix of its own constituents would have paid.

This module owns the vocabulary and the parsing (``parse_mix``: ``"mix:SPY=0.6,AGG=0.4"`` into
weights; the weighting rules; what a portfolio outcome may combine with); the arithmetic is the
harness's (``services/evaluation/cross_section/portfolio/``). Split from ``document.py`` (at its
line cap)."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

PORTFOLIO_KIND = "portfolio_return"
BENCHMARK_BASE = "benchmark"  # ``base``: what the book is compared with is the blended benchmark
MIX = "mix:"  # a benchmark of this form is a blend of the listed instruments
CASH = "CASH"  # a pick that earns the T-bill yield (``rates/treasury``) instead of an instrument
ENSEMBLE = "ensemble"  # the id of the combined variant of an ``[ensemble]`` (a screener may not be)
OOS_CLASSES = ("trend",)  # ``oos_class``: what ``verdict.toml [oos_haircut]`` has a share for
VOL_RETURN_FIELD = "rollup.trend_stats@v2.ret_1d"  # the daily return a vol_target book is sized by
VOL_WINDOW = 60  # sessions of the book's daily returns its volatility is measured over
MIN_VOL_WINDOW = 20  # a sample standard deviation over fewer sessions says nothing
WEIGHTINGS = ("equal", "inverse_vol", "score")
EQUAL, INVERSE_VOL, SCORE = WEIGHTINGS
# A blend's weights add to one within this tolerance (``0.6, 0.4`` is exact, thirds are not).
MIX_TOLERANCE = 1e-6
_TICKER = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


def parse_mix(benchmark: str, where: str = "benchmark") -> tuple[tuple[str, float], ...]:
    """The ``(ticker, weight)`` pairs of ``"mix:SPY=0.6,AGG=0.4"``, in the order written. Fails
    closed: a ticker listed twice, a weight outside ``(0, 1]``, a weight sum other than one and a
    ticker that is not a plain symbol are refused, never normalised."""
    if not benchmark.startswith(MIX):
        raise ConfigurationError(f"{where}: {benchmark!r} is not a mix (expected 'mix:T=w,T=w')")
    found: dict[str, float] = {}
    for part in benchmark[len(MIX) :].split(","):
        ticker, sep, raw = part.strip().partition("=")
        ticker = ticker.strip()
        if not sep or not _TICKER.fullmatch(ticker):
            raise ConfigurationError(
                f"{where}: {part.strip()!r} is not TICKER=weight in {benchmark!r}"
            )
        if ticker in found:
            raise ConfigurationError(f"{where}: {ticker} is listed twice in {benchmark!r}")
        try:
            weight = float(raw)
        except ValueError:
            raise ConfigurationError(
                f"{where}: the weight of {ticker} is {raw.strip()!r}, not a number"
            ) from None
        if not math.isfinite(weight) or not 0 < weight <= 1:
            raise ConfigurationError(
                f"{where}: the weight of {ticker} must be in (0, 1], got {raw}"
            )
        found[ticker] = weight
    total = sum(found.values())
    if abs(total - 1.0) > MIX_TOLERANCE:
        raise ConfigurationError(f"{where}: the weights of {benchmark!r} add to {total:g}, not 1")
    return tuple(found.items())


def blend(benchmark: str) -> tuple[tuple[str, float], ...]:
    """The constituents of a portfolio outcome's benchmark: ``SPY`` is the blend of SPY alone."""
    return parse_mix(benchmark) if benchmark.startswith(MIX) else ((benchmark, 1.0),)


def benchmark_of(o: Table, benchmarks: Sequence[str]) -> str:
    """The benchmark text of a ``portfolio_return`` outcome: one of ``benchmarks`` that is a
    real index (never ``none``: a book has no meaning without something to beat) or a valid mix."""
    raw = o.text("benchmark", "") if "benchmark" in o.names() else ""
    if not raw:
        raise ConfigurationError(f"{o.where} benchmark: required for a portfolio_return outcome")
    if raw.startswith(MIX):
        parse_mix(raw, f"{o.where} benchmark")
        return raw
    real = [b for b in benchmarks if b != "none"]
    if raw not in real:
        raise ConfigurationError(
            f"{o.where} benchmark: a portfolio_return outcome is read against {real} or a mix "
            f"('mix:SPY=0.6,AGG=0.4'), got {raw!r}"
        )
    return raw


def weighting_of(o: Table, kind: str) -> tuple[str, str | None]:
    """``(weighting, vol_field)`` of an outcome: only a portfolio outcome has either; an
    ``inverse_vol`` book names the declared feature its volatility is read from at D."""
    names = o.names()
    if kind != PORTFOLIO_KIND:
        for key in ("weighting", "vol_field"):
            if key in names:
                raise ConfigurationError(
                    f"{o.where} {key}: only a portfolio_return outcome has one"
                )
        return EQUAL, None
    weighting = o.choice("weighting", EQUAL, WEIGHTINGS)
    vol_field = o.text("vol_field", "") or None
    if weighting == INVERSE_VOL and vol_field is None:
        raise ConfigurationError(
            f"{o.where} vol_field: an inverse_vol book needs the feature its volatility is read "
            f"from"
        )
    if weighting != INVERSE_VOL and vol_field is not None:
        raise ConfigurationError(f"{o.where} vol_field: only an inverse_vol book reads one")
    return weighting, vol_field


def vol_target_of(o: Table, kind: str) -> tuple[float | None, int, str]:
    """``(vol_target, vol_window, vol_return_field)`` of an outcome: the book's annualised
    volatility target (a fraction in ``(0, 1]``, None: none), the sessions it is measured over
    and the daily return feature it is measured from (ADR 0074 amendment). Only a
    ``portfolio_return`` outcome has any; ``vol_window`` and ``vol_return_field`` need a target."""
    names = o.names()
    keys = ("vol_target", "vol_window", "vol_return_field")
    if kind != PORTFOLIO_KIND:
        for key in keys:
            if key in names:
                raise ConfigurationError(
                    f"{o.where} {key}: only a portfolio_return outcome has one"
                )
        return None, VOL_WINDOW, VOL_RETURN_FIELD
    target = o.number("vol_target", None, 0)
    if target is None:
        for key in keys[1:]:
            if key in names:
                raise ConfigurationError(f"{o.where} {key}: needs a vol_target")
        return None, VOL_WINDOW, VOL_RETURN_FIELD
    if not math.isfinite(target) or not 0 < target <= 1:
        raise ConfigurationError(
            f"{o.where} vol_target: expected a fraction in (0, 1], got {target}"
        )
    window = o.integer("vol_window", VOL_WINDOW, MIN_VOL_WINDOW)
    return target, window, o.text("vol_return_field", VOL_RETURN_FIELD)


@dataclass(frozen=True)
class Canary:
    """``[outcome.canary]`` (ADR 0074 amendment): the book moves to a defensive asset by the share
    of ``tickers`` whose ``field`` is negative at D, in units of ``breadth`` (a breadth of 1 is
    VAA's, 2 is DAA's). ``defensive``: ``("CASH",)``, or tickers of which the one with the highest
    ``field`` at D is held."""

    tickers: tuple[str, ...]
    field: str
    breadth: int
    defensive: tuple[str, ...]


def canary_of(o: Table, kind: str) -> Canary | None:
    """The outcome's ``[outcome.canary]`` (None: none). A portfolio outcome only; tickers are
    distinct plain symbols (turned into ids at D through the resolver, never here), ``breadth`` is
    between one and the number of canaries, and ``defensive`` is ``["CASH"]`` or tickers."""
    if "canary" not in o.names():
        return None
    if kind != PORTFOLIO_KIND:
        raise ConfigurationError(f"{o.where} canary: only a portfolio_return outcome has one")
    c = o.table("canary", ("tickers", "field", "breadth", "defensive"))
    tickers, defensive = c.strings("tickers", ()), c.strings("defensive", ())
    for key, found in (("tickers", tickers), ("defensive", defensive)):
        plain = [t for t in found if t != CASH or key == "defensive"]
        if not found or len(set(found)) != len(found):
            raise ConfigurationError(f"{c.where} {key}: expected one or more distinct symbols")
        if not all(_TICKER.fullmatch(t) for t in plain):
            raise ConfigurationError(f"{c.where} {key}: {list(found)} are not plain symbols")
    if CASH in tickers or (CASH in defensive and len(defensive) > 1):
        raise ConfigurationError(f"{c.where}: CASH is only the whole defensive choice ['CASH']")
    breadth = c.integer("breadth", 1, 1)
    if breadth > len(tickers):
        raise ConfigurationError(
            f"{c.where} breadth: {breadth} is more than the {len(tickers)} canaries"
        )
    return Canary(tickers, c.line("field"), breadth, defensive)


def check_portfolio(
    o: Table,
    kind: str,
    side: str,
    drawdown: float | None,
    hold: bool,
    schedule: str,
    schedules: Sequence[str],
    horizons: tuple[int, ...],
) -> None:
    """What a portfolio outcome may combine with: a long book (a short or a spread is not an
    allocation), no drawdown limit (the window's low is a name's, not the book's), no buy/hold
    band (the book's turnover is the weight change), and a rebalance schedule whose windows
    never overlap (``month_end``, or ``every_session`` held one session), as the turnover cost
    is charged between consecutive sessions. Any other kind is left alone."""
    if kind != PORTFOLIO_KIND:
        return
    if side != "long":
        raise ConfigurationError(f"{o.where} side: a portfolio_return book is long, got {side!r}")
    if drawdown is not None:
        raise ConfigurationError(f"{o.where} max_drawdown: not for a portfolio_return outcome")
    if hold:
        raise ConfigurationError(
            f"{o.where} hold_rank: not for a portfolio_return outcome (its turnover is the weight "
            f"change between rebalances)"
        )
    if schedule not in schedules or (schedule == "every_session" and horizons != (1,)):
        raise ConfigurationError(
            f"{o.where}: a portfolio_return rebalances on month_end, or every_session held one "
            f"session (horizon_sessions = [1]), so windows never overlap; got {schedule!r} with "
            f"{list(horizons)}"
        )


def check_base(kind: str, base: str, where: str) -> None:
    """``base = "benchmark"`` belongs to a portfolio outcome and only to it."""
    if (kind == PORTFOLIO_KIND) != (base == BENCHMARK_BASE):
        raise ConfigurationError(
            f"{where} base: "
            + (
                f"a portfolio_return is compared with its benchmark (base = {BENCHMARK_BASE!r}), "
                f"got {base!r}"
                if kind == PORTFOLIO_KIND
                else f"base = {BENCHMARK_BASE!r} belongs to a portfolio_return outcome"
            )
        )


def benchmark_words(benchmark: str) -> str:
    """A benchmark in words: ``SPY``, or ``a blend of 60% SPY and 40% AGG`` for a mix."""
    if not benchmark.startswith(MIX):
        return benchmark
    parts = [f"{weight:.0%} {ticker}" for ticker, weight in parse_mix(benchmark)]
    head = ", ".join(parts[:-1])
    return "a blend of " + (f"{head} and {parts[-1]}" if head else parts[0])


def ensemble_of(t: Table, screeners: Sequence[str], kind: str) -> tuple[str, ...]:
    """The members of the edge's ``[ensemble] variants = [...]``: the pre-registered grid of
    screeners (ADR 0074 amendment) whose books are averaged per session into one variant, ``()``
    when the document declares none. At least two distinct screeners the edge lists, for a
    portfolio outcome only (an average of weights); ``ensemble`` is the combined variant's id, so
    no screener may take it."""
    if ENSEMBLE in screeners:
        raise ConfigurationError(f"{t.where} screeners: {ENSEMBLE!r} is the id of an ensemble")
    if t.raw(ENSEMBLE) is None:
        return ()
    members = t.table(ENSEMBLE, ("variants",)).strings("variants", ())
    if kind != PORTFOLIO_KIND:
        raise ConfigurationError(f"{t.where} ensemble: only a portfolio_return outcome has one")
    if len(members) < 2 or len(set(members)) != len(members):
        raise ConfigurationError(
            f"{t.where} ensemble variants: expected two or more distinct screeners, got "
            f"{list(members)}"
        )
    unknown = [m for m in members if m not in screeners]
    if unknown:
        raise ConfigurationError(
            f"{t.where} ensemble variants: {unknown} are not among the edge's screeners "
            f"{list(screeners)} (a grid is pre-registered, so its members are listed)"
        )
    return members


def oos_class_of(t: Table) -> str | None:
    """The edge's ``oos_class`` (None: no haircut expectation is shown for it)."""
    return t.choice("oos_class", "", OOS_CLASSES) if "oos_class" in t.names() else None
