"""``read_delisted_tickers``: Massive's inactive (delisted) tickers, the latest snapshot (ADR 0087).

``instruments/delisted_tickers`` is a full copy per pull session, stamped with its pull time, so
the read takes the **latest snapshot** whatever the session and says which (ADR 0036's rule for
snapshot tables). ``end_date`` is the vendor's last trading day: this read is for the id merge
into the listing history and for the data-quality report only, never a feature, a label or a
sort key (``tests/architecture/data/test_listing_end_date_readers.py`` scans for the column).
``security_type`` is Massive's ``type`` mapped to ours, null where Massive gave none (before
2017); ``end_date`` is null for the few rows Massive dates not at all.

``read_delisted_details`` reads ``instruments/delisted_details`` (PR3b): Massive's ticker details
as of a record's last day, increments the ``delisted-details`` task adds, so the read is the union
of the partitions, the latest answer per (ticker, ``end_date``). Identity only, like the rest.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.data.reference import ALL_TIME, read_snapshot
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/delisted_tickers"
HINT = "algotrade-ingest run delisted-tickers"
DETAILS_TABLE = "instruments/delisted_details"
DETAILS_KEY = ["ticker", "end_date"]
# Massive's ``primary_exchange`` (a MIC) -> our exchange name, for the listing history's merge
# (ADR 0087): the five venues the Tiingo adapter keeps (``tiingo/listings.EXCHANGES``). Here, not
# in the vendor module, because ingestion tasks never import vendors (R3). An unmapped MIC (OTC,
# a foreign venue, none) is a record outside the universe's scope.
EXCHANGE_BY_MIC = {"XNAS": "NASDAQ", "XNYS": "NYSE", "XASE": "AMEX", "ARCX": "ARCA", "BATS": "BATS"}


def read_delisted_tickers(reader: StoreReader) -> tuple[pd.DataFrame, date]:
    """Every row of the latest ``instruments/delisted_tickers`` snapshot (``ticker``, ``name``,
    ``exchange`` (the MIC), ``vendor_type``, ``security_type``, ``cik``, ``figi``,
    ``share_class_figi``, ``market``, ``locale``, ``currency_name``, ``last_updated_utc``,
    ``end_date`` and the stamps; the four after ``share_class_figi`` are absent from a snapshot
    pulled before ADR 0087's merge) and that snapshot's date; ``MissingDataError`` with none."""
    frame, snap = read_snapshot(reader, TABLE, None, HINT)
    return frame, snap.snapshot_date


def read_delisted_details(reader: StoreReader, as_of: datetime | None = None) -> pd.DataFrame:
    """Every stored answer of the details task, the latest per (``ticker``, ``end_date``), found
    or not (``found`` false: Massive did not know the ticker that day): ``ticker``, ``end_date``,
    ``asked_date``, ``found``, ``list_date``, ``delisted_date``, ``cik``, ``figi`` and the other
    columns of the table. Empty (no columns beyond the key) when the task never ran: absent
    details are no details, never a failure."""
    frame = reader.table_range(DETAILS_TABLE, *ALL_TIME, as_of, None)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*DETAILS_KEY, "found"])
    frame = frame.sort_values("knowledge_ts", kind="stable")
    frame = frame.drop_duplicates(["source", *DETAILS_KEY], keep="last")
    return frame.sort_values(DETAILS_KEY, kind="stable").reset_index(drop=True)
