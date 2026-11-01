"""Find the sessions in a folder of HistoricalOptionData zips without extracting any of them.

The owner downloads daily zips (``options_<YYYYMMDD>.csv`` and its two siblings) or monthly zips
whose members carry an ``L2_`` prefix, and one ``stockhistory`` zip (``dividends.csv``,
``stocksplits.csv``). ``scan`` reads only each zip's member list, so a 115 GB folder is listed in
seconds; ``open_member`` streams one member out of its zip.
"""

import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import IO

KINDS = ("options", "stockquotes", "optionstats")
_MEMBER = re.compile(r"^(?:L2_)?(?P<kind>options|stockquotes|optionstats)_(?P<day>\d{8})\.csv$")
STOCK_HISTORY = ("dividends.csv", "stocksplits.csv")


@dataclass(frozen=True)
class SessionFiles:
    """Where one session's three files are: the zip and the member name of each kind."""

    session: date
    zip_path: Path
    members: dict[str, str]  # kind -> member name

    @property
    def complete(self) -> bool:
        return all(kind in self.members for kind in KINDS)


def scan(root: Path) -> dict[date, SessionFiles]:
    """Every session found under ``root`` (any depth) by its ``options`` member. When a session
    is in two zips (a daily file inside a month's zip) the lexically last zip name wins, so a
    corrected download replaces an older one deterministically."""
    found: dict[date, SessionFiles] = {}
    for path in sorted(root.rglob("*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile:
            continue
        per_day: dict[str, dict[str, str]] = {}
        for name in names:
            match = _MEMBER.match(Path(name).name)
            if match:
                per_day.setdefault(match["day"], {})[match["kind"]] = name
        for day, members in per_day.items():
            session = date(int(day[:4]), int(day[4:6]), int(day[6:]))
            if "options" in members:
                found[session] = SessionFiles(session, path, members)
    return dict(sorted(found.items()))


def stock_history_zips(root: Path) -> list[Path]:
    """The zips under ``root`` holding the one-off stock history files."""
    out = []
    for path in sorted(root.rglob("*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                if set(STOCK_HISTORY) <= {Path(n).name for n in archive.namelist()}:
                    out.append(path)
        except zipfile.BadZipFile:
            continue
    return out


def open_member(zip_path: Path, member: str) -> IO[bytes]:
    """A stream of one member (the zip stays open until the stream is closed)."""
    archive = zipfile.ZipFile(zip_path)
    stream = archive.open(member)
    original_close = stream.close

    def close() -> None:
        original_close()
        archive.close()

    stream.close = close  # type: ignore[method-assign]
    return stream
