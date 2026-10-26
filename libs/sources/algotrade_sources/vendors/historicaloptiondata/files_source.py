"""``HodFiles``: a folder of bought HistoricalOptionData zips as a source (ADR 0084).

Not an HTTP vendor: the registry builds it from the directory the owner points a task at
(``registry.FILE_SOURCES``, beside the golden fixture sources). ``sessions`` lists the folder by
member names, ``read`` parses one session (streamed out of its zip: nothing is extracted), and
``stock_history`` the one-off dividends and splits. ``fetch`` / ``normalize`` (the ``Source``
contract) give one session's ``options`` bytes and their frame; the import uses ``read``."""

import hashlib
import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import index_id
from algotrade_sources.framework.base import FetchRequest, HistorySession, Normalized
from algotrade_sources.vendors.historicaloptiondata.archive import (
    SessionFiles,
    open_member,
    scan,
    stock_history_zips,
)
from algotrade_sources.vendors.historicaloptiondata.session_files import (
    INDEX_UNDERLYINGS,
    parse_option_stats,
    parse_options,
    parse_stock_quotes,
)
from algotrade_sources.vendors.historicaloptiondata.stock_history import (
    parse_dividends,
    parse_splits,
)

SOURCE = "historicaloptiondata"
DATASET = "option_history"
QUOTES = "option_history/quotes"
UNDERLYING = "option_history/underlying"
STATS = "option_history/stats"
DIVIDENDS = "option_history/dividends"
SPLITS = "option_history/splits"


class HodFiles:
    """Implements ``Source`` and ``HistoryFileSource``. Request key = ``YYYY-MM-DD``."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, directory: Path | None) -> None:
        self.directory = directory  # None: built without --source-dir (``--init`` needs none)
        self._found: dict[date, SessionFiles] | None = None

    def _root(self) -> Path:
        if self.directory is None:
            raise ConfigurationError(
                "option-history-import needs --source-dir (the folder of zips)"
            )
        return self.directory

    def _files(self) -> dict[date, SessionFiles]:
        if self._found is None:
            self._found = scan(self._root())
        return self._found

    def sessions(self) -> list[HistorySession]:
        out = []
        for day, files in self._files().items():
            with zipfile.ZipFile(files.zip_path) as archive:
                infos = [archive.getinfo(files.members[kind]) for kind in sorted(files.members)]
            # every member counts: a stockquotes file added to a session later is a change too
            digest = "|".join(f"{i.filename}:{i.CRC:08x}:{i.file_size}" for i in infos)
            checksum = (
                f"{hashlib.sha1(digest.encode()).hexdigest()[:8]}:{sum(i.file_size for i in infos)}"
            )
            out.append(HistorySession(day, files.zip_path.name, checksum, files.complete))
        return out

    def fetch(self, request: FetchRequest) -> bytes | None:
        files = self._files().get(date.fromisoformat(request.key))
        if files is None:
            return None
        with zipfile.ZipFile(files.zip_path) as archive:
            return archive.read(files.members["options"])

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        parsed = parse_options(io.BytesIO(payload))
        if parsed is None:
            return None
        return Normalized(parsed.session, {QUOTES: parsed.options}, parsed.notes)

    def read(self, session: date) -> Normalized:
        files = self._files()[session]
        stream = open_member(files.zip_path, files.members["options"])
        try:
            parsed = parse_options(stream)
        finally:
            stream.close()
        if parsed is None or parsed.options.empty:
            raise ValueError(f"{session}: the options file holds no rows we keep")
        if parsed.session != session:
            raise ValueError(f"{session}: the options file is for {parsed.session}")
        tables: dict[str, pd.DataFrame] = {QUOTES: _with_index_ids(parsed.options)}
        for kind, table, parse in (
            ("stockquotes", UNDERLYING, parse_stock_quotes),
            ("optionstats", STATS, parse_option_stats),
        ):
            member = files.members.get(kind)
            if member is None:
                continue
            stream = open_member(files.zip_path, member)
            try:
                tables[table] = _with_index_ids(parse(stream))
            finally:
                stream.close()
        return Normalized(session, tables, parsed.notes, {"excluded_roots": parsed.excluded_roots})

    def stock_history(self) -> Normalized | None:
        zips = stock_history_zips(self._root())
        if not zips:
            return None
        path = zips[-1]
        dividends = splits = None
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                base = Path(name).name
                if base == "dividends.csv":
                    with archive.open(name) as stream:
                        dividends = parse_dividends(stream)
                elif base == "stocksplits.csv":
                    with archive.open(name) as stream:
                        splits = parse_splits(stream)
        if dividends is None or splits is None:
            return None
        return Normalized(None, {DIVIDENDS: dividends, SPLITS: splits}, {})


def _with_index_ids(frame: pd.DataFrame) -> pd.DataFrame:
    """``underlying_id`` of the index underlyings (``IDX:SPX`` for SPX and SPXW, the ``root``
    keeping their settlements apart); null for every other symbol: the task resolves those from
    the listing history as of the session, and a name with none stays null."""
    out = frame.copy()
    out["underlying_id"] = out["symbol"].map(
        lambda s: index_id(INDEX_UNDERLYINGS[s]) if s in INDEX_UNDERLYINGS else None
    )
    return out


def hod_files(directory: Path | None = None) -> HodFiles:
    return HodFiles(directory)
