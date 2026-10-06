"""``earnings_schedule@v1``: whether the next report date is known on the session (ADR 0046).

Input: the same ``events/earnings`` snapshots as ``earnings@v1``, read through its compute, so
both groups see the same rows and the same knowledge. One row per instrument with an
``earnings@v1`` row (a next or a last report date); an instrument with none has no row here
either, and its earnings stay UNKNOWN.

    next_status  SCHEDULED (a next report date on or after the session in the calendars
                 stored by then) or NOT_ANNOUNCED (none: only a last date). The
                 ``null_status`` of ``earnings@v1``'s next-report features, so a missing next
                 date reads "Not announced", not UNKNOWN

A status-only group, so ``earnings@v1`` keeps its stored columns (and every preset and saved
view naming them) instead of a re-version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, NullReason
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_schedule"
VERSION = 1
SCHEDULED, NOT_ANNOUNCED = "SCHEDULED", NullReason.NOT_ANNOUNCED.value

FEATURES = (
    Feature(
        "next_status", "str", "category",
        "SCHEDULED: a next report date on or after the session is in the calendars stored by "
        "then; NOT_ANNOUNCED: none, only a last report date",
        "never", "label", categories=(SCHEDULED, NOT_ANNOUNCED),
        inputs=(f"{earnings.EVENTS}.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    dates = earnings.compute(inputs, session, None)
    status = np.where(dates["next_earnings_date"].notna(), SCHEDULED, NOT_ANNOUNCED)
    return pd.DataFrame({"instrument_id": dates["instrument_id"], "next_status": status})


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Whether the next earnings date is announced (scheduled) on the session",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
