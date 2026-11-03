"""``peer_sensitivity@v1``: which other names' earnings reports have moved this name, measured
(ADR 0050 decision 7, docs/event-sensitivity-plan.md 4.3), and when the next of them reports.

Candidates for a name X, from windows that end at the session: the ``CORRELATED`` names whose daily
returns correlate most with X's over the last 252 sessions, and the ``INDUSTRY`` best correlated of
its own ``instruments/company`` industry (a label over the whole universe). The sector-ETF
co-holdings of the plan wait for the owner's ``etf-holdings`` run. A candidate P is **tested**, not
assumed: each of P's earnings reports whose reaction session is on the grid (``pre`` P's own
session, ``post`` the next; an unknown time is left out) is an event for X, and X's reaction is its
idiosyncratic return there (its return minus beta_252d times SPY's) over X's normal day (the stdev
of its 20 idiosyncratic returns before). A session on which X reported itself is skipped. P is kept
when X's median multiple over at least ``MIN_REPORTS`` (8) such reports is above ``MIN_MULTIPLE``
(1.5 normal days); the kept peers, ranked by that median, are the ``TOP`` best. The plan's four
reports (decision 3) clear 1.5 by chance for about half of the names among about 40 candidates, so
this version asks for eight (decisions log 2026-11-02); the peers are still the best of the
candidates chosen in-sample: a backtested figure, and peers that report the same day reuse one
session of X.

    peers_kept                 how many candidates were kept (0 with candidates_tested 0: none
                               could be measured)
    candidates_tested          how many candidates had enough reports to be judged
    peer_<k>_id, _multiple, _n the k-th peer's instrument id, X's median multiple on its reports
                               and how many reports behind it (k = 1 .. 10)
    next_peer_report_date      the first report date after the session among the kept peers
    next_peer_report_id        the peer that reports it

Point in time: reports are those known by the session (``read_reactions``: ``known_from <= S``) with
a reaction session on or before it; the correlation, beta and normal-day windows all end at the
session, so a past session's peer list never saw a later report. A name with under 250 sessions of
bars, or fewer than 200 returns for the beta, is SHORT_HISTORY, and with no SPY bars every name is
NO_MARKET (every other column null); a candidate
with fewer than ``MIN_REPORTS`` testable reports cannot be kept. Candidates are those the name's
correlated returns point to: a peer that never moves the name is not kept however alike the
industry. One row per instrument traded on the session.
"""

import warnings
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import SYMBOLS, read_reactions
from algotrade.features.rollups.event_study import moves
from algotrade.features.rollups.event_study.event_reaction import (
    HISTORY,
    earnings_positions,
)
from algotrade.features.rollups.price.price_stats import BARS, CLOSE

NAME = "peer_sensitivity"
VERSION = 1
COMPANY = "instruments/company"
OK, SHORT_HISTORY, NO_MARKET = "OK", "SHORT_HISTORY", "NO_MARKET"
WINDOW = 252  # sessions of the correlation and the beta
MIN_RETURNS = 200  # returns of the window a name needs (a young listing has fewer)
CORRELATED = 30  # candidates by correlation
INDUSTRY = 10  # candidates from the name's own industry, by correlation
MIN_REPORTS = 8  # testable reports a peer needs (a median of fewer clears 1.5 by chance too often)
MIN_MULTIPLE = 1.5  # median normal days a kept peer moves the name by
TOP = 10  # peers kept
BLOCK = 500  # names whose correlations are held at once

_EARN = f"{earnings.EVENTS}.ts"
_NONE = (
    f"fewer than {moves.MIN_SESSIONS} sessions of the name's own bars, or fewer than {MIN_RETURNS} "
    "returns for its beta (SHORT_HISTORY), or no peer measured to move it"
)


