"""Shared builders for the winners-study discovery tests: the study's settings from the site file
with overrides, and a frame of winners and controls with chosen feature columns."""

import tomllib
from dataclasses import replace
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.edges.winners import WinnersStudySettings, parse_winners
from algotrade.services.evaluation.discovery.frame import SessionFrame
from algotrade.services.evaluation.discovery.grid import GridSession
from algotrade.services.evaluation.discovery.labels import Labels
from tests.conftest import REPO_ROOT


def settings(**changes: Any) -> WinnersStudySettings:
    """The site's winners study settings, with fields replaced."""
    doc = tomllib.loads((REPO_ROOT / "config/site/studies/winners.toml").read_text())
    return replace(parse_winners(doc), **changes)


def session_frame_of(
    day: date,
    block: int,
    columns: dict[str, np.ndarray],
    winners: int = 10,
    controls: int = 30,
    losers: int = 10,
) -> SessionFrame:
    """A session of ``winners``, ``controls`` then ``losers`` rows; ``columns`` the feature values
    by field, of length winners + controls (the losers then repeat the first controls' values:
    they look like controls) or of the full length; one cell ``C`` so the permutation shuffles
    across all rows."""
    n = winners + controls + losers
    ids = [f"EQ:{i:03d}" for i in range(n)]
    frame = pd.DataFrame(
        {
            "instrument_id": ids,
            "winner": [i < winners for i in range(n)],
            "loser": [i >= winners + controls for i in range(n)],
            "cell": "C",
        }
    )
    for name, values in columns.items():
        v = np.asarray(values, dtype=float)
        if v.size == winners + controls:
            v = np.concatenate([v, v[winners : winners + losers]])
        frame[name] = v
    won, lost = frozenset(ids[:winners]), frozenset(ids[winners + controls :])
    labels = Labels(day, won, 0.5, n, n, frozenset(ids), 0.0, lost, -0.5)
    return SessionFrame(GridSession(day, block), labels, controls, (0, day.toordinal()), frame, ())
