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
) -> SessionFrame:
    """A session of ``winners`` then ``controls`` rows; ``columns`` the feature values by field
    (length winners + controls); one cell ``C`` so the permutation shuffles across all rows."""
    n = winners + controls
    ids = [f"EQ:{i:03d}" for i in range(n)]
    frame = pd.DataFrame(
        {"instrument_id": ids, "winner": [i < winners for i in range(n)], "cell": "C"}
    )
    for name, values in columns.items():
        frame[name] = np.asarray(values, dtype=float)
    labels = Labels(day, frozenset(ids[:winners]), 0.5, n, n, 0.0)
    return SessionFrame(GridSession(day, block), labels, controls, (0, day.toordinal()), frame, ())
