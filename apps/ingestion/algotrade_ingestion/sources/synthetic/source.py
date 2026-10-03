"""``GoldenCsvSource``: the committed golden CSVs exposed through the standard source contract.

Request key: ``<dataset>/<SYMBOL>``; the request's ``instrument_id`` (resolved by the golden
job) keys the rows. Payloads are whole price histories, so normalised frames carry a ``ts``
per row and ``session_date`` is ``None``.
"""

from algotrade_ingestion.sources.base import FetchRequest, Normalized
from algotrade_ingestion.sources.synthetic.files import GoldenFiles, parse_csv

BARS_TABLE = "bars/1d"


class GoldenCsvSource:
    name = "synthetic"
    dataset = "golden_csv"

    def __init__(self, files: GoldenFiles) -> None:
        self.files = files

    def fetch(self, request: FetchRequest) -> bytes | None:
        dataset, _, symbol = request.key.partition("/")
        path = self.files.path(dataset, symbol)
        return path.read_bytes() if symbol and path.exists() else None

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        if not request.instrument_id:
            raise ValueError(f"{request.key}: golden bars need the request's instrument_id")
        bars = parse_csv(payload, request.key)
        bars.insert(0, "instrument_id", request.instrument_id)
        return Normalized(session_date=None, tables={BARS_TABLE: bars})
