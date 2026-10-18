"""``ipo_lockups@v1``: how far an instrument's IPO lock-up expiry is, ahead or behind (the fields
the ``on_event:ipo_lockup[:<terms>]`` schedule reads, ADR 0075, ADR 0050, edge build D8).

Inputs: ``events/ipo_lockup`` as the session knew it (the loader keeps, per prospectus
(``cik`` + ``accession``), the latest version known on or before the session, so a re-extraction
that changed a value is never read early: ``data.events.latest_versions``) and the
``instruments/company`` snapshot on or before the session. Only ``is_ipo`` prospectuses with an
expiry date count. A prospectus is keyed by its ISSUER's CIK; the instrument is the one the CIK
maps to in the company snapshot AS OF THE SESSION, never the ``instrument_id`` stored on the row
(filled by a later run: a name that listed after the session, or a survivor, would leak). A CIK
with several share classes gives every one of them the event.

    lockup_expiry_date           the expiry session of the nearest lock-up in the window
    sessions_to_lockup_expiry    exchange sessions from the session to it: 3 three sessions ahead,
                                 0 the expiry session, negative after it down to ``-AFTER``
    lockup_release_terms         ``standard`` or ``early_release`` (the prospectus lets part of
                                 the lock-up end early, on earnings or a price condition)
    lockup_days                  the stated lock-up term in calendar days
    ipo_offer_price              the IPO offer price per share

The nearest lock-up is the earliest expiry on or after ``AFTER`` sessions before the session. An
instrument with none has no row (UNKNOWN, never "no lock-up").
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import session_offset
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "ipo_lockups"
VERSION = 1
EVENTS = "events/ipo_lockup"
COMPANY = "instruments/company"
AFTER = 20  # sessions after the expiry a lock-up is still read
STANDARD, EARLY_RELEASE = "standard", "early_release"
_NONE = (
    f"no IPO prospectus known by the session whose lock-up expires from {AFTER} sessions ago "
    "on, or its CIK is in no company snapshot of the session (the prospectus states no "
    "lock-up date, or the issuer is not an instrument yet)"
)
_INPUTS = (f"{EVENTS}.lockup_expiry", f"{EVENTS}.early_release", f"{EVENTS}.lockup_days")

FEATURES = (
    Feature(
        "lockup_expiry_date", "date", "date",
        "The expiry session of the nearest IPO lock-up (the event's anchor)", _NONE, inputs=_INPUTS,
    ),
    Feature(
        "sessions_to_lockup_expiry", "int", "sessions",
        f"Exchange sessions from the session to the lock-up expiry: 0 on the expiry session, "
        f"negative after it (down to -{AFTER})",
        _NONE, valid_range=(-AFTER, None), inputs=_INPUTS,
    ),
    Feature(
        "lockup_release_terms", "str", "category",
        "standard (one expiry date) or early_release (the prospectus lets part of the lock-up "
        "end early)",
        _NONE, "label", categories=(STANDARD, EARLY_RELEASE), inputs=_INPUTS,
    ),
    Feature(
        "lockup_days", "int", "days", "The lock-up term the prospectus states, in calendar days",
        _NONE + ", or the term is not stated", valid_range=(1, None), inputs=_INPUTS,
    ),
    Feature(
        "ipo_offer_price", "float", "usd_per_share", "The IPO offer price per share",
        _NONE + ", or the price is not stated", valid_range=(0, None), inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _ciks(company: pd.DataFrame | None) -> pd.DataFrame:
    """``instrument_id`` and ``cik`` of the company snapshot, rows with a CIK only."""
    if company is None or company.empty or "cik" not in company.columns:
        return pd.DataFrame({"instrument_id": [], "cik": []})
    ciks = company[["instrument_id", "cik"]].dropna()
    return ciks.assign(instrument_id=ciks["instrument_id"].astype(str), cik=ciks["cik"].astype(str))


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    rows = stored[stored["is_ipo"].fillna(False).astype(bool) & stored["lockup_expiry"].notna()]
    rows = rows.assign(
        lockup_expiry=pd.to_datetime(rows["lockup_expiry"]).dt.date, cik=rows["cik"].astype(str)
    )
    rows = rows.assign(offset=[session_offset(session, day) for day in rows["lockup_expiry"]]).pipe(
        lambda f: f[f["offset"] >= -AFTER]
    )
    rows = rows.drop(columns=["instrument_id"], errors="ignore")  # the row's own id: never read
    mapped = rows.merge(_ciks(inputs.get(COMPANY)), on="cik", how="inner")
    if mapped.empty:
        return pd.DataFrame(columns=columns)
    nearest = mapped.sort_values(["instrument_id", "lockup_expiry", "accession"], kind="stable")
    nearest = nearest.drop_duplicates("instrument_id", keep="first")
    early = nearest["early_release"].fillna(False).astype(bool)
    return pd.DataFrame(
        {
            "instrument_id": nearest["instrument_id"].to_numpy(),
            "lockup_expiry_date": list(nearest["lockup_expiry"]),
            "sessions_to_lockup_expiry": pd.array(nearest["offset"].to_numpy(), dtype="Int64"),
            "lockup_release_terms": [EARLY_RELEASE if e else STANDARD for e in early],
            "lockup_days": nearest["lockup_days"].astype("Int64").reset_index(drop=True),
            "ipo_offer_price": pd.to_numeric(nearest["offer_price"]).astype(float).to_numpy(),
        }
    )[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The nearest IPO lock-up expiry of an instrument, the sessions to it and its release terms",
    (
        Input(EVENTS, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
)
