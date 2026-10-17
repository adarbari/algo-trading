"""``analyst_targets@v1``: where analysts put the price of a stock.

Inputs: ``analyst/estimate_snapshots`` as the session sees it (our own nightly history of FMP's
price-target consensus: ``data.analyst.reading``) and the session's ``universe`` (one row per
equity). ``licence = "personal"`` on every feature (ADR 0068, ADR 0069).

    target_consensus, target_median   the average and the median analyst price target, USD
    target_high, target_low           the highest and the lowest
    targets_age_days                  days from the snapshot's session to this one
    targets_status                    OK / STALE / NOT_COVERED / NOT_FETCHED (``analyst_status``)

The targets are the vendor's current ones on the day it was asked: they carry no date of their
own, and the vendor restates them silently, so only the snapshots we stored make a past session
reproducible. A STALE snapshot (older than ``stale_days``, 21) serves no values: they read as
not stored, the age and status stay. The values are in the vendor's reporting currency, which for
a foreign filer is not the listing's.
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.consensus.analyst_status import (
    LOOKBACK,
    OK,
    SNAPSHOTS,
    STATUSES,
    TARGET,
    UNCOVERED,
    UNIVERSE,
    AnalystParams,
    population,
    resolve,
    vendor_rows,
)

NAME = "analyst_targets"
VERSION = 1
_P: Licence = "personal"
_SNAP = f"{SNAPSHOTS}."
_STATUS = "targets_status"
_WHY = (
    "targets_status is STALE (the newest snapshot is older than stale_days), NOT_COVERED (the "
    "vendor has no price target for the name) or NOT_FETCHED (never asked: the nightly rotation "
    "has not reached it)"
)
_VALUES = {
    "target_consensus": "The average analyst price target, USD, as the newest snapshot says",
    "target_median": "The median analyst price target, USD",
    "target_high": "The highest analyst price target, USD",
    "target_low": "The lowest analyst price target, USD",
}

FEATURES = (
    *(
        Feature(
            name, "float32", "usd_per_share", what, _WHY, valid_range=(0.0, None),
            inputs=(f"{_SNAP}{name}",), licence=_P, null_status=_STATUS,
            uncovered_statuses=UNCOVERED,
        )
        for name, what in _VALUES.items()
    ),
    Feature(
        "targets_age_days", "int", "days",
        "Days from the snapshot's session to this session: how old the targets are (shown for "
        "OK and STALE)",
        "targets_status is NOT_COVERED or NOT_FETCHED: no snapshot of the name",
        valid_range=(0, None), inputs=(f"{_SNAP}session_date",), licence=_P,
        null_status=_STATUS, uncovered_statuses=UNCOVERED,
    ),
    Feature(
        _STATUS, "str", "category",
        "OK: a snapshot at most stale_days (21) old; STALE: older, values not served; "
        "NOT_COVERED: the vendor has no price target for the name; NOT_FETCHED: never asked",
        "never", "label", categories=STATUSES, inputs=(f"{_SNAP}kind",), licence=_P,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def compute(inputs: Inputs, session: date, p: AnalystParams) -> pd.DataFrame:
    snapshots = inputs.get(SNAPSHOTS)
    ids = population(inputs[UNIVERSE], snapshots)
    rows = vendor_rows(snapshots, TARGET)
    status = resolve(ids, rows, snapshots, session, p)
    out = pd.DataFrame({"instrument_id": status["instrument_id"]})
    out[_STATUS] = status["status"]
    out["targets_age_days"] = pd.to_numeric(status["age_days"])
    served = rows[
        rows["instrument_id"].isin(set(status.loc[status["status"] == OK, "instrument_id"]))
    ]
    served = served.sort_values("instrument_id", kind="stable").drop_duplicates(
        "instrument_id", keep="last"
    )
    served = served.set_index("instrument_id")
    for name in _VALUES:
        out[name] = out["instrument_id"].map(pd.to_numeric(served[name]))
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Analysts' price targets: consensus, median, high and low (FMP price-target consensus, our "
    "own point-in-time snapshots; personal-use licence)",
    (Input(UNIVERSE), Input(SNAPSHOTS, lookback=LOOKBACK, required=False)),
    FEATURES,
    compute,
    AnalystParams(),
    optional=True,  # a screen without the table warns, never PARTIAL (ADR 0055, ADR 0068)
)
