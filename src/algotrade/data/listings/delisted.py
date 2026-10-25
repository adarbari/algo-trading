"""``read_delisted_tickers``: Massive's inactive (delisted) tickers, the latest snapshot (ADR 0084).

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


def read_delisted_tickers(reader: StoreReader) -> tuple[pd.DataFrame, date]:
    """Every row of the latest ``instruments/delisted_tickers`` snapshot (``ticker``, ``name``,
    ``exchange``, ``vendor_type``, ``security_type``, ``cik``, ``figi``, ``share_class_figi``,
    ``end_date`` and the stamps) and that snapshot's date; ``MissingDataError`` with none."""
    frame, snap = read_snapshot(reader, TABLE, None, HINT)
    return frame, snap.snapshot_date
