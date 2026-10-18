"""``share_classes@v1``: the other share class of an issuer and how far apart the two trade (the
fields the ``pair_spread`` outcome reads, ADR 0053 amendment, EB H9).

An issuer with two listed classes (GOOG / GOOGL, BRK.A / BRK.B) is a pair: the same cash flows
under two tickers, so the price ratio should stay near its own mean. One row per instrument of
such an issuer; every other instrument has no row (UNKNOWN, never "no sibling").

Inputs: ``instruments/reference`` (the snapshot the session sees: the sibling is the one of
THAT snapshot, so a reclassification is read at the date it happened, never from today's
reference), ``bars/1d`` split-adjusted as of the session, 252 sessions back. An operating
company (``COMMON_STOCK`` / ``ADR``) is grouped by its issuer ``cik`` and its ``share_class_figi``
(ADR 0018: the id is the row's own ``instrument_id``, never built from a ticker or a hand list).

    sibling_id      the other class's instrument id (null: the issuer's classes do not make a
                    pair, see sibling_status)
    class_count     the issuer's share classes in the reference
    sibling_status  PAIRED (exactly two classes, one instrument each) or AMBIGUOUS (three or
                    more classes, or a class listed under several ids: no pair is guessed)
    spread_z_252d   z-score of today's ln(close / sibling close) in the trailing 252 sessions'
                    values of it; negative: this class is cheap against its sibling
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.instruments import pad_cik
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import OPERATING_TYPES, Feature
from algotrade.features.rollups.market.tickers import BARS
from algotrade.features.rollups.price.price_stats import panel

NAME = "share_classes"
VERSION = 1
REFERENCE = "instruments/reference"
LOOKBACK = 252  # sessions of the ratio the z-score is read against
MIN_RATIOS = 200  # fewest sessions of the ratio a z-score needs (both classes with a bar)
PAIRED, AMBIGUOUS = "PAIRED", "AMBIGUOUS"
STATUSES = (PAIRED, AMBIGUOUS)
_NO_PAIR = "the issuer has one class listed, or the reference has no issuer or class id for it"
_NO_Z = (
    f"the status is not PAIRED, either class has fewer than {MIN_RATIOS} of the last "
    f"{LOOKBACK + 1} sessions with a bar, or the ratio has no spread over them"
)

FEATURES = (
    Feature(
        "sibling_id", "str", "text",
        "The issuer's other listed share class (an instrument id of the reference snapshot the "
        "session sees): the one class sharing its issuer CIK with a different share-class FIGI",
        f"{_NO_PAIR}; or the classes are not a pair (see sibling_status)",
        "label", inputs=(f"{REFERENCE}.cik", f"{REFERENCE}.share_class_figi"),
    ),
    Feature(
        "class_count", "int", "count",
        "How many share classes of the issuer the reference lists (operating companies only)",
        _NO_PAIR, valid_range=(2, None),
        inputs=(f"{REFERENCE}.cik", f"{REFERENCE}.share_class_figi"),
    ),
    Feature(
        "sibling_status", "str", "category",
        "PAIRED: exactly two classes, one instrument each; AMBIGUOUS: three or more classes, or "
        "a class under several ids, so no pair is named",
        _NO_PAIR, "label", categories=STATUSES,
        inputs=(f"{REFERENCE}.cik", f"{REFERENCE}.share_class_figi"),
    ),
    Feature(
        f"spread_z_{LOOKBACK}d", "float32", "ratio",
        f"Where today's ln(close / sibling close) stands against its own last {LOOKBACK} "
        "sessions: (today - mean) / standard deviation. -2 is two standard deviations cheaper "
        "than its usual gap to the sibling, +2 as much richer",
        _NO_Z, valid_range=(-20, 20), inputs=(f"{BARS}.close", f"{REFERENCE}.share_class_figi"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def pairs(reference: pd.DataFrame) -> pd.DataFrame:
    """One row per instrument of an issuer with two or more classes: ``instrument_id``,
    ``sibling_id``, ``class_count`` and ``sibling_status`` (the module doc's rules)."""
    need = {"instrument_id", "cik", "share_class_figi", "security_type"}
    columns = ["instrument_id", "sibling_id", "class_count", "sibling_status"]
    if not need <= set(
        reference.columns
    ):  # never an empty answer: every pick would read no_sibling
        raise MissingDataError(
            REFERENCE,
            f"the snapshot has no {sorted(need - set(reference.columns))} column",
            "rebuild the reference snapshot (algotrade-ingest reference)",
        )
    held = reference[reference["security_type"].isin(OPERATING_TYPES)].copy()
    held["cik"] = held["cik"].map(pad_cik)  # one form of the issuer id
    held = held[held["cik"].notna()]
    held = held[held["share_class_figi"].fillna("").astype(str).str.strip().ne("")]
    rows = []
    for _, issuer in held.groupby("cik", sort=True):
        classes = issuer.groupby("share_class_figi")["instrument_id"].apply(sorted)
        if len(classes) < 2:
            continue
        ids = [i for group in classes for i in group]
        pair = len(classes) == 2 and all(len(group) == 1 for group in classes)
        for i in ids:
            other = [j for j in ids if j != i]
            rows.append(
                {
                    "instrument_id": str(i),
                    "sibling_id": str(other[0]) if pair else None,
                    "class_count": len(classes),
                    "sibling_status": PAIRED if pair else AMBIGUOUS,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def spread_z(close: pd.DataFrame, ids: list[str], siblings: list[str | None]) -> np.ndarray:
    """The z-score of each instrument's last ln(close / sibling close) over the window's
    values of it (NaN: no sibling, too few sessions with both bars, or no spread)."""
    column = {iid: at for at, iid in enumerate(close.columns)}
    out = np.full(len(ids), np.nan)
    for at, (own, other) in enumerate(zip(ids, siblings, strict=True)):
        if other is None or own not in column or other not in column:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.log(close[own].to_numpy() / close[other].to_numpy())
        seen = ratio[np.isfinite(ratio)]
        if len(seen) < MIN_RATIOS or not np.isfinite(ratio[-1]) or float(np.std(seen)) == 0.0:
            continue
        out[at] = (ratio[-1] - float(np.mean(seen))) / float(np.std(seen))
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    reference = inputs[REFERENCE]
    assert reference is not None  # a required input
    found = pairs(reference)
    columns = ["instrument_id", *COLUMNS]
    if found.empty:
        return pd.DataFrame(columns=columns)
    z = np.full(len(found), np.nan)
    bars = inputs.get(BARS)
    if bars is not None and not bars.empty:
        days = sessions_ending(session, LOOKBACK + 1)
        px = panel(bars, days)
        close = pd.DataFrame(px.close, columns=list(px.ids))
        siblings = [None if pd.isna(s) else str(s) for s in found["sibling_id"]]
        z = spread_z(close, [str(i) for i in found["instrument_id"]], siblings)
    frame = found.assign(**{f"spread_z_{LOOKBACK}d": z})
    frame["class_count"] = frame["class_count"].astype("Int64")
    return frame[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The other listed share class of an issuer and where the pair's price ratio stands",
    (Input(REFERENCE), Input(BARS, lookback=LOOKBACK, required=False)),
    FEATURES,
    compute,
    applies_to="operating_company",
)