def _features() -> tuple[Feature, ...]:
    out = [
        Feature(
            "peer_status",
            "str",
            "category",
            f"OK: the name has {moves.MIN_SESSIONS} sessions of bars and a beta; SHORT_HISTORY: "
            "fewer; NO_MARKET: SPY has no bars or is not in the reference (every other column "
            "is null)",
            "never",
            "label",
            categories=(OK, SHORT_HISTORY, NO_MARKET),
            inputs=(CLOSE,),
        ),
        Feature(
            "peers_kept",
            "int",
            "count",
            f"How many candidate peers (the {CORRELATED} most correlated names and the {INDUSTRY} "
            f"best correlated of its industry) moved the name by more than {MIN_MULTIPLE:g} normal "
            f"days at the median over at least {MIN_REPORTS} of their earnings reports; chosen "
            "in-sample as the best of the candidates tested, so a backtested figure",
            "SHORT_HISTORY or NO_MARKET (every other column is null)",
            valid_range=(0, TOP),
            inputs=(CLOSE, _EARN),
        ),
        Feature(
            "candidates_tested",
            "int",
            "count",
            f"How many candidate peers had {MIN_REPORTS} or more testable reports to be judged: "
            "0 with peers_kept 0 means no peer could be measured, not that none moves the name",
            "SHORT_HISTORY or NO_MARKET (every other column is null)",
            valid_range=(0, CORRELATED + INDUSTRY),
            inputs=(CLOSE, _EARN),
        ),
    ]
    for k in range(1, TOP + 1):
        inputs = (CLOSE, _EARN, f"{COMPANY}.industry")
        out += [
            Feature(f"peer_{k}_id", "str", "text",
                    f"The instrument id of the name's number {k} measured peer (ranked by its "
                    "median "
                    "multiple)", _NONE, inputs=inputs),
            Feature(f"peer_{k}_multiple", "float32", "ratio",
                    f"The name's median idiosyncratic reaction on peer {k}'s earnings reports, in "
                    "its own normal days", _NONE, valid_range=(0, None), inputs=inputs),
            Feature(f"peer_{k}_n", "int", "count",
                    f"How many of peer {k}'s reports stand behind peer_{k}_multiple", _NONE,
                    valid_range=(MIN_REPORTS, None), inputs=inputs),
        ]  # fmt: skip
    out += [
        Feature("next_peer_report_date", "date", "date",
                "The first earnings report date after the session among the kept peers",
                f"{_NONE}, or no kept peer has a report date after the session known",
                inputs=(_EARN,)),
        Feature("next_peer_report_id", "str", "text",
                "The kept peer that reports on next_peer_report_date",
                f"{_NONE}, or no kept peer has a report date after the session known",
                inputs=(_EARN,)),
    ]  # fmt: skip
    return tuple(out)


FEATURES = _features()
COLUMNS = column_types(FEATURES)


def market_betas(returns: np.ndarray, market: int) -> np.ndarray:
    """OLS beta of each column's last ``WINDOW`` returns on column ``market``'s (NaN: fewer than
    ``MIN_RETURNS`` sessions with both)."""
    r, m = returns[-WINDOW:], returns[-WINDOW:, [market]]
    both = np.isfinite(r) & np.isfinite(m)
    count = both.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_r = np.where(both, r, 0.0).sum(axis=0) / count
        mean_m = np.where(both, m, 0.0).sum(axis=0) / count
        dr, dm = np.where(both, r - mean_r, 0.0), np.where(both, m - mean_m, 0.0)
        beta = (dr * dm).sum(axis=0) / (dm * dm).sum(axis=0)
    beta[count < MIN_RETURNS] = np.nan
    return np.asarray(beta, dtype=np.float64)


