"""Settle open paper trades from the stored outcomes (ADR 0053 amendment 2026-10-09).

An open trade (a name bought at ``buy_session``, sold ``horizon`` sessions later) is closed by
the outcome stored for it: ``cross_section/hit.apply_outcome`` is the one place an edge's
``[outcome]`` meets the stored fields, so a paper trade wins or loses exactly as a backtest row
would. Outcomes are read as of ``now`` (a window not closed has no row: the trade stays open,
never a loss). The edge's outcome is judged by the definition it had at the signal: a trade
whose edge's ``[outcome]`` changed since (``outcome_hash``) is skipped with that reason. A name
with no outcome row although its window's partition is stored has no entry bar (skipped); a
window with no outcome at all ``GRACE_SESSIONS`` after its sell session is skipped too, with
the reason: a missing result is never a loss and never a zero. An outcome that reads the implied
vol (``expires_otm``: the strike is set from it) reads it at the signal session D, as the harness
does (``harness.implied_at``, ``harness.iv_field_of``); a name whose vol
is missing or invalid there is skipped with that reason, never a loss. ``excess_return`` of a
settled trade is set only when the outcome's value is a return (not an ``expires_otm`` cushion)."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.outcomes import read_outcomes
from algotrade.services.evaluation.cross_section.harness import BENCHMARK, implied_at, iv_field_of
from algotrade.services.evaluation.cross_section.hit import (
    INVALID_IMPLIED_VOL,
    MISSING_DRAWDOWN,
    MISSING_VALUE,
    NO_IMPLIED_VOL,
    apply_outcome,
    is_return,
    needs_implied_vol,
)
from algotrade.services.evaluation.forward.signals import advance

GRACE_SESSIONS = 5  # sessions after a window's close an outcome may still be stored
OPEN, WON, LOST, SKIPPED = "open", "won", "lost", "skipped"
# What a reader sees for the harness's exclusion codes (a trader's sentence, never the code).
REASONS = {
    MISSING_VALUE: "the result could not be computed (no benchmark return)",
    MISSING_DRAWDOWN: "the worst drawdown of the window could not be computed",
    NO_IMPLIED_VOL: "no implied vol was stored for the name at the signal session",
    INVALID_IMPLIED_VOL: "the implied vol stored at the signal session was not usable",
}


@dataclass(frozen=True)
class Settled:
    """One trade's new state (``status`` won / lost / skipped); ``excess_return`` None unless
    counted."""

    instrument_id: str
    status: str
    reason: str
    excess_return: float | None
    delisted: bool


def outcome_hash(edge: Edge) -> str:
    """A fingerprint of the edge's ``[outcome]``: what a hit means."""
    text = json.dumps(asdict(edge.outcome), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _skipped(instrument: str, why: str) -> Settled:
    return Settled(instrument, SKIPPED, why, None, False)


def settle_group(
    reader: StoreReader,
    edge: Edge,
    trades: pd.DataFrame,
    session: date,
    now: datetime,
) -> list[Settled]:
    """The trades of one (edge, buy session, horizon) group (open rows of the book) that
    ``now`` settles; a trade still waiting is not returned."""
    first = trades.iloc[0]
    buy, horizon = first["buy_session"], int(first["horizon_sessions"])
    names = [str(i) for i in trades["instrument_id"]]
    changed = trades["outcome_hash"] != outcome_hash(edge)
    out = [
        _skipped(i, "the edge's outcome changed after the signal")
        for i in trades.loc[changed, "instrument_id"]
    ]
    names = [i for i in names if i not in {s.instrument_id for s in out}]
    if not names:
        return out
    try:
        stored = read_outcomes(reader, horizon, [buy], BENCHMARK, as_of=now)
    except MissingDataError:
        stored = pd.DataFrame()
    if stored.empty:
        late = session >= advance(first["sell_session"], GRACE_SESSIONS)
        return out + (
            [_skipped(i, "no outcome stored for its window") for i in names] if late else []
        )
    mine = stored[stored["instrument_id"].isin(names)]
    try:
        implied = (
            implied_at(reader, iv_field_of(edge), names, first["signal_session"])
            if needs_implied_vol(edge)
            else None
        )
    except MissingDataError:
        return out + [_skipped(i, "no implied vol stored at the signal session") for i in names]
    result = apply_outcome(edge, mine, implied).set_index("instrument_id") if len(mine) else None
    for name in names:
        if result is None or name not in result.index:
            out.append(_skipped(name, "no entry bar at the buy session"))
            continue
        row = result.loc[name]
        if row["excluded"]:
            out.append(_skipped(name, REASONS.get(str(row["excluded"]), str(row["excluded"]))))
            continue
        out.append(
            Settled(
                name,
                WON if row["hit"] else LOST,
                "",
                float(str(row["value"])) if is_return(edge) else None,
                bool(row["delisted"]),
            )
        )
    return out
