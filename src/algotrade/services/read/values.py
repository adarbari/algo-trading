"""Values a read returns: the one scalar coercion (``to_scalar``) shared by reads and runs, and
the UNKNOWN vocabulary a value missing for the session carries (ADR 0036, ADR 0037).

A value that is not there is never silently ``None``: it comes with an ``Unknown`` saying why
(``UnknownCode``) and where (``detail`` names the table and the session)."""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue
from algotrade.features.framework.feature import NullReason
from algotrade.storage.tables.schemas import COMMON

__all__ = ["NullReason", "Unknown", "UnknownCode", "records", "stored_values", "to_scalar"]


class UnknownCode(StrEnum):
    """Why a value is UNKNOWN for the session (docs/api/read-model.md "Values and UNKNOWN")."""

    NO_PARTITION = "NO_PARTITION"  # the table has no partition for the session
    NO_ROW = "NO_ROW"  # the partition exists, the instrument has no row
    NULL = "NULL"  # stored null: see FeatureInfo.nullMeaning
    NOT_IN_CATALOGUE = "NOT_IN_CATALOGUE"  # the name is not in the caller's catalogue
    LICENCE = "LICENCE"  # a personal-licence feature and the caller is not its owner (ADR 0028)
    NOT_RUN = "NOT_RUN"  # a screener (or the data-quality check) has no run for the session
    PRE_SNAPSHOT = "PRE_SNAPSHOT"  # identity came from a later snapshot (survivorship)
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the feature is not defined for this instrument (ADR 0042)
    ILLIQUID = "ILLIQUID"  # an option feature null because the chain is too thin (ADR 0042)
    EXPLAINED = "EXPLAINED"  # the null is a fact: ``Unknown.reason`` says which (ADR 0046)


@dataclass(frozen=True)
class Unknown:
    """A value that is not known for the session, with the reason and where it was looked for
    (``"rollups/instrument/earnings@v1 has no partition for 2026-10-03"``). ``reason`` is set
    exactly when ``code`` is EXPLAINED."""

    code: UnknownCode
    detail: str
    reason: NullReason | None = None


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


def stored_values(row: Mapping[Any, Any], drop: Iterable[str] = ()) -> dict[str, FeatureValue]:
    """A stored row as ``{column: to_scalar(value)}``, without the point-in-time stamps
    (``session_date``, ``knowledge_ts``, ``source``, ``run_id``) and ``drop``."""
    skip = {*COMMON, *drop}
    return {str(k): to_scalar(v) for k, v in row.items() if str(k) not in skip}


def records(frame: pd.DataFrame, drop: Iterable[str] = ()) -> list[dict[str, FeatureValue]]:
    """``stored_values`` of every row of ``frame``."""
    dropped = tuple(drop)
    return [stored_values(r, dropped) for r in frame.to_dict("records")]
