"""Where an event's own source page is (``source_link``), so the web app receives a ready URL and
never assembles one. Three kinds link, from what is already stored (no new column):

- ``filing``: an 8-K or 8-K/A (``events/filing`` ``cik`` + ``accession``) to its sec.gov filing
  index;
- ``earnings``: a report stored from the 8-K Item 2.02 release (source ``sec_8k``) to the index of
  the same company's Item 2.02 filing accepted at that instant; a report from
  the Nasdaq calendar alone, and one still ahead, has no filing and so no link;
- ``macro_release``: a release key to the agency page held in ``config/site/events/links.toml``.

Every other kind (dividends, splits, reference changes, expiry days) has none: nothing stored
names a page. URLs only point at sec.gov or at an address of that file; a ``cik`` or ``accession``
that is not the plain digits SEC writes yields no link rather than an interpolated one."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from algotrade.storage.tables.schemas.events import EARNINGS_8K_SOURCE

SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
RESULTS_ITEM = "2.02"  # the 8-K item of a results release
KINDS = ("filing", "earnings", "macro_release")
_CIK = re.compile(r"^\d{1,10}$")
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_SAME_INSTANT = timedelta(seconds=1)  # a midnight acceptance is stored one second later


@dataclass(frozen=True)
class FilingRef:
    """An 8-K as the link needs it: its ``cik`` and ``accession``, the acceptance instant
    (UTC) and its ``form`` (8-K or 8-K/A)."""

    cik: str
    accession: str
    accepted: datetime
    form: str


def filing_url(cik: str, accession: str) -> str | None:
    """The sec.gov filing index of ``accession`` filed by ``cik`` (None: either is not the
    plain digits SEC writes)."""
    cik, accession = cik.strip(), accession.strip()
    if not _CIK.match(cik) or not _ACCESSION.match(accession):
        return None
    return f"{SEC_ARCHIVE}/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


def results_filing(at: datetime, filings: Sequence[FilingRef]) -> FilingRef | None:
    """The Item 2.02 filing a report stored at ``at`` (UTC) came from: the one accepted at that
    instant (a report row is made from an original 8-K at its acceptance instant, so a filing
    of the same day at another instant is a different one: never matched); an 8-K before its
    amendment when both match; None when none does."""
    found = [f for f in filings if abs(f.accepted - at) <= _SAME_INSTANT]
    return min(found, key=lambda f: (f.form != "8-K", f.accepted)) if found else None


def source_link(
    kind: str,
    *,
    cik: str | None = None,
    accession: str | None = None,
    release_key: str | None = None,
    macro_links: Mapping[str, str] | None = None,
    source: str | None = None,
    at: datetime | None = None,
    filings: Sequence[FilingRef] = (),
) -> str | None:
    """The page of one event, or None when it has none. ``kind``: ``filing`` (``cik``,
    ``accession``), ``earnings`` (the row's ``source``, its ``ts`` as ``at`` and the company's
    Item 2.02 ``filings``) or ``macro_release`` (``release_key`` against ``macro_links``, the
    config's release key -> page); any other kind, or a missing input, is None."""
    if kind == "filing" and cik is not None and accession is not None:
        return filing_url(cik, accession)
    if kind == "macro_release" and release_key is not None:
        return (macro_links or {}).get(release_key)
    if kind == "earnings" and source == EARNINGS_8K_SOURCE and at is not None:
        match = results_filing(at, filings)
        return filing_url(match.cik, match.accession) if match else None
    return None
