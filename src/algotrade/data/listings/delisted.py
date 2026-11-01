"""``read_delisted_tickers``: Massive's inactive (delisted) tickers, the latest snapshot (ADR 0087).

``instruments/delisted_tickers`` is a full copy per pull session, stamped with its pull time, so
the read takes the **latest snapshot** whatever the session and says which (ADR 0036's rule for
snapshot tables). ``end_date`` is the vendor's last trading day: this read is for the id merge
into the listing history and for the data-quality report only, never a feature, a label or a
sort key (``tests/architecture/data/test_listing_end_date_readers.py`` scans for the column).
``security_type`` is Massive's ``type`` mapped to ours, null where Massive gave none (before
2017); ``end_date`` is null for the few rows Massive dates not at all.
"""

from datetime import date

import pandas as pd

from algotrade.data.reference import read_snapshot
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/delisted_tickers"
HINT = "algotrade-ingest run delisted-tickers"
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
