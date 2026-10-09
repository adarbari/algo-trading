"""The winners at one grid session (ED6 winners study, definition 1). **With the harness and the
training frame, the only module of ``services/evaluation`` that imports
``algotrade.data.outcomes``** (a fitness test checks all three): the winner label is the outcome
of the window that starts at S, which is what the study explains; nothing else it reads is later
than S.

A winner is an eligible name whose ``fwd_excess_return`` over the benchmark is in the top
``top_fraction`` of the eligible names with a COMPLETE or DELISTED row (the delisted count: leaving
them out would drop the worst losers and bias the threshold up). A session where more than
``max_missing_fraction`` of the eligible names have no such row is refused, not labelled
(``MissingDataError``, ADR 0008): a threshold over a thin survivor sample is not the study's.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.outcomes import read_outcomes
from algotrade.storage.tables.schemas import FORWARD_RETURNS

COUNTED = ("COMPLETE", "DELISTED")
HINT = "run `algotrade-ingest run outcomes --horizon 504 --from ... --to ...` (a backfill)"


@dataclass(frozen=True)
class Labels:
    """``winners``: instrument ids at or above ``threshold``; ``eligible``: names considered;
    ``measured``: those with a counted row; ``missing_fraction``: the rest over ``eligible``."""

    session: date
    winners: frozenset[str]
    threshold: float
    eligible: int
    measured: int
    missing_fraction: float


def label_winners(
    outcomes: pd.DataFrame,
    eligible: Collection[str],
    session: date,
    settings: WinnersStudySettings,
) -> Labels:
    """The winners among ``eligible`` from ``outcomes`` (the rows of the window starting at
    ``session``: ``instrument_id``, ``fwd_excess_return``, ``outcome_status``). Raises
    ``MissingDataError`` when no name is eligible or too many have no counted row."""
    ids = sorted(set(eligible))
    if not ids:
        raise MissingDataError(FORWARD_RETURNS, f"no eligible name on {session}", HINT)
    rows = outcomes[outcomes["instrument_id"].isin(ids)]
    rows = rows[rows["outcome_status"].isin(COUNTED)]
    excess = pd.to_numeric(rows["fwd_excess_return"], errors="coerce")
    counted = pd.DataFrame(
        {"instrument_id": rows["instrument_id"].astype(str), "excess": excess}
    ).dropna()
    counted = counted.drop_duplicates("instrument_id")
    missing = (len(ids) - len(counted)) / len(ids)
    if missing > settings.max_missing_fraction:
        raise MissingDataError(
            FORWARD_RETURNS,
            f"{missing:.1%} of the {len(ids)} eligible names on {session} have no COMPLETE or "
            f"DELISTED outcome (at most {settings.max_missing_fraction:.1%})",
            HINT,
        )
    threshold = float(np.quantile(counted["excess"].to_numpy(), 1.0 - settings.top_fraction))
    won = counted[counted["excess"] >= threshold]
    return Labels(
        session=session,
        winners=frozenset(won["instrument_id"]),
        threshold=threshold,
        eligible=len(ids),
        measured=len(counted),
        missing_fraction=missing,
    )


def read_labels(
    reader: StoreReader,
    session: date,
    eligible: Collection[str],
    settings: WinnersStudySettings,
) -> Labels:
    """``label_winners`` over the stored outcomes of the window starting at ``session``."""
    outcomes = read_outcomes(
        reader, settings.horizon_sessions, [session], settings.benchmark, sorted(set(eligible))
    )
    return label_winners(outcomes, eligible, session, settings)