def standardised(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The last ``WINDOW`` returns of each column demeaned and scaled to unit variance, NaN as 0
    (a missing day adds nothing to a correlation); and the mask of columns with ``MIN_RETURNS``."""
    r = returns[-WINDOW:]
    ok = np.isfinite(r).sum(axis=0) >= MIN_RETURNS
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN column is 0, not an error
        z = (r - np.nanmean(r, axis=0)) / np.nanstd(r, axis=0)
    z = np.where(np.isfinite(z), z, 0.0).astype(np.float32)
    z[:, ~ok] = 0.0
    return z, ok


def candidates(
    z: np.ndarray, ok: np.ndarray, eligible: np.ndarray, industry: np.ndarray, block: slice
) -> dict[int, list[int]]:
    """Candidate peers per column of ``block``: the ``CORRELATED`` most correlated eligible names
    and the ``INDUSTRY`` most correlated of the column's own industry (``industry`` integer codes,
    -1 for none)."""
    corr = z[:, block].T @ z / len(z)  # (block, names)
    corr[:, ~(ok & eligible)] = -np.inf
    out: dict[int, list[int]] = {}
    for row, col in enumerate(range(block.start, min(block.stop, z.shape[1]))):
        corr[row, col] = -np.inf  # never itself
        keep = min(CORRELATED, corr.shape[1])
        top = np.argpartition(-corr[row], keep - 1)[:keep]
        found = {int(i) for i in top if np.isfinite(corr[row, i])}
        if industry[col] >= 0:
            same = np.flatnonzero((industry == industry[col]) & np.isfinite(corr[row]))
            best = same[np.argsort(-corr[row, same])[:INDUSTRY]]
            found |= {int(i) for i in best}
        out[col] = sorted(found)
    return out


def measure(
    mult: np.ndarray, col: int, cands: list[int], reports: dict[int, list[int]], own: set[int]
) -> tuple[list[tuple[int, float, int]], int]:
    """``([(peer column, median multiple, reports)], candidates tested)`` for ``col``: the kept
    are the candidates whose reports (reaction positions in ``reports``, the name's own report
    sessions ``own`` skipped) moved it by more than ``MIN_MULTIPLE`` normal days at the median
    over ``MIN_REPORTS`` or more, best first, at most ``TOP``; tested are those with enough
    reports to be judged. The best of about 40 candidates chosen in-sample: backtested."""
    kept = []
    tested = 0
    for peer in cands:
        rows = [p for p in reports.get(peer, ()) if p not in own]
        values = mult[rows, col] if rows else np.empty(0)
        values = values[np.isfinite(values)]
        if len(values) < MIN_REPORTS:
            continue
        tested += 1
        if np.median(values) > MIN_MULTIPLE:
            kept.append((peer, float(np.median(values)), len(values)))
    return sorted(kept, key=lambda k: (-k[1], k[0]))[:TOP], tested


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    read = read_reactions(inputs, session, HISTORY)
    px, ids = read.px, read.ids
    traded = ~np.isnan(px[-1])
    width = px.shape[1]
    returns = moves.log_returns(px)
    spy = read.spy
    beta = np.full(width, np.nan) if spy is None else market_betas(returns, spy)
    idio = returns if spy is None else returns - beta * returns[:, [spy]]
    mult = moves.multiples(idio)
    known, unknown = earnings_positions(read, read.column_of)
    z, ok = standardised(returns)
    ok &= np.isfinite(beta) & (np.isfinite(px).sum(axis=0) >= moves.MIN_SESSIONS)
    eligible = np.array([len(known.get(c, ())) >= MIN_REPORTS for c in range(width)])
    company = inputs.get(COMPANY)
    industry = np.full(width, -1)
    if company is not None and "industry" in company.columns:
        labels = company.drop_duplicates("instrument_id").set_index("instrument_id")["industry"]
        found = pd.Series(ids).map(labels).fillna("").astype(str)
        industry = np.where(found == "", -1, pd.factorize(found)[0])
    cols: dict[str, list[object]] = {name: [None] * width for name in COLUMNS}
    cols["peer_status"] = [
        NO_MARKET if spy is None else (OK if ok[c] else SHORT_HISTORY) for c in range(width)
    ]
    if spy is None:  # no SPY to take the market out: a fact about the input, not the names
        ok[:] = False
    for start in range(0, width, BLOCK):
        pool = candidates(z, ok, eligible, industry, slice(start, start + BLOCK))
        for col, cands in pool.items():
            if not ok[col] or not traded[col]:
                continue
            own = set(known.get(col, ())) | set(unknown.get(col, ()))
            kept, tested = measure(mult, col, cands, known, own)
            cols["peers_kept"][col] = len(kept)
            cols["candidates_tested"][col] = tested
            for k, (peer, med, n) in enumerate(kept, start=1):
                cols[f"peer_{k}_id"][col] = str(ids[peer])
                cols[f"peer_{k}_multiple"][col] = med
                cols[f"peer_{k}_n"][col] = n
            ahead = [
                (d, str(ids[p]))
                for p, _, _ in kept
                for d in read.all_reports.get(str(ids[p]), ())
                if d > session
            ]
            if ahead:
                cols["next_peer_report_date"][col], cols["next_peer_report_id"][col] = min(ahead)
    frame = pd.DataFrame({"instrument_id": ids, **cols})[["instrument_id", *COLUMNS]]
    frame = frame[traded].sort_values("instrument_id", kind="stable").reset_index(drop=True)
    out: pd.DataFrame = moves.nullable_ints(frame, COLUMNS)
    for name, dtype in COLUMNS.items():
        if dtype == "float32":
            out[name] = out[name].astype(float)
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The other names whose earnings reports have moved this name by 1.5 normal days or more, "
    "measured over its most correlated names and its industry, ranked, and the next of them to "
    "report",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=HISTORY),
        Input(SYMBOLS, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
