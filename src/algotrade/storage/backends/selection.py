"""Point-in-time run selection shared by all backends, so they cannot disagree."""

from collections.abc import Mapping, Sequence
from datetime import datetime

import pandas as pd


def latest_run(knowledge: Mapping[str, pd.Timestamp], as_of: datetime | None) -> str | None:
    """The run with the greatest knowledge_ts that is <= as_of (ties broken by run id)."""
    eligible = {
        run: ts for run, ts in knowledge.items() if as_of is None or ts <= pd.Timestamp(as_of)
    }
    if not eligible:
        return None
    return max(eligible, key=lambda r: (eligible[r], r))


def select_instruments(frame: pd.DataFrame, instruments: Sequence[str] | None) -> pd.DataFrame:
    if instruments is None:
        return frame.reset_index(drop=True)
    return frame[frame["instrument_id"].isin(list(instruments))].reset_index(drop=True)
