"""The ``results/edge_picks`` rows of one session, stamped (ADR 0081): the table's one framer."""

from datetime import date, datetime

import pandas as pd

from algotrade.config.user import SITE_USER
from algotrade.services.evaluation.edge_picks.night import EdgePicks
from algotrade.storage.tables.edge_schemas import EDGE_PICKS

RESULT = EDGE_PICKS.name.removeprefix("results/")
SOURCE = "edge-picks"


def edge_picks_frame(
    rows: list[EdgePicks], session: date, run_id: str, now: datetime
) -> pd.DataFrame:
    """``rows`` as the table's rows of ``session`` (the partition), written at ``now``."""
    frame = pd.DataFrame(
        {
            "user_id": SITE_USER,
            "edge_id": [r.edge_id for r in rows],
            "screener": [r.screener for r in rows],
            "status": [r.status for r in rows],
            "reason": [r.reason for r in rows],
            "config_hash": [r.config_hash for r in rows],
            "top_k": pd.array([r.top_k for r in rows], dtype="Int64"),
            "pick_ids": [list(r.pick_ids) for r in rows],
        }
    )
    frame["session_date"] = session
    frame["knowledge_ts"] = pd.Timestamp(now)
    frame["source"] = SOURCE
    frame["run_id"] = run_id
    return frame[[c.name for c in EDGE_PICKS.columns if c.name in frame.columns]]
