"""Read the Describe-it events (``feedback/drafting_events``) and the missing-feature requests
(``feedback/feature_requests``), written by the API's feedback recorders, for a range of exchange
calendar dates. Unfiltered: whose rows a viewer may see is the loader's rule (ADR 0066), not this
module's."""

from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

DRAFTING_EVENTS = "feedback/drafting_events"
FEATURE_REQUESTS = "feedback/feature_requests"


def read_drafting_events(
    reader: StoreReader, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The events of ``start``..``end`` (inclusive), ``None`` when nothing was recorded."""
    return reader.table_range(DRAFTING_EVENTS, start, end, as_of)


def read_feature_requests(
    reader: StoreReader, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The requests of ``start``..``end`` (inclusive), ``None`` when nothing was recorded."""
    return reader.table_range(FEATURE_REQUESTS, start, end, as_of)
