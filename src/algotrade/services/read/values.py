"""Values a read returns: the one scalar coercion (``to_scalar``) shared by reads and runs, and
the UNKNOWN vocabulary a value missing for the session carries (ADR 0036, ADR 0037).

A value that is not there is never silently ``None``: it comes with an ``Unknown`` saying why
(``UnknownCode``) and where (``detail`` names the table and the session)."""

import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue


class UnknownCode(StrEnum):
    """Why a value is UNKNOWN for the session (docs/api/read-model.md "Values and UNKNOWN")."""

    NO_PARTITION = "NO_PARTITION"  # the table has no partition for the session
    NO_ROW = "NO_ROW"  # the partition exists, the instrument has no row
    NULL = "NULL"  # stored null: see FeatureInfo.nullMeaning
    NOT_IN_CATALOGUE = "NOT_IN_CATALOGUE"  # the name is not in the caller's catalogue
    LICENCE = "LICENCE"  # a personal-licence feature and the caller is not its owner (ADR 0028)
    NOT_RUN = "NOT_RUN"  # a screener has no run for the session
    PRE_SNAPSHOT = "PRE_SNAPSHOT"  # identity came from a later snapshot (survivorship)


@dataclass(frozen=True)
class Unknown:
    """A value that is not known for the session, with the reason and where it was looked for
    (``"rollups/instrument/earnings@v1 has no partition for 2026-10-03"``)."""

    code: UnknownCode
    detail: str


def to_scalar(value: Any) -> FeatureValue:
    """A stored scalar as a plain JSON-safe value: numpy / pandas scalars unwrapped, NaN and
    NaT -> ``None``, dates and timestamps -> ISO text, anything else -> its text."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return to_scalar(value.item())
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
