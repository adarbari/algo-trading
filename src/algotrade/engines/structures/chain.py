"""One session's stored chain as the engine reads it, and what makes a name's chain unusable on a
day (design 2.4): a ``DayChain`` carries the quotes, each underlying's quote, its chain status
label and when the partitions became known; ``Labels`` names the two statuses the engine tells
apart (the caller passes ``data.chains``'s, which this pure folder does not import)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Labels:
    """The chain labels that matter: ``ok`` is usable, ``stale`` is a feed fact (ADR 0054)."""

    ok: str = "OK"
    stale: str = "STALE_DATA"


@dataclass(frozen=True)
class DayChain:
    """What one session's stored chain says: the quotes (``instrument_id``, ``underlying_id``,
    ``expiry``, ``right`` C / P, ``strike``, ``bid``, ``ask``), each underlying's quote, its
    chain status label (``OK``, ``STALE_DATA``, ...) and when the partitions became known."""

    day: date
    options: pd.DataFrame | None
    spots: Mapping[str, float]
    labels: Mapping[str, str]
    known: datetime | None


def usable(chain: DayChain, ids: pd.Series, labels: Labels) -> np.ndarray:
    return np.array(
        [chain.labels.get(i) == labels.ok and np.isfinite(chain.spots.get(i, np.nan)) for i in ids]
    )


def why_not(chain: DayChain, ids: pd.Series, labels: Labels) -> list[str]:
    """Per name the reason its chain on ``chain.day`` is not usable (``""`` when it is):
    ``STALE_CHAIN:<day>`` for a stale feed, else ``NO_CHAIN:<day>`` (also a name that left the
    chain: a delisting is a missing chain, never a filled one)."""
    out = []
    for i in ids:
        label = chain.labels.get(i)
        if label == labels.ok and np.isfinite(chain.spots.get(i, np.nan)):
            out.append("")
        elif label == labels.stale:
            out.append(f"STALE_CHAIN:{chain.day}")
        else:
            out.append(f"NO_CHAIN:{chain.day}")
    return out
