"""Recorded Treasury par yield curve CSVs (real format, trimmed rows).

Files: ``tests/fixtures/sources/treasury/``."""

from pathlib import Path

from tests.conftest import REPO_ROOT

DIR = REPO_ROOT / "tests" / "fixtures" / "sources" / "treasury"


def payload(year: int) -> bytes:
    """The recorded CSV for 2025 (with 1.5 Month and 4 Mo) or 2020 (older columns)."""
    return Path(DIR / f"yield_curve_{year}.csv").read_bytes()
