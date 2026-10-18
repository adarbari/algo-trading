"""The winners and losers at one grid session (ED6 winners study, definition 1). **With the
harness and the training frame, the only module of ``services/evaluation`` that imports
``algotrade.data.outcomes``** (a fitness test checks all three): the winner label is the outcome
of the window that starts at S, which is what the study explains; nothing else it reads is later
than S.

A winner is an eligible name whose ``fwd_excess_return`` over the benchmark is in the top
``top_fraction`` of the eligible names with a COMPLETE or DELISTED row (the delisted count: leaving
them out would drop the worst losers and bias the threshold up). The losers are the mirror: the
eligible names at or below the ``bottom_fraction`` quantile of the same counted rows (many of
them delisted), counted alike; a tell must separate winners from them as well as from the
matched controls. A session where more than
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
    ``measured``: those with a counted row; ``missing_fraction``: the rest over ``eligible``;
    ``losers`` at or below ``loser_threshold`` (NaN when a hand-built value leaves them out)."""

    session: date
    winners: frozenset[str]
    threshold: float
    eligible: int
    measured: int
    measured_ids: frozenset[str]  # the eligible names with a counted row: the control pool
    missing_fraction: float
    losers: frozenset[str] = frozenset()
    loser_threshold: float = float("nan")


def label_winners(
    outcomes: pd.DataFrame,
    eligible: Collection[str],
    session: date,
    settings: WinnersStudySettings,
) -> Labels:
    """The winners and losers among ``eligible`` from ``outcomes`` (the rows of the window
    starting at ``session``: ``instrument_id``, ``fwd_excess_return``, ``outcome_status``). Raises
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
    floor = float(np.quantile(counted["excess"].to_numpy(), settings.bottom_fraction))
    lost = counted[counted["excess"] <= floor]
    return Labels(
        session=session,
        winners=frozenset(won["instrument_id"]),
        threshold=threshold,
        eligible=len(ids),
        measured=len(counted),
        measured_ids=frozenset(counted["instrument_id"]),
        missing_fraction=missing,
        losers=frozenset(lost["instrument_id"]) - frozenset(won["instrument_id"]),
        loser_threshold=floor,
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
