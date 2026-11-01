"""``etf_launches``: when each specialised ETF launched, for the ``etf_launches@v1`` rollup
(ADR 0076).

The launch date is the Tiingo ``instruments/listing_history.start_date``, the earliest listing
of the instrument, disclosed as ``LAUNCH_SOURCE`` (not the fund's inception: a ticker change or
relisting moves it, and a fund older than Tiingo's coverage is capped at it). A listing is public
the day it starts, so the date is also the day the event is known (no later knowledge).

Both tables are read at their **latest snapshot**, the identity exception of
``data.listings.universe`` (the listing history is stamped with its pull time, the reference
snapshot carries today's name-rule category): a fund is offered for a session only from its own
start date, so point in time is kept by the dates, not the snapshot. The category is the one the
latest build resolved from the fund's name, so a fund renamed since launch carries today's
category on its launch date (a disclosed tilt), and a fund that never reached a reference
snapshot, or that the latest snapshot no longer lists, has none and is not in the sample
(a survivorship tilt: its row is in the edge's base without a category).
The listing's closing date is not read.
"""

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.data.listings.universe import listing_frame
from algotrade.data.reference import REFERENCE_HINT, read_snapshot
from algotrade.storage.tables.readers import StoreReader

LAUNCH_SOURCE = "tiingo_listing"
SPECIALISED = ("thematic", "sector")  # the paper's "specialised": sector funds and thematic funds
COLUMNS = ["instrument_id", "event_date", "etf_category", "etf_theme"]


def etf_launches(reader: StoreReader) -> pd.DataFrame:
    """One row per specialised ETF (``etf_category`` in ``SPECIALISED``): ``instrument_id``, its
    launch date as ``event_date`` and the category and theme. ``MissingDataError`` when a table
    has no snapshot, or the latest reference snapshot carries no category yet (the universe
    build has not run since ADR 0076): missing data is an error, never "no launches"."""
    reference, _ = read_snapshot(reader, REFERENCE_TABLE, None, REFERENCE_HINT)
    if "etf_category" not in reference.columns:
        raise MissingDataError(
            REFERENCE_TABLE,
            "the latest reference snapshot has no etf_category (built before ADR 0076)",
            REFERENCE_HINT,
        )
    funds = reference[reference["etf_category"].isin(SPECIALISED)]
    funds = funds[["instrument_id", "etf_category", "etf_theme"]]
    listings, _ = listing_frame(reader)
    listings = listings[["instrument_id", "start_date"]].dropna()
    starts = listings.assign(event_date=pd.to_datetime(listings["start_date"]).dt.date)
    first = starts.groupby("instrument_id")["event_date"].min().rename("event_date")
    out = funds.merge(first, left_on="instrument_id", right_index=True, how="inner")
    out = out.assign(instrument_id=out["instrument_id"].astype(str))
    return out[COLUMNS].sort_values(["event_date", "instrument_id"]).reset_index(drop=True)
